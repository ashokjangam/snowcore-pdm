"""Can Plant B (PIADE) support a predictive model, before any SQL is written?

Plant A failed: its anonymised sensor channels do not predict its alarms. The
lesson is to measure predictability first rather than build a pipeline and
discover the answer at the end.

Plant B is a different shape of data. The hourly file carries 133 alarm-code
counts, five state fractions, 25 state-transition counts and a package count,
for 5 machines across two years. None of it is anonymised beyond the codes
themselves, and it describes what the line was doing rather than a rescaled
physical reading.

Four label candidates are tested, all strictly forward-looking:

  STOP_NEXT_1H      any unplanned downtime in the next hour
  HEAVY_STOP_1H     more than 10% of the next hour lost to unplanned downtime
  STOP_NEXT_4H      any unplanned downtime in the next four hours
  OEE_DROP_1H       next hour's run fraction falls below this machine's
                    own 25th percentile

Each is compared against two baselines that need no model:
  - the base rate (always predict positive)
  - persistence (this hour's downtime predicts next hour's)

A model that cannot beat persistence is not worth deploying, however good its
AUC looks.

Read-only. Nothing here touches Snowflake.
"""

from __future__ import annotations

import pathlib
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

warnings.filterwarnings("ignore")

HOURLY = (
    pathlib.Path(__file__).resolve().parents[1]
    / "data" / "raw" / "piade" / "sequences_1h_data.csv"
)

STATE_COLS = [
    "%idle", "%production", "%downtime", "%performance_loss",
    "%scheduled_downtime",
]
# Fraction of the hour the machine was actually making product.
RUN_COLS = ["%production", "%performance_loss"]

# Train on everything before this, hold out everything after. Roughly 80/20
# of a 2020-01-01 to 2022-01-01 range.
CUTOFF = pd.Timestamp("2021-08-01")


def load() -> pd.DataFrame:
    df = pd.read_csv(HOURLY)
    df["interval_start"] = pd.to_datetime(df["interval_start"], format="ISO8601")
    return df.sort_values(["equipment_ID", "interval_start"]).reset_index(drop=True)


