"""Is Plant B's biggest 'undiagnosed' loss actually idle time?

The Pareto reported UNDIAGNOSED at 50,149 stops and 10,266 hours, which is
exactly the number of intervals the profile counted in the 'idle' state. If
alarm codes attach only to 'downtime' and never to 'idle', then labelling
those hours UNDIAGNOSED is wrong and misleading: the line was not broken with
an unrecorded cause, it was sitting waiting, which is a completely different
management problem.

That would also reframe the synthetic cost finding. 3,592 of the 4,061 long
stops carry no alarm, and if those are idle rather than breakdowns then the
largest attributed cost on Plant B is waiting, not failure.

Verify rather than infer.
"""

from __future__ import annotations

import pathlib

import pandas as pd

CSV = (
    pathlib.Path(__file__).resolve().parents[1]
    / "data" / "raw" / "piade" / "raw_data.csv"
)


def main() -> None:
    df = pd.read_csv(CSV)
    df["dur_min"] = df["elapsed"] / 60000.0
    df["no_alarm"] = df["alarm"] == "A_000"

    print("alarm presence by state — does A_000 track one state exactly?")
    print(f"{'state':22s} {'intervals':>10s} {'no_alarm':>10s} {'pct_no_alarm':>13s} {'hours':>10s}")
    for state, g in df.groupby("type"):
        print(f"{state:22s} {len(g):>10,d} {int(g['no_alarm'].sum()):>10,d} "
              f"{g['no_alarm'].mean() * 100:>12.1f}% {g['dur_min'].sum() / 60:>10,.0f}")
    print()

    unplanned = df[df["type"].isin(["downtime", "idle"])]
    print("within unplanned stops only:")
    print(f"  intervals            {len(unplanned):,}")
    print(f"  with no alarm        {int(unplanned['no_alarm'].sum()):,}")
    print(f"  idle intervals       {int((unplanned['type'] == 'idle').sum()):,}")
    print()

    # The claim to test: no-alarm and idle are the same set.
    same = (unplanned["no_alarm"] == (unplanned["type"] == "idle")).all()
    print(f"  'no alarm' is exactly 'idle': {same}")
    if not same:
        cross = pd.crosstab(unplanned["type"], unplanned["no_alarm"])
        print("  cross-tab of state against no-alarm:")
        print(cross.to_string())
    print()

    # And the part that matters for cost: the long stops.
    long_stops = unplanned[unplanned["dur_min"] >= 30]
    print(f"long stops (>= 30 min), the ones that become work orders: {len(long_stops):,}")
    for state, g in long_stops.groupby("type"):
        print(f"  {state:20s} {len(g):>6,d} stops, {g['dur_min'].sum() / 60:>8,.0f} hours, "
              f"no_alarm {int(g['no_alarm'].sum()):>6,d}")
    print()
    print("So the largest block of attributed cost is:")
    top = long_stops.groupby("type")["dur_min"].sum().idxmax()
    share = (
        long_stops.groupby("type")["dur_min"].sum().max()
        / long_stops["dur_min"].sum() * 100
    )
    print(f"  state '{top}', holding {share:.1f}% of all long-stop time")
    print()

    # A maintenance work order belongs to a breakdown, not to a line that is
    # waiting. So the threshold has to be re-chosen against 'downtime' alone,
    # where the durations are much shorter than across all unplanned stops.
    print("=" * 70)
    print("BREAKDOWNS ONLY ('downtime' state) — choosing a work-order threshold")
    print("=" * 70)
    dt = df[df["type"] == "downtime"]
    print(f"intervals {len(dt):,}, total {dt['dur_min'].sum() / 60:,.0f} hours, "
          f"median {dt['dur_min'].median():.2f} min")
    for q in (0.75, 0.9, 0.95, 0.99):
        print(f"  p{int(q * 100)} {dt['dur_min'].quantile(q):.2f} min")
    print()
    span_days = (
        pd.to_datetime(df["interval_start"], format="ISO8601").max()
        - pd.to_datetime(df["interval_start"], format="ISO8601").min()
    ).days
    machines = df["equipment_ID"].nunique()
    total = dt["dur_min"].sum()
    print(f"  {'min_dur':>8s} {'orders':>8s} {'per_machine_per_day':>20s} {'share_of_breakdown_time':>24s}")
    for thr in (2, 5, 10, 15, 30):
        sel = dt[dt["dur_min"] >= thr]
        print(f"  {thr:>8d} {len(sel):>8,d} "
              f"{len(sel) / max(span_days, 1) / machines:>20.2f} "
              f"{sel['dur_min'].sum() / total * 100:>23.1f}%")
    print()
    print("  idle periods >= 30 min, which become production-loss incidents "
          "rather than work orders:")
    idle_long = df[(df["type"] == "idle") & (df["dur_min"] >= 30)]
    print(f"    {len(idle_long):,} incidents, {idle_long['dur_min'].sum() / 60:,.0f} hours, "
          f"median {idle_long['dur_min'].median():.0f} min")


if __name__ == "__main__":
    main()
