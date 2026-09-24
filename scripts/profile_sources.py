"""Profile the downloaded CoMoPI and PIADE files before any Snowflake load.

Read-only. Writes a plain-text report to docs/cortex-audit/002-source-profile.md
so every claim about the data is traceable to a measurement, not an assumption.
"""

from pathlib import Path

import pandas as pd

RAW = Path("data/raw")
OUT = Path("docs/cortex-audit/002-source-profile.md")

lines: list[str] = []


def say(text: str = "") -> None:
    print(text)
    lines.append(text)


def profile_comopi_sensors() -> None:
    df = pd.read_csv(RAW / "comopi/industrial_dataset_sensors_10m_agg.csv", index_col=0)
    df["_time"] = pd.to_datetime(df["_time"], utc=True)
    sensor_cols = [c for c in df.columns if c not in ("_time", "_serial")]

    say("## CoMoPI sensors")
    say()
    say(f"rows={len(df)}  machines={df['_serial'].nunique()}  sensor_cols={len(sensor_cols)}")
    say(f"time range: {df['_time'].min()} .. {df['_time'].max()}")
    say(f"nulls total: {int(df.isna().sum().sum())}")
    say()
    say("per machine:")
    grp = df.groupby("_serial")["_time"].agg(["count", "min", "max"])
    for serial, row in grp.iterrows():
        say(f"  {serial}: rows={row['count']}  {row['min']} .. {row['max']}")
    say()
    say("value ranges per sensor (anonymised/rescaled, units unknown):")
    desc = df[sensor_cols].agg(["min", "max", "mean"]).T
    for col, row in desc.iterrows():
        nulls = int(df[col].isna().sum())
        say(f"  {col}: min={row['min']:.4f} max={row['max']:.4f} mean={row['mean']:.4f} nulls={nulls}")
    # Tolerance guards against float artefacts like 1.0000000000000002.
    outside = desc[(desc["min"] < -1e-9) | (desc["max"] > 1 + 1e-9)]
    say(f"  columns materially outside [0,1]: {list(outside.index) if len(outside) else 'none'}")
    say("  -> all sensors are rescaled into [0,1]; physical units are not recoverable")
    say()


def profile_comopi_alarms() -> None:
    df = pd.read_csv(RAW / "comopi/industrial_dataset_alarm_10m_agg.csv", index_col=0)
    df["_time"] = pd.to_datetime(df["_time"], utc=True)
    al_cols = [c for c in df.columns if c.startswith("AL_")]

    say("## CoMoPI alarms")
    say()
    say(f"rows={len(df)}  machines={df['_serial'].nunique()}  alarm_cols={len(al_cols)}")
    say(f"time range: {df['_time'].min()} .. {df['_time'].max()}")
    say()
    say("fault-target alarms (the published PdM labels):")
    for col in ("AL_53", "AL_54"):
        fired = (df[col] > 0).sum()
        total = int(df[col].sum())
        machines = df.loc[df[col] > 0, "_serial"].nunique()
        say(f"  {col}: windows_with_alarm={fired}  total_count={total}  machines_affected={machines}")
    say()
    say("AL_53/AL_54 windows per machine:")
    fault = df[(df["AL_53"] > 0) | (df["AL_54"] > 0)]
    if len(fault):
        for serial, n in fault["_serial"].value_counts().sort_index().items():
            say(f"  {serial}: {n}")
    say()
    say("top 10 most frequent alarms overall:")
    totals = df[al_cols].sum().sort_values(ascending=False).head(10)
    for col, val in totals.items():
        say(f"  {col}: {int(val)}")
    say()
    say("all 16 target-module alarms (candidate labels if AL_53/54 are too rare):")
    module = [
        "AL_17", "AL_18", "AL_40", "AL_41", "AL_42", "AL_43", "AL_45", "AL_46",
        "AL_47", "AL_48", "AL_49", "AL_50", "AL_51", "AL_52", "AL_53", "AL_54",
    ]
    for col in module:
        fired = int((df[col] > 0).sum())
        say(f"  {col}: windows={fired}  total={int(df[col].sum())}  machines={df.loc[df[col] > 0, '_serial'].nunique()}")
    say()
    _label_overlap(df)


