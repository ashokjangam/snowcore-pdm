"""Why did the Plant A model fail, and is the label predictable by anything?

The Snowflake run produced a model whose held-out probabilities were slightly
HIGHER for non-alarm rows than for alarm rows. That is not a weak model, it is
no model, and a tuning pass would be wasted effort until we know whether the
signal exists at all.

This runs locally on the CSVs so the experiments are seconds rather than
minutes, and answers four questions in order of how much they would change the
plan:

  1. Persistence. How well does "a module alarm is firing right now" predict
     "a module alarm in the next 60 minutes"? If that is strong, then alarm
     autocorrelation is the real signal and excluding it from the features left
     the model with nothing.
  2. Nowcast. Can the sensors identify a CONCURRENT alarm? If they cannot even
     do that, they do not carry the fault signature at 10-minute aggregation
     and no forward horizon will rescue them.
  3. Drift. Does the train period look like the test period per machine? A
     chronological split across a distribution shift can produce exactly the
     inverted result we saw.
  4. Horizon. Does a shorter or longer lead time change anything?

Read-only. Nothing here writes to Snowflake.
"""

from __future__ import annotations

import pathlib
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

RAW = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw" / "comopi"
SENSORS = RAW / "industrial_dataset_sensors_10m_agg.csv"
ALARMS = RAW / "industrial_dataset_alarm_10m_agg.csv"

MODULE_ALARMS = [
    "AL_17", "AL_18", "AL_40", "AL_41", "AL_42", "AL_43", "AL_45", "AL_46",
    "AL_47", "AL_48", "AL_49", "AL_50", "AL_51", "AL_52", "AL_53", "AL_54",
]
A_SIDE = ["AE", "AF", "APP", "AP", "ALE", "ALP", "ADS", "AES"]
B_SIDE = ["BE", "BF", "BPP", "BP", "BLE", "BLP", "BDS", "BES"]
SENSOR_COLS = A_SIDE + B_SIDE

CUTOFF = pd.Timestamp("2022-12-08 08:52:00", tz="UTC")


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    sensors = pd.read_csv(SENSORS)
    alarms = pd.read_csv(ALARMS)
    for f in (sensors, alarms):
        f["_time"] = pd.to_datetime(f["_time"], utc=True, format="ISO8601")
    alarms["module_count"] = alarms[MODULE_ALARMS].sum(axis=1)
    alarms["module_hit"] = alarms["module_count"] > 0
    return sensors, alarms


def build(sensors: pd.DataFrame, alarms: pd.DataFrame, horizon_min: int) -> pd.DataFrame:
    """Sensor rows with rolling features, an alarm-now flag, and a forward label."""
    hits = alarms.loc[alarms["module_hit"], ["_serial", "_time"]]
    out = []
    for serial, grp in sensors.groupby("_serial"):
        grp = grp.sort_values("_time").copy()
        # Drop the tz after converting, so numpy gives datetime64 rather than
        # an object array and vectorised arithmetic works.
        times = grp["_time"].dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()
        hit_arr = (
            hits.loc[hits["_serial"] == serial, "_time"]
            .dt.tz_convert("UTC").dt.tz_localize(None)
            .sort_values().to_numpy()
        )

        if len(hit_arr):
            horizon = pd.Timedelta(minutes=horizon_min).to_timedelta64()
            nxt = hit_arr.searchsorted(times, side="right")
            grp["label_fwd"] = [
                bool(i < len(hit_arr) and (hit_arr[i] - t) <= horizon)
                for i, t in zip(nxt, times)
            ]
            same = hit_arr.searchsorted(times, side="left")
            grp["alarm_now"] = [
                bool(i < len(hit_arr) and hit_arr[i] == t) for i, t in zip(same, times)
            ]
            # Was there a module alarm in the previous hour?
            prv = hit_arr.searchsorted(times - pd.Timedelta(hours=1).to_timedelta64(),
                                       side="left")
            grp["alarm_past_1h"] = [
                bool(p < s) for p, s in zip(prv, hit_arr.searchsorted(times, side="right"))
            ]
        else:
            grp["label_fwd"] = False
            grp["alarm_now"] = False
            grp["alarm_past_1h"] = False

        idx = grp.set_index("_time")
        for col in SENSOR_COLS:
            roll = idx[col].rolling("60min")
            grp[f"{col}_m1"] = roll.mean().to_numpy()
            grp[f"{col}_s1"] = roll.std().to_numpy()
            grp[f"{col}_d6"] = (idx[col] - idx[col].rolling("6h").mean()).to_numpy()
        out.append(grp)

    df = pd.concat(out).sort_values("_time").reset_index(drop=True)
    df[B_SIDE] = df[B_SIDE].fillna(-1)
    feat_cols = [c for c in df.columns if c.endswith(("_m1", "_s1", "_d6"))]
    df[feat_cols] = df[feat_cols].fillna(-1)
    return df


