"""What should a synthetic work order actually be attached to?

The IT layer must be generated from each plant's own OT events and nothing
else. That only works if the event thresholds are chosen from the real
distributions rather than invented, so this measures them.

Two questions:

  Plant B  Unplanned stops number in the hundreds of thousands and average a
           few minutes. Raising a work order for a 3-minute micro-stop would
           be fiction. Where is the natural cut, and how many orders does each
           candidate threshold produce?

  Plant A  Module alarms arrive as 10-minute windows. Consecutive windows are
           one incident, not several. How many incidents are there once runs
           are merged, and how long do they last?

Read-only.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

RAW = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw"

MODULE_ALARMS = [
    "AL_17", "AL_18", "AL_40", "AL_41", "AL_42", "AL_43", "AL_45", "AL_46",
    "AL_47", "AL_48", "AL_49", "AL_50", "AL_51", "AL_52", "AL_53", "AL_54",
]


def plant_b() -> None:
    print("=" * 74)
    print("PLANT B — unplanned stops, and what each work-order threshold costs")
    print("=" * 74)
    df = pd.read_csv(RAW / "piade" / "raw_data.csv")
    df["dur_min"] = df["elapsed"] / 60000.0
    # The published column is 'type'; Bronze renames it to STATE_TYPE.
    stops = df[df["type"].isin(["downtime", "idle"])]

    print(f"unplanned stop intervals : {len(stops):,}")
    print(f"total stop time (hours)  : {stops['dur_min'].sum() / 60:,.0f}")
    print(f"mean duration (min)      : {stops['dur_min'].mean():.2f}")
    print(f"median duration (min)    : {stops['dur_min'].median():.2f}")
    for q in (0.5, 0.75, 0.9, 0.95, 0.99):
        print(f"  p{int(q * 100):<3d} duration (min)     : {stops['dur_min'].quantile(q):.2f}")
    print(f"max duration (min)       : {stops['dur_min'].max():,.1f}")
    print()

    print("candidate work-order thresholds:")
    print(f"  {'min_dur':>8s} {'orders':>9s} {'per_machine_per_day':>20s} "
          f"{'share_of_stop_time':>19s}")
    total_time = stops["dur_min"].sum()
    span_days = (
        pd.to_datetime(df["interval_start"], format="ISO8601").max()
        - pd.to_datetime(df["interval_start"], format="ISO8601").min()
    ).days
    machines = df["equipment_ID"].nunique()
    for thr in (5, 10, 15, 30, 60, 120):
        sel = stops[stops["dur_min"] >= thr]
        per_md = len(sel) / max(span_days, 1) / machines
        share = sel["dur_min"].sum() / total_time * 100
        print(f"  {thr:>8d} {len(sel):>9,d} {per_md:>20.2f} {share:>18.1f}%")
    print()
    print(f"  (span {span_days} days, {machines} machines)")
    print()

    print("alarm attached to stops at the 30-minute threshold, top 10:")
    sel = stops[stops["dur_min"] >= 30]
    top = sel["alarm"].value_counts().head(10)
    for code, n in top.items():
        mins = sel.loc[sel["alarm"] == code, "dur_min"].sum()
        print(f"  {code}: {n:,} stops, {mins / 60:,.0f} hours, "
              f"median {sel.loc[sel['alarm'] == code, 'dur_min'].median():.1f} min")
    print()


def plant_a() -> None:
    print("=" * 74)
    print("PLANT A — module-alarm incidents once consecutive windows are merged")
    print("=" * 74)
    al = pd.read_csv(RAW / "comopi" / "industrial_dataset_alarm_10m_agg.csv")
    al["_time"] = pd.to_datetime(al["_time"], utc=True, format="ISO8601")
    al["module_count"] = al[MODULE_ALARMS].sum(axis=1)
    hits = al[al["module_count"] > 0].sort_values(["_serial", "_time"])

    print(f"module-alarm windows : {len(hits):,}")

    incidents = []
    for serial, g in hits.groupby("_serial"):
        g = g.sort_values("_time")
        gap = g["_time"].diff().dt.total_seconds().fillna(1e9)
        # More than 30 minutes of quiet ends an incident. Below that the
        # windows are treated as the same event still running.
        new = gap > 1800
        g = g.assign(incident=new.cumsum())
        for inc, sub in g.groupby("incident"):
            incidents.append({
                "machine": serial,
                "start": sub["_time"].min(),
                "end": sub["_time"].max(),
                "windows": len(sub),
                "alarm_count": sub["module_count"].sum(),
                "dominant": sub[MODULE_ALARMS].sum().idxmax(),
            })

    inc = pd.DataFrame(incidents)
    inc["span_min"] = (
        (inc["end"] - inc["start"]).dt.total_seconds() / 60 + 10
    )
    print(f"merged incidents     : {len(inc):,}")
    print(f"windows per incident : median {inc['windows'].median():.0f}, "
          f"mean {inc['windows'].mean():.2f}, max {inc['windows'].max()}")
    print(f"incident span (min)  : median {inc['span_min'].median():.0f}, "
          f"p90 {inc['span_min'].quantile(0.9):.0f}, "
          f"max {inc['span_min'].max():.0f}")
    print()
    print("incidents per machine:")
    for m, n in inc["machine"].value_counts().items():
        print(f"  {m}: {n}")
    print()
    print("dominant alarm across incidents:")
    for code, n in inc["dominant"].value_counts().head(10).items():
        print(f"  {code}: {n}")
    print()


if __name__ == "__main__":
    plant_b()
    plant_a()