def engineer(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Rolling history plus forward labels, computed strictly per machine."""
    alarm_cols = [c for c in df.columns if c.startswith("A_")]
    trans_cols = [c for c in df.columns if "/" in c]

    out = []
    for _, grp in df.groupby("equipment_ID"):
        g = grp.sort_values("interval_start").copy()
        g["run_frac"] = g[RUN_COLS].sum(axis=1)
        g["alarm_total"] = g[alarm_cols].sum(axis=1)
        g["alarm_distinct"] = (g[alarm_cols] > 0).sum(axis=1)

        # History. Everything here is the past or the present, never the future.
        for w in (3, 12, 24):
            g[f"downtime_m{w}"] = g["%downtime"].rolling(w, min_periods=1).mean()
            g[f"run_m{w}"] = g["run_frac"].rolling(w, min_periods=1).mean()
            g[f"alarm_m{w}"] = g["alarm_total"].rolling(w, min_periods=1).mean()
            g[f"changes_m{w}"] = g["#changes"].rolling(w, min_periods=1).mean()
            g[f"count_m{w}"] = g["count_sum"].rolling(w, min_periods=1).mean()
        g["downtime_s24"] = g["%downtime"].rolling(24, min_periods=1).std().fillna(0)
        g["run_trend"] = g["run_m3"] - g["run_m24"]
        g["hours_since_downtime"] = (
            g.groupby((g["%downtime"] > 0).cumsum()).cumcount()
        )
        g["gap_hours"] = (
            g["interval_start"].diff().dt.total_seconds().div(3600).fillna(-1)
        )

        # Forward labels. shift(-n) looks ahead, which is the point.
        nxt_dt = g["%downtime"].shift(-1)
        g["STOP_NEXT_1H"] = (nxt_dt > 0).astype(int)
        g["HEAVY_STOP_1H"] = (nxt_dt > 0.10).astype(int)
        g["STOP_NEXT_4H"] = (
            g["%downtime"].shift(-1).rolling(4, min_periods=1).max()
            .shift(-3).fillna(0) > 0
        ).astype(int)
        q25 = g["run_frac"].quantile(0.25)
        g["OEE_DROP_1H"] = (g["run_frac"].shift(-1) < q25).astype(int)

        # Harsher and longer-range variants. STOP_NEXT_1H turned out to be
        # degenerate because nearly every hour has some downtime, so the
        # useful question is not "any stop" but "a bad hour".
        g["SEVERE_STOP_1H"] = (nxt_dt > 0.30).astype(int)
        fwd4 = (
            g["%downtime"].shift(-1).rolling(4, min_periods=1).max().shift(-3)
        )
        g["HEAVY_STOP_4H"] = (fwd4 > 0.10).astype(int)
        g["SEVERE_STOP_4H"] = (fwd4 > 0.30).astype(int)
        # A specific frequent stop cause rather than downtime in aggregate.
        for code in ("A_065", "A_101", "A_005"):
            if code in g.columns:
                g[f"NEXT_{code}"] = (g[code].shift(-1) > 0).astype(int)

        # The persistence baseline: this hour's downtime, used as a prediction.
        g["persistence_score"] = g["%downtime"]

        g = g.iloc[:-4]  # last rows have incomplete forward windows
        out.append(g)

    full = pd.concat(out).reset_index(drop=True)

    feat = (
        STATE_COLS
        + ["#changes", "count_sum", "run_frac", "alarm_total", "alarm_distinct",
           "downtime_s24", "run_trend", "hours_since_downtime", "gap_hours"]
        + [c for c in full.columns if c.split("_m")[-1] in ("3", "12", "24")
           and any(c.startswith(p) for p in
                   ("downtime_m", "run_m", "alarm_m", "changes_m", "count_m"))]
        + trans_cols
        + alarm_cols
    )
    feat = [c for c in dict.fromkeys(feat) if c in full.columns]
    full[feat] = full[feat].fillna(0)
    return full, feat


def evaluate(full: pd.DataFrame, feat: list[str], target: str,
             baseline_col: str = "persistence_score") -> None:
    """Score a label against the right do-nothing baseline.

    The baseline matters more than the model. For downtime labels the honest
    comparison is this hour's downtime. For "will alarm X fire next hour" it
    is whether alarm X fired THIS hour — comparing that against downtime
    instead would manufacture a large apparent lift out of pure alarm
    autocorrelation.
    """
    train = full[full["interval_start"] < CUTOFF]
    test = full[full["interval_start"] >= CUTOFF]
    ytr, yte = train[target], test[target]

    if ytr.sum() == 0 or yte.sum() == 0 or yte.nunique() < 2:
        print(f"{target:16s} skipped (degenerate label)")
        return

    gb = GradientBoostingClassifier(
        n_estimators=250, max_depth=5, learning_rate=0.08, subsample=0.8,
        random_state=20260924,
    ).fit(train[feat], ytr)
    p = gb.predict_proba(test[feat])[:, 1]

    base = yte.mean()
    auc = roc_auc_score(yte, p)
    ap = average_precision_score(yte, p)
    pers_auc = roc_auc_score(yte, test[baseline_col])
    pers_ap = average_precision_score(yte, test[baseline_col])

    # Precision and recall at the threshold that flags the top 10% of hours,
    # which is roughly what a maintenance team could actually act on.
    cut = np.quantile(p, 0.90)
    flagged = p >= cut
    prec = yte[flagged].mean() if flagged.sum() else 0.0
    rec = yte[flagged].sum() / yte.sum()

    # The same top-decile rule applied to the baseline, so the two are
    # compared on identical terms.
    bcut = np.quantile(test[baseline_col], 0.90)
    bflag = test[baseline_col] >= bcut
    bprec = yte[bflag].mean() if bflag.sum() else 0.0

    print(f"{target:16s} base={base * 100:5.1f}%  "
          f"model AUC={auc:.3f} AP={ap:.3f}  |  "
          f"baseline[{baseline_col}] AUC={pers_auc:.3f} AP={pers_ap:.3f}")
    print(f"{'':16s} top-10% flagged: model precision={prec * 100:5.1f}% "
          f"recall={rec * 100:5.1f}% (lift {prec / base:.2f}x)  vs  "
          f"baseline precision={bprec * 100:5.1f}% (lift {bprec / base:.2f}x)")

    imp = sorted(zip(feat, gb.feature_importances_), key=lambda kv: -kv[1])[:8]
    print(f"{'':16s} top features: "
          + ", ".join(f"{n}({v:.3f})" for n, v in imp))
    print()


def main() -> None:
    df = load()
    full, feat = engineer(df)

    train = full[full["interval_start"] < CUTOFF]
    test = full[full["interval_start"] >= CUTOFF]
    print(f"rows={len(full)}  features={len(feat)}  machines={full['equipment_ID'].nunique()}")
    print(f"train={len(train)} ({train['interval_start'].min():%Y-%m-%d} .. "
          f"{train['interval_start'].max():%Y-%m-%d})")
    print(f"test ={len(test)} ({test['interval_start'].min():%Y-%m-%d} .. "
          f"{test['interval_start'].max():%Y-%m-%d})")
    print()

    print("rows per machine, train / test:")
    for eq in sorted(full["equipment_ID"].unique()):
        tr = (train["equipment_ID"] == eq).sum()
        te = (test["equipment_ID"] == eq).sum()
        print(f"  {eq}: {tr:6d} / {te:5d}")
    print()

    print("=" * 78)
    print("PREDICTABILITY — model must beat BOTH the base rate and persistence")
    print("=" * 78)
    for target in ("HEAVY_STOP_1H", "SEVERE_STOP_1H", "HEAVY_STOP_4H",
                   "SEVERE_STOP_4H", "OEE_DROP_1H"):
        if target in full.columns:
            evaluate(full, feat, target)

    # For alarm labels the baseline is that same alarm in the current hour.
    print("-" * 78)
    print("alarm labels, scored against 'the same alarm fired this hour'")
    print("-" * 78)
    for code in ("A_065", "A_101", "A_005"):
        target = f"NEXT_{code}"
        if target in full.columns:
            evaluate(full, feat, target, baseline_col=code)

    # And the same labels with the current-hour alarm counts removed, which
    # answers whether anything other than autocorrelation is doing the work.
    print("-" * 78)
    print("alarm labels again, with ALL current-hour alarm counts removed")
    print("-" * 78)
    no_alarm_feat = [c for c in feat if not c.startswith("A_")]
    for code in ("A_065", "A_101", "A_005"):
        target = f"NEXT_{code}"
        if target in full.columns:
            evaluate(full, no_alarm_feat, target, baseline_col=code)

    # Per-machine, on the best label so far. A fleet-level number can hide a
    # model that only works on the machine with the most rows.
    print("=" * 78)
    print("HEAVY_STOP_1H per machine — does it hold up everywhere?")
    print("=" * 78)
    for eq in sorted(full["equipment_ID"].unique()):
        sub = full[full["equipment_ID"] == eq]
        tr, te = sub[sub["interval_start"] < CUTOFF], sub[sub["interval_start"] >= CUTOFF]
        if tr["HEAVY_STOP_1H"].nunique() < 2 or te["HEAVY_STOP_1H"].nunique() < 2:
            print(f"  {eq}: degenerate")
            continue
        m = GradientBoostingClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.08,
            random_state=20260924,
        ).fit(tr[feat], tr["HEAVY_STOP_1H"])
        p = m.predict_proba(te[feat])[:, 1]
        print(f"  {eq}: n={len(te):5d} base={te['HEAVY_STOP_1H'].mean() * 100:5.1f}% "
              f"AUC={roc_auc_score(te['HEAVY_STOP_1H'], p):.3f} "
              f"AP={average_precision_score(te['HEAVY_STOP_1H'], p):.3f}")
    print()

    # Same drift probe that exposed the Plant A problem.
    probe = pd.concat([train.assign(_t=0), test.assign(_t=1)])
    half = probe.sample(frac=0.5, random_state=20260924)
    rest = probe.drop(half.index)
    gb = GradientBoostingClassifier(
        n_estimators=100, max_depth=4, random_state=20260924
    ).fit(half[feat], half["_t"])
    auc = roc_auc_score(rest["_t"], gb.predict_proba(rest[feat])[:, 1])
    print("=" * 78)
    print(f"adversarial train-vs-test AUC: {auc:.3f}")
    print("  Plant A scored 0.944 here, meaning its two periods barely overlapped.")


if __name__ == "__main__":
    main()