def rate(mask: pd.Series, label: pd.Series) -> str:
    if mask.sum() == 0:
        return "n=0"
    return f"n={int(mask.sum())} rate={label[mask].mean() * 100:.1f}%"


def q1_persistence(df: pd.DataFrame) -> None:
    print("=" * 70)
    print("1. PERSISTENCE — is the answer just 'an alarm is already firing'?")
    print("=" * 70)
    base = df["label_fwd"].mean() * 100
    print(f"base rate                     : {base:.1f}%")
    print(f"given alarm_now = True        : {rate(df['alarm_now'], df['label_fwd'])}")
    print(f"given alarm_now = False       : {rate(~df['alarm_now'], df['label_fwd'])}")
    print(f"given alarm in past hour      : {rate(df['alarm_past_1h'], df['label_fwd'])}")
    print(f"given no alarm in past hour   : {rate(~df['alarm_past_1h'], df['label_fwd'])}")
    lift = df.loc[df["alarm_past_1h"], "label_fwd"].mean() / df["label_fwd"].mean()
    print(f"\nlift from past-hour alarm alone: {lift:.2f}x base rate")


def _fit_eval(train: pd.DataFrame, test: pd.DataFrame, cols: list[str],
              target: str, name: str) -> None:
    ytr, yte = train[target].astype(int), test[target].astype(int)
    if yte.sum() == 0 or ytr.sum() == 0:
        print(f"  {name:38s} skipped (no positives in one side)")
        return
    gb = GradientBoostingClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.1, subsample=0.8,
        random_state=20260924,
    )
    gb.fit(train[cols], ytr)
    p = gb.predict_proba(test[cols])[:, 1]
    auc = roc_auc_score(yte, p)
    ap = average_precision_score(yte, p)
    print(f"  {name:38s} AUC={auc:.3f}  AP={ap:.3f}  "
          f"(base AP={yte.mean():.3f})  meanP+={p[yte == 1].mean():.3f} "
          f"meanP-={p[yte == 0].mean():.3f}")


def q2_nowcast(df: pd.DataFrame) -> None:
    print()
    print("=" * 70)
    print("2. CAN THE SENSORS SEE ANYTHING? chronological split, AUC 0.5 = noise")
    print("=" * 70)
    train = df[df["_time"] < CUTOFF]
    test = df[df["_time"] >= CUTOFF]
    roll = [c for c in df.columns if c.endswith(("_m1", "_s1", "_d6"))]
    raw_and_roll = SENSOR_COLS + roll

    print(" forward label (alarm in next 60 min):")
    _fit_eval(train, test, SENSOR_COLS, "label_fwd", "raw sensors only")
    _fit_eval(train, test, raw_and_roll, "label_fwd", "raw + rolling (as built in SQL)")
    _fit_eval(train, test, raw_and_roll + ["alarm_now", "alarm_past_1h"],
              "label_fwd", "raw + rolling + alarm history")

    print(" concurrent label (alarm in THIS window):")
    _fit_eval(train, test, SENSOR_COLS, "alarm_now", "raw sensors only")
    _fit_eval(train, test, raw_and_roll, "alarm_now", "raw + rolling")

    # A linear model too: if trees fail but logistic works, it was overfitting.
    ytr = train["label_fwd"].astype(int)
    yte = test["label_fwd"].astype(int)
    sc = StandardScaler().fit(train[raw_and_roll])
    lr = LogisticRegression(max_iter=2000, C=0.1).fit(sc.transform(train[raw_and_roll]), ytr)
    p = lr.predict_proba(sc.transform(test[raw_and_roll]))[:, 1]
    print(f"  {'logistic regression, forward label':38s} "
          f"AUC={roc_auc_score(yte, p):.3f}  AP={average_precision_score(yte, p):.3f}")


