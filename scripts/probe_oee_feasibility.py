"""Test whether PIADE can support a genuine Availability x Performance x Quality.

Availability and Performance look derivable from the published state and speed
columns. Quality is the doubtful one: pi and po are cumulative counters, and the
profiling run found counter resets on three machines. This checks whether
differencing them survives those resets well enough to mean anything.

Read-only. Prints findings; makes no claim the data cannot support.
"""

import pandas as pd

RAW = "data/raw/piade/raw_data.csv"

RUNNING = {"production", "performance_loss"}
PLANNED_OUT = {"scheduled_downtime"}

df = pd.read_csv(RAW)
df["interval_start"] = pd.to_datetime(df["interval_start"], utc=True, format="ISO8601")
df = df.sort_values(["equipment_ID", "start"]).reset_index(drop=True)

print("=== per-machine counter behaviour ===")
frames = []
for machine, sub in df.groupby("equipment_ID"):
    sub = sub.copy()
    sub["d_pi"] = sub["pi"].diff()
    sub["d_po"] = sub["po"].diff()
    resets = ((sub["d_pi"] < 0) | (sub["d_po"] < 0)).sum()
    # A reset makes that one delta meaningless; drop it, keep the rest.
    sub.loc[(sub["d_pi"] < 0) | (sub["d_po"] < 0), ["d_pi", "d_po"]] = pd.NA
    usable = sub["d_pi"].notna().sum()
    print(
        f"{machine}: intervals={len(sub)} resets={resets} "
        f"usable_deltas={usable} ({100 * usable / len(sub):.1f}%)"
    )
    frames.append(sub)

df = pd.concat(frames, ignore_index=True)

print("\n=== Quality candidate: output packages / input packages ===")
prod = df[df["type"].isin(RUNNING)].copy()
prod = prod[(prod["d_pi"] > 0)]
prod["yield_ratio"] = prod["d_po"] / prod["d_pi"]
print(f"running intervals with positive input delta: {len(prod)}")
print(prod["yield_ratio"].describe(percentiles=[0.01, 0.25, 0.5, 0.75, 0.99]))
print(f"ratio <= 1.0 share: {100 * (prod['yield_ratio'] <= 1.0).mean():.2f}%")
print(f"ratio  > 1.0 share: {100 * (prod['yield_ratio'] > 1.0).mean():.2f}%")
print("  -> ratios above 1.0 mean po and pi are not a clean in/out pair per interval")

print("\n=== aggregate quality by machine (sum of deltas, not mean of ratios) ===")
agg = prod.groupby("equipment_ID")[["d_pi", "d_po"]].sum()
agg["yield_pct"] = 100 * agg["d_po"] / agg["d_pi"]
print(agg)

print("\n=== Availability / Performance ingredients (hourly) ===")
df["hour"] = df["interval_start"].dt.floor("h")
df["dur_s"] = df["elapsed"] / 1000.0
df["is_running"] = df["type"].isin(RUNNING)
df["is_planned_out"] = df["type"].isin(PLANNED_OUT)
df["speed_time"] = df["speed"] * df["dur_s"]

hourly = df.groupby(["equipment_ID", "hour"]).apply(
    lambda g: pd.Series(
        {
            "total_s": g["dur_s"].sum(),
            "run_s": g.loc[g["is_running"], "dur_s"].sum(),
            "planned_out_s": g.loc[g["is_planned_out"], "dur_s"].sum(),
            "speed_time": g.loc[g["is_running"], "speed_time"].sum(),
        }
    ),
    include_groups=False,
).reset_index()

hourly["planned_s"] = hourly["total_s"] - hourly["planned_out_s"]
hourly = hourly[hourly["planned_s"] > 0]
hourly["availability"] = hourly["run_s"] / hourly["planned_s"]
ideal = df.loc[df["is_running"], "speed"].max()
hourly["performance"] = hourly["speed_time"] / (hourly["run_s"] * ideal)

print(f"hourly buckets with planned time: {len(hourly)}")
print(f"ideal rate (max observed speed while running): {ideal} packages/hour")
print(hourly[["availability", "performance"]].describe(percentiles=[0.05, 0.5, 0.95]))
print(f"availability > 1.0 rows: {int((hourly['availability'] > 1.0000001).sum())}")
print(f"performance  > 1.0 rows: {int((hourly['performance'] > 1.0000001).sum())}")
