"""Physics-grounded training-only perturbations for MetroPT-3 features."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SimulatorParameters:
    unload_pressure: float
    loaded_fraction_median: float
    loaded_fraction_iqr: float
    pressure_slope_scale: float
    temperature_scale: float
    current_scale: float


def fit_parameters(february: pd.DataFrame) -> SimulatorParameters:
    loaded = february["loaded_fraction_2h"].dropna()
    return SimulatorParameters(
        unload_pressure=float(february["tp3_max_120m"].quantile(0.95)),
        loaded_fraction_median=float(loaded.median()),
        loaded_fraction_iqr=float(loaded.quantile(0.75) - loaded.quantile(0.25)),
        pressure_slope_scale=max(float(february["tp3_slope_120m"].abs().quantile(0.90)), 1e-4),
        temperature_scale=max(float(february["oil_temperature_std_120m"].median()), 0.1),
        current_scale=max(float(february["motor_current_std_120m"].median()), 0.1),
    )


def _raise(frame: pd.DataFrame, column: str, value: np.ndarray) -> None:
    if column in frame:
        frame[column] = frame[column].to_numpy(dtype=float) + value


def generate_leaks(
    healthy: pd.DataFrame,
    parameters: SimulatorParameters,
    copies: int = 2,
    seed: int = 42,
    wrong_physics: bool = False,
) -> pd.DataFrame:
    """Generate feature windows; never call this on calibration or test rows."""
    rng = np.random.default_rng(seed)
    blocks: list[pd.DataFrame] = []
    mechanisms = ("downstream_leak", "dryer_drain_open", "reduced_delivery")
    sample_size = min(len(healthy), max(1500, len(healthy) // 2))
    for copy in range(copies):
        base = healthy.sample(sample_size, replace=True, random_state=seed + copy).copy()
        severity = rng.uniform(0.25, 1.0, len(base))
        mechanism = np.asarray(mechanisms, dtype=object)[rng.integers(0, len(mechanisms), len(base))]
        if wrong_physics:
            _raise(base, "oil_temperature_mean_120m", severity * 8 * parameters.temperature_scale)
            _raise(base, "h1_max_30m", rng.normal(0, 10, len(base)))
            mechanism[:] = "wrong_channel_control"
        else:
            load_delta = severity * max(parameters.loaded_fraction_iqr, 0.05) * 2.5
            base["loaded_fraction_2h"] = np.clip(base["loaded_fraction_2h"] + load_delta, 0, 1)
            _raise(base, "comp_fraction_120m", load_delta)
            _raise(base, "mpg_fraction_120m", load_delta)
            _raise(base, "motor_current_mean_120m", severity * parameters.current_scale)
            _raise(base, "oil_temperature_mean_120m", severity * 0.5 * parameters.temperature_scale)
            leak = mechanism == "downstream_leak"
            drain = mechanism == "dryer_drain_open"
            delivery = mechanism == "reduced_delivery"
            _raise(base, "reservoirs_slope_120m", -severity * parameters.pressure_slope_scale * leak)
            _raise(base, "tp3_reservoir_gap", severity * 0.3 * leak)
            _raise(base, "dv_pressure_mean_120m", severity * 0.5 * drain)
            _raise(base, "tp2_slope_120m", -severity * parameters.pressure_slope_scale * delivery)
            base["cycle_starts_2h"] = np.maximum(
                0, base["cycle_starts_2h"] + severity * (leak.astype(float) + drain.astype(float))
            )
        base["synthetic_mechanism"] = mechanism
        base["synthetic_severity"] = severity
        base["target_failure_2h"] = 1
        base["data_origin"] = "SYNTHETIC_TRAINING_ONLY"
        blocks.append(base)
    return pd.concat(blocks, ignore_index=True)


def realism_report(february: pd.DataFrame, march: pd.DataFrame, parameters: SimulatorParameters) -> dict:
    columns = ["loaded_fraction_2h", "cycle_starts_2h", "oil_temperature_mean_120m"]
    comparisons = {}
    passes = True
    for column in columns:
        fit_median = float(february[column].median())
        check_median = float(march[column].median())
        scale = max(float(february[column].quantile(0.75) - february[column].quantile(0.25)), 1e-6)
        normalised_error = abs(check_median - fit_median) / scale
        comparisons[column] = {
            "fit_median": fit_median,
            "heldout_healthy_median": check_median,
            "normalised_error_iqr": normalised_error,
        }
        passes &= normalised_error <= 3
    return {
        "passes_healthy_march_check": bool(passes),
        "comparisons": comparisons,
        "parameters": parameters.__dict__,
    }
