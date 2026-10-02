"""Cycle-by-cycle compressor physics from raw MetroPT telemetry.

Each run of constant COMP state is one segment. COMP == 0 is loaded (compressing),
COMP == 1 is idle (the reservoir drains through consumers and any leak).

Per segment: duration, TP3 at start and end, pressure rate, mean motor current and
oil-temperature change. The idle decay floor, the slowest idle decay seen in a
window, approximates a leak-down test: when consumers draw little air, what remains
is leakage. Output: one segment table and one 5-minute feature frame per unit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ingest_metropt import normalise_name  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
CYCLES = PROCESSED / "cycles"
EXTERNAL = ROOT / "data" / "raw" / "external"
COLUMNS = ("timestamp", "tp3", "comp", "motor_current", "oil_temperature")
SOURCES = {
    "METROPT3_UCI_791": None,
    "METROPT_2022_ZENODO_6854240": EXTERNAL / "metropt2022_train.csv",
    "METROPT2_ZENODO_7766691": EXTERNAL / "MetroPT2.csv",
}
MAX_GAP_SECONDS = 60
MIN_SEGMENT_MINUTES = 0.5
WINDOWS_HOURS = (1, 6, 24)


def read_raw(unit: str) -> pd.DataFrame:
    path = SOURCES[unit]
    if path is None:
        return pd.read_parquet(PROCESSED / "telemetry.parquet", columns=list(COLUMNS))
    header = pd.read_csv(path, nrows=0).columns
    mapping = {column: normalise_name(column) for column in header}
    keep = [column for column, name in mapping.items() if name in COLUMNS]
    pieces = []
    for chunk in pd.read_csv(path, usecols=keep, chunksize=2_000_000, low_memory=False):
        chunk = chunk.rename(columns=mapping)
        chunk["timestamp"] = pd.to_datetime(chunk["timestamp"], errors="coerce")
        for column in COLUMNS[1:]:
            chunk[column] = pd.to_numeric(chunk[column], errors="coerce").astype("float32")
        pieces.append(chunk.dropna(subset=["timestamp"]))
    return pd.concat(pieces).sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)


def segments(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.dropna(subset=["tp3", "comp"]).sort_values("timestamp").reset_index(drop=True)
    state = (raw["comp"].to_numpy() >= 0.5).astype(np.int8)
    gap = raw["timestamp"].diff().dt.total_seconds().fillna(np.inf).to_numpy() > MAX_GAP_SECONDS
    breaks = gap | np.r_[True, state[1:] != state[:-1]]
    seg_id = np.cumsum(breaks)
    grouped = raw.assign(seg=seg_id, idle=state).groupby("seg", sort=True)
    table = grouped.agg(
        start=("timestamp", "first"),
        end=("timestamp", "last"),
        idle=("idle", "first"),
        p_start=("tp3", "first"),
        p_end=("tp3", "last"),
        current=("motor_current", "mean"),
        oil_start=("oil_temperature", "first"),
        oil_end=("oil_temperature", "last"),
        samples=("tp3", "size"),
    ).reset_index(drop=True)
    table["minutes"] = (table["end"] - table["start"]).dt.total_seconds() / 60
    table = table[table["minutes"] >= MIN_SEGMENT_MINUTES].reset_index(drop=True)
    table["rate"] = (table["p_end"] - table["p_start"]) / table["minutes"]
    table["oil_rise"] = table["oil_end"] - table["oil_start"]
    return table


def inject_leak(table: pd.DataFrame, delta: np.ndarray) -> pd.DataFrame:
    """Add a leak of delta bar/min per segment, holding the pressure band fixed.

    Idle decay speeds up by delta, loaded rise slows by delta. With the band fixed, idle
    segments shorten and loaded segments lengthen in proportion. A loaded segment whose
    rise would fall to zero or below is held at a stalled 0.001 bar/min.
    """
    out = table.copy()
    idle = out["idle"].to_numpy() == 1
    rate = out["rate"].to_numpy(dtype=float)
    minutes = out["minutes"].to_numpy(dtype=float)
    new_rate = np.where(idle, rate - delta, np.maximum(rate - delta, 1e-3))
    span = np.abs(rate * minutes)
    new_minutes = np.where(np.abs(new_rate) > 1e-9, span / np.abs(new_rate), minutes)
    new_minutes = np.where(span < 1e-6, minutes, new_minutes)
    out["rate"] = new_rate
    out["minutes"] = new_minutes
    return out


def bin_features(table: pd.DataFrame, grid: pd.DatetimeIndex) -> pd.DataFrame:
    """Trailing-window cycle physics on a 5-minute grid, using segments ended by each bin."""
    idle = table[table["idle"] == 1].set_index("end").sort_index()
    loaded = table[table["idle"] == 0].set_index("end").sort_index()
    frame = pd.DataFrame(index=grid)
    decay = (-idle["rate"]).clip(lower=0)
    rise = loaded["rate"]
    for hours in WINDOWS_HOURS:
        window = f"{hours}h"
        frame[f"decay_floor_{hours}h"] = decay.rolling(window).quantile(0.10).reindex(grid, method="ffill")
        frame[f"decay_median_{hours}h"] = decay.rolling(window).median().reindex(grid, method="ffill")
        frame[f"rise_median_{hours}h"] = rise.rolling(window).median().reindex(grid, method="ffill")
        frame[f"loaded_minutes_median_{hours}h"] = loaded["minutes"].rolling(window).median().reindex(grid, method="ffill")
        frame[f"idle_minutes_median_{hours}h"] = idle["minutes"].rolling(window).median().reindex(grid, method="ffill")
        frame[f"cycles_{hours}h"] = loaded["minutes"].rolling(window).count().reindex(grid, method="ffill")
        frame[f"current_loaded_{hours}h"] = loaded["current"].rolling(window).median().reindex(grid, method="ffill")
        frame[f"oil_rise_loaded_{hours}h"] = loaded["oil_rise"].rolling(window).median().reindex(grid, method="ffill")
    last_end = pd.Series(table["end"].to_numpy(), index=table["end"]).sort_index()
    staleness = (grid - pd.DatetimeIndex(last_end.reindex(grid, method="ffill").to_numpy())).total_seconds() / 60
    frame["minutes_since_segment"] = np.asarray(staleness, dtype=float)
    return frame.reset_index().rename(columns={"index": "timestamp"})


def unit_grid(unit: str) -> pd.DatetimeIndex:
    stamps = pd.read_parquet(PROCESSED / "units" / f"{unit}.parquet", columns=["timestamp"])["timestamp"]
    return pd.DatetimeIndex(stamps.sort_values().unique())


def main() -> int:
    CYCLES.mkdir(parents=True, exist_ok=True)
    for unit in SOURCES:
        table = segments(read_raw(unit))
        table.to_parquet(CYCLES / f"{unit}_segments.parquet", index=False)
        bin_features(table, unit_grid(unit)).to_parquet(CYCLES / f"{unit}_cycle5m.parquet", index=False)
        idle = table[table["idle"] == 1]
        print(f"{unit}: {len(table):,} segments, idle decay median {(-idle['rate']).median():.4f} bar/min", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
