"""How many Plant A machines can actually be given a health baseline?

The first build used "the machine's first 14 days" and silently produced a
baseline for only 5 of 8 machines, leaving 1,684 of 15,704 windows unscored.
Sampling is irregular, so a fixed time window gives different sample counts on
different machines. This measures the alternative — the machine's first N
windows — so the choice is made on numbers rather than intuition.
"""

from __future__ import annotations

import pathlib

import pandas as pd

CSV = (
    pathlib.Path(__file__).resolve().parents[1]
    / "data" / "raw" / "comopi" / "industrial_dataset_sensors_10m_agg.csv"
)
MIN_SAMPLES = 50


def main() -> None:
    d = pd.read_csv(CSV)
    d["_time"] = pd.to_datetime(d["_time"], utc=True, format="ISO8601")

    header = f"{'machine':8s} {'rows':>6s} {'in_14d':>7s} {'span_d':>7s} {'14d_ok':>7s} {'200_ok':>7s}"
    print(header)
    print("-" * len(header))

    total = kept_14d = kept_200 = 0
    for serial, g in d.groupby("_serial"):
        g = g.sort_values("_time")
        in_14d = int((g["_time"] < g["_time"].min() + pd.Timedelta(days=14)).sum())
        span = (g["_time"].max() - g["_time"].min()).days
        ok_14d = in_14d >= MIN_SAMPLES
        # Under a count-based rule the baseline is the first 200 windows, so a
        # machine qualifies whenever it has at least MIN_SAMPLES windows at all.
        ok_200 = len(g) >= MIN_SAMPLES
        print(f"{serial:8s} {len(g):6d} {in_14d:7d} {span:7d} "
              f"{str(ok_14d):>7s} {str(ok_200):>7s}")
        total += len(g)
        kept_14d += len(g) if ok_14d else 0
        kept_200 += len(g) if ok_200 else 0

    print()
    print(f"windows total                      {total}")
    print(f"scored under the 14-day rule       {kept_14d} ({kept_14d / total * 100:.1f}%)")
    print(f"scored under a first-200 rule      {kept_200} ({kept_200 / total * 100:.1f}%)")


if __name__ == "__main__":
    main()
