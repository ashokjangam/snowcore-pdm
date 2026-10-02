"""Compressor leak physics from raw telemetry: duty, pressure gain while loaded, decay while idle.

COMP is active when the compressor takes no air (off or unloaded), so COMP == 0 is loaded.
A leak shows up as the compressor staying loaded while TP3 barely rises, and as TP3
falling faster than usual while the compressor is idle.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

WINDOWS_MINUTES = (30, 60)
MAX_STEP_MINUTES = 1.0


def physics_features(telemetry: pd.DataFrame) -> pd.DataFrame:
    frame = telemetry[["timestamp", "tp3", "comp"]].sort_values("timestamp").reset_index(drop=True)
    step = frame["timestamp"].diff().dt.total_seconds().div(60).to_numpy()
    rise = frame["tp3"].diff().to_numpy()
    loaded = (frame["comp"] < 0.5).to_numpy()
    valid = np.isfinite(step) & (step > 0) & (step <= MAX_STEP_MINUTES)
    both_loaded = valid & loaded & np.r_[False, loaded[:-1]]
    both_idle = valid & ~loaded & np.r_[False, ~loaded[:-1]]
    per_sample = pd.DataFrame(
        {
            "loaded_minutes": np.where(valid & loaded, step, 0.0),
            "observed_minutes": np.where(valid, step, 0.0),
            "loaded_gain": np.where(both_loaded, rise, 0.0),
            "loaded_gain_minutes": np.where(both_loaded, step, 0.0),
            "idle_drop": np.where(both_idle, -rise, 0.0),
            "idle_drop_minutes": np.where(both_idle, step, 0.0),
        },
        index=frame["timestamp"],
    )
    bins = per_sample.resample("5min").sum()
    out = pd.DataFrame(index=bins.index)
    breaks = ~valid | ~loaded | ~np.r_[False, loaded[:-1]]
    run_id = np.cumsum(breaks)
    run_minutes = pd.Series(np.where(breaks, 0.0, step), index=frame.index).groupby(run_id).cumsum()
    out["loaded_run_minutes"] = (
        pd.Series(np.where(loaded, run_minutes.to_numpy(), 0.0), index=frame["timestamp"]).resample("5min").max()
    )
    for minutes in WINDOWS_MINUTES:
        rolled = bins.rolling(f"{minutes}min").sum()
        out[f"duty_{minutes}m"] = rolled["loaded_minutes"] / rolled["observed_minutes"].replace(0, np.nan)
        out[f"loaded_gain_rate_{minutes}m"] = rolled["loaded_gain"] / rolled["loaded_gain_minutes"].replace(0, np.nan)
        out[f"idle_drop_rate_{minutes}m"] = rolled["idle_drop"] / rolled["idle_drop_minutes"].replace(0, np.nan)
        out[f"coverage_{minutes}m"] = rolled["observed_minutes"] / minutes
    return out.reset_index().rename(columns={"index": "timestamp"})


def fit_baseline(train: pd.DataFrame, minutes: int) -> dict:
    duty = train[f"duty_{minutes}m"]
    working = train[(duty > 0.2) & (train[f"coverage_{minutes}m"] > 0.8)]
    gain = working[f"loaded_gain_rate_{minutes}m"].dropna()
    drop = train[f"idle_drop_rate_{minutes}m"].dropna()
    return {
        "gain_rate": max(float(gain.median()) if len(gain) else 0.5, 1e-3),
        "idle_drop_rate": max(float(drop.median()) if len(drop) else 0.05, 1e-3),
    }


def leak_score(frame: pd.DataFrame, baseline: dict, minutes: int, use_decay: bool) -> np.ndarray:
    duty = frame[f"duty_{minutes}m"].fillna(0).clip(0, 1).to_numpy()
    coverage = frame[f"coverage_{minutes}m"].fillna(0).clip(0, 1).to_numpy()
    gain = frame[f"loaded_gain_rate_{minutes}m"].to_numpy()
    starvation = np.clip(1 - np.nan_to_num(gain, nan=baseline["gain_rate"]) / baseline["gain_rate"], 0, 1)
    score = duty * starvation
    if use_decay:
        drop = np.nan_to_num(frame[f"idle_drop_rate_{minutes}m"].to_numpy(), nan=0.0)
        excess = np.clip((drop / baseline["idle_drop_rate"] - 1) / 9, 0, 1)
        score = np.maximum(score, excess)
    return score * (coverage > 0.5)