def _label_overlap(alarms: pd.DataFrame) -> None:
    """Do the fault alarms happen on machines/times where we also have sensors?

    Without overlap there is nothing to learn from, no matter which model we pick.
    """
    sensors = pd.read_csv(RAW / "comopi/industrial_dataset_sensors_10m_agg.csv", index_col=0)
    sensors["_time"] = pd.to_datetime(sensors["_time"], utc=True)

    fault = alarms[(alarms["AL_53"] > 0) | (alarms["AL_54"] > 0)][["_serial", "_time"]]
    module_cols = ["AL_17", "AL_18", "AL_40", "AL_41", "AL_42", "AL_43", "AL_45", "AL_46",
                   "AL_47", "AL_48", "AL_49", "AL_50", "AL_51", "AL_52", "AL_53", "AL_54"]
    module = alarms[(alarms[module_cols] > 0).any(axis=1)][["_serial", "_time"]]

    say("sensor/label overlap (can a model actually be trained?):")
    for name, events in (("AL_53+AL_54", fault), ("any target-module alarm", module)):
        joined = events.merge(sensors[["_serial", "_time"]], on=["_serial", "_time"], how="inner")
        say(f"  {name}: {len(events)} alarm windows, {len(joined)} have a matching sensor row")
        if len(events):
            covered = events.merge(
                sensors.groupby("_serial")["_time"].agg(["min", "max"]).reset_index(),
                on="_serial", how="left",
            )
            in_window = covered[
                (covered["_time"] >= covered["min"]) & (covered["_time"] <= covered["max"])
            ]
            say(f"    within a machine's sensor coverage period: {len(in_window)}")
    say()


def profile_piade_raw() -> None:
    df = pd.read_csv(RAW / "piade/raw_data.csv")
    df["interval_start"] = pd.to_datetime(df["interval_start"], utc=True, format="ISO8601")

    say("## PIADE raw intervals")
    say()
    say(f"rows={len(df)}  machines={df['equipment_ID'].nunique()}")
    say(f"time range: {df['interval_start'].min()} .. {df['interval_start'].max()}")
    say()
    say("state mix (the Availability/Performance ingredients):")
    for state, n in df["type"].value_counts().items():
        say(f"  {state}: {n} intervals ({100 * n / len(df):.2f}%)")
    say()
    say("elapsed units check:")
    computed_ms = (df["end"] - df["start"]) * 1000
    ratio = (df["elapsed"] / computed_ms.replace(0, pd.NA)).dropna()
    say(f"  elapsed / ((end-start)*1000) median={ratio.median():.6f}")
    say("  -> ratio near 1.0 means 'elapsed' is milliseconds")
    say(f"  elapsed sum as hours: {df['elapsed'].sum() / 3_600_000:.1f}")
    say()
    say("pi/po counter check (cumulative vs per-interval):")
    for machine in sorted(df["equipment_ID"].unique()):
        sub = df[df["equipment_ID"] == machine].sort_values("start")
        dpo = sub["po"].diff().dropna()
        say(
            f"  {machine}: po first={int(sub['po'].iloc[0])} last={int(sub['po'].iloc[-1])} "
            f"monotonic={bool(sub['po'].is_monotonic_increasing)} "
            f"negative_diffs={int((dpo < 0).sum())} median_diff={dpo.median():.1f}"
        )
    say("  -> monotonic increasing with huge absolute values means cumulative counters;")
    say("     per-interval output must be derived by differencing.")
    say()
    say("alarm codes:")
    say(f"  distinct alarm values={df['alarm'].nunique()}")
    say(f"  most common: {df['alarm'].value_counts().head(5).to_dict()}")
    say(f"  nulls in alarm: {int(df['alarm'].isna().sum())}")
    say()
    say("speed column:")
    say(f"  min={df['speed'].min()} max={df['speed'].max()} median={df['speed'].median()}")
    say(f"  nonzero speed rows={int((df['speed'] > 0).sum())}")
    say()


def profile_piade_sequences() -> None:
    df = pd.read_csv(RAW / "piade/sequences_1h_data.csv")
    df["interval_start"] = pd.to_datetime(df["interval_start"])
    pct_cols = [c for c in df.columns if c.startswith("%")]

    say("## PIADE hourly sequences")
    say()
    say(f"rows={len(df)}  machines={df['equipment_ID'].nunique()}  columns={len(df.columns)}")
    say(f"time range: {df['interval_start'].min()} .. {df['interval_start'].max()}")
    say()
    say("state-fraction columns:")
    for col in pct_cols:
        say(f"  {col}: mean={df[col].mean():.4f} nulls={int(df[col].isna().sum())}")
    row_sums = df[pct_cols].sum(axis=1)
    say(f"  row sums: min={row_sums.min():.4f} max={row_sums.max():.4f} mean={row_sums.mean():.4f}")
    say("  -> sums near 1.0 confirm these are fractions of the hour")
    say()


def main() -> None:
    say("# Source profile — measured, not assumed")
    say()
    say("Generated by scripts/profile_sources.py against checksum-verified Zenodo files.")
    say()
    profile_comopi_sensors()
    profile_comopi_alarms()
    profile_piade_raw()
    profile_piade_sequences()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
