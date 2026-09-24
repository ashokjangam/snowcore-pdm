"""Where do the CoMoPI positives sit in time?

A chronological holdout is only honest if the test period actually contains
positives. With 455 sensor-matched positive windows in total, that is not a
given, and picking the cutoff before checking would be guessing. This script
measures it so the cutoff in sql/14_ml_comopi.sql can be justified.

Read-only. Touches the downloaded CSVs only.
"""

from __future__ import annotations

import pathlib

import pandas as pd

RAW = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw"
SENSORS = RAW / "comopi" / "industrial_dataset_sensors_10m_agg.csv"
ALARMS = RAW / "comopi" / "industrial_dataset_alarm_10m_agg.csv"

# The 16 alarms belonging to the module the publisher instrumented.
MODULE_ALARMS = [
    "AL_17", "AL_18", "AL_40", "AL_41", "AL_42", "AL_43", "AL_45", "AL_46",
    "AL_47", "AL_48", "AL_49", "AL_50", "AL_51", "AL_52", "AL_53", "AL_54",
]

# Horizon for the forward-looking label, in minutes.
HORIZON_MIN = 60


def main() -> None:
    sensors = pd.read_csv(SENSORS)
    alarms = pd.read_csv(ALARMS)

    for frame in (sensors, alarms):
        frame["_time"] = pd.to_datetime(frame["_time"], utc=True, format="ISO8601")

    alarms["module_hit"] = alarms[MODULE_ALARMS].sum(axis=1) > 0
    hits = alarms.loc[alarms["module_hit"], ["_serial", "_time"]]

    print(f"sensor rows: {len(sensors)}")
    print(f"module-alarm windows (alarm table): {len(hits)}")
    print()

    # Forward label: does a module alarm start within HORIZON_MIN after this
    # sensor window? Done per machine, because alarms never cross machines.
    labelled = []
    for serial, grp in sensors.groupby("_serial"):
        machine_hits = hits.loc[hits["_serial"] == serial, "_time"].sort_values()
        grp = grp.sort_values("_time").copy()
        if machine_hits.empty:
            grp["label_fwd"] = False
            grp["label_now"] = False
            labelled.append(grp)
            continue

        hit_arr = machine_hits.to_numpy()
        times = grp["_time"].to_numpy()
        horizon = pd.Timedelta(minutes=HORIZON_MIN).to_timedelta64()

        # searchsorted gives, for each sensor time, the first alarm at or after it.
        nxt = hit_arr.searchsorted(times, side="right")
        has_next = nxt < len(hit_arr)
        gap = pd.Series(
            [hit_arr[i] - t if ok else None for i, t, ok in zip(nxt, times, has_next)]
        )
        grp["label_fwd"] = [
            bool(ok and g is not None and g <= horizon)
            for ok, g in zip(has_next, gap)
        ]
        # Concurrent: an alarm in the same 10-minute window.
        same = hit_arr.searchsorted(times, side="left")
        grp["label_now"] = [
            bool(i < len(hit_arr) and hit_arr[i] == t) for i, t in zip(same, times)
        ]
        labelled.append(grp)

    df = pd.concat(labelled).sort_values("_time")
    print(f"forward-label positives (alarm within {HORIZON_MIN}m): "
          f"{int(df['label_fwd'].sum())} "
          f"({df['label_fwd'].mean() * 100:.2f}%)")
    print(f"concurrent-label positives: {int(df['label_now'].sum())} "
          f"({df['label_now'].mean() * 100:.2f}%)")
    print()

    print("forward positives per machine:")
    per = df.groupby("_serial").agg(
        rows=("label_fwd", "size"), pos=("label_fwd", "sum")
    )
    for serial, row in per.iterrows():
        print(f"  {serial}: rows={row['rows']} pos={row['pos']}")
    print()

    print("forward positives per month:")
    by_month = df.groupby(df["_time"].dt.to_period("M")).agg(
        rows=("label_fwd", "size"), pos=("label_fwd", "sum")
    )
    for month, row in by_month.iterrows():
        print(f"  {month}: rows={row['rows']} pos={row['pos']}")
    print()

    # Candidate chronological cutoffs: what does each leave in the test half?
    print("candidate chronological cutoffs (train < cutoff <= test):")
    for q in (0.70, 0.75, 0.80, 0.85):
        cutoff = df["_time"].quantile(q)
        test = df.loc[df["_time"] >= cutoff]
        train = df.loc[df["_time"] < cutoff]
        print(
            f"  q={q:.2f} cutoff={cutoff:%Y-%m-%d %H:%M}  "
            f"train rows={len(train)} pos={int(train['label_fwd'].sum())}  |  "
            f"test rows={len(test)} pos={int(test['label_fwd'].sum())}"
        )
    print()

    # Event-level view: consecutive positive windows collapse into one event.
    # A model that flags one window of a five-window event has caught the event.
    events = 0
    for _, grp in df.groupby("_serial"):
        flags = grp.sort_values("_time")["label_fwd"].to_numpy()
        events += int(((flags) & (~pd.Series(flags).shift(1, fill_value=False))).sum())
    print(f"distinct forward-label events (consecutive windows merged): {events}")

    # Sampling regularity: rolling windows are meaningless if rows are far apart.
    gaps = df.groupby("_serial")["_time"].diff().dt.total_seconds().dropna()
    print()
    print("gap between consecutive sensor rows, seconds:")
    print(f"  median={gaps.median():.0f} p90={gaps.quantile(0.9):.0f} "
          f"max={gaps.max():.0f}")
    print(f"  share of gaps > 1 hour: {(gaps > 3600).mean() * 100:.1f}%")


if __name__ == "__main__":
    main()