def q3_drift(df: pd.DataFrame) -> None:
    print()
    print("=" * 70)
    print("3. DRIFT — does the training period resemble the test period?")
    print("=" * 70)
    train = df[df["_time"] < CUTOFF]
    test = df[df["_time"] >= CUTOFF]

    print(" positive rate per machine, train vs test:")
    for serial in sorted(df["_serial"].unique()):
        tr = train[train["_serial"] == serial]
        te = test[test["_serial"] == serial]
        tr_r = f"{tr['label_fwd'].mean() * 100:5.1f}%" if len(tr) else "    -"
        te_r = f"{te['label_fwd'].mean() * 100:5.1f}%" if len(te) else "    -"
        print(f"   {serial}: train n={len(tr):5d} {tr_r}   test n={len(te):5d} {te_r}")

    print("\n sensor mean shift, train vs test (abs diff, top 6):")
    shift = {c: abs(train[c].mean() - test[c].mean()) for c in SENSOR_COLS}
    for c, v in sorted(shift.items(), key=lambda kv: -kv[1])[:6]:
        print(f"   {c}: train={train[c].mean():.3f} test={test[c].mean():.3f} diff={v:.3f}")

    # Can a model tell train from test? High AUC means the periods differ so
    # much that a model fitted on one cannot be expected to transfer.
    probe = pd.concat([train.assign(_is_test=0), test.assign(_is_test=1)])
    roll = [c for c in df.columns if c.endswith(("_m1", "_s1", "_d6"))]
    gb = GradientBoostingClassifier(n_estimators=100, max_depth=4,
                                    random_state=20260924)
    half = probe.sample(frac=0.5, random_state=20260924)
    rest = probe.drop(half.index)
    gb.fit(half[SENSOR_COLS + roll], half["_is_test"])
    auc = roc_auc_score(rest["_is_test"], gb.predict_proba(rest[SENSOR_COLS + roll])[:, 1])
    print(f"\n adversarial train-vs-test AUC: {auc:.3f}")
    print("   0.5 = periods indistinguishable; above ~0.8 = serious drift")


def q4_horizon(sensors: pd.DataFrame, alarms: pd.DataFrame) -> None:
    print()
    print("=" * 70)
    print("4. HORIZON — does a different lead time help?")
    print("=" * 70)
    for h in (10, 30, 60, 180, 360):
        d = build(sensors, alarms, h)
        train, test = d[d["_time"] < CUTOFF], d[d["_time"] >= CUTOFF]
        roll = [c for c in d.columns if c.endswith(("_m1", "_s1", "_d6"))]
        cols = SENSOR_COLS + roll
        ytr, yte = train["label_fwd"].astype(int), test["label_fwd"].astype(int)
        if ytr.sum() == 0 or yte.sum() == 0:
            continue
        gb = GradientBoostingClassifier(n_estimators=150, max_depth=5,
                                        random_state=20260924).fit(train[cols], ytr)
        p = gb.predict_proba(test[cols])[:, 1]
        print(f"  horizon={h:4d}m  test pos={yte.mean() * 100:5.1f}%  "
              f"AUC={roc_auc_score(yte, p):.3f}  AP={average_precision_score(yte, p):.3f}")


def main() -> None:
    sensors, alarms = load()
    df = build(sensors, alarms, 60)
    q1_persistence(df)
    q2_nowcast(df)
    q3_drift(df)
    q4_horizon(sensors, alarms)


if __name__ == "__main__":
    main()
