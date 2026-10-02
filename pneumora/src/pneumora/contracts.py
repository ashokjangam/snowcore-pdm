"""Immutable data and evaluation contracts for PNEUMORA."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

SOURCE_DATASET = "METROPT3_UCI_791"
SOURCE_DOI = "10.24432/C5VW3R"

OBSERVED = "OBSERVED_METROPT3"
DERIVED = "DERIVED_FROM_OBSERVED"
SYNTHETIC_TRAINING = "SYNTHETIC_TRAINING_ONLY"
SYNTHETIC_MAINTENANCE = "SYNTHETIC_MAINTENANCE"
SYNTHETIC_FACTORY = "SYNTHETIC_FACTORY_SCENARIO"

FIT_END = datetime(2020, 3, 1)
CALIBRATION_END = datetime(2020, 4, 1)
PRIMARY_HORIZON_MINUTES = 120
ALERT_MERGE_MINUTES = 30
MAX_FALSE_ALERTS_PER_HEALTHY_DAYS = 1 / 7

ANALOG_SIGNALS = (
    "tp2",
    "tp3",
    "h1",
    "dv_pressure",
    "reservoirs",
    "oil_temperature",
    "motor_current",
)
DIGITAL_SIGNALS = ("comp", "dv_electric", "towers", "mpg", "lps", "pressure_switch", "oil_level", "caudal_impulses")
LEARNED_SIGNALS = tuple(signal for signal in ANALOG_SIGNALS if signal not in {"tp2", "tp3", "reservoirs"})


@dataclass(frozen=True)
class FailureEpisode:
    episode_id: str
    start: str
    end: str
    report: str
    onset_precision: str = "minute"


FAILURES = (
    FailureEpisode("F01", "2020-04-18 00:00:00", "2020-04-18 23:59:59", "Air leak, high stress", "day"),
    FailureEpisode("F02", "2020-05-29 23:30:00", "2020-05-30 06:00:00", "Air leak, high stress"),
    FailureEpisode("F03", "2020-06-05 10:00:00", "2020-06-07 14:30:00", "Air leak, high stress"),
    FailureEpisode("F04", "2020-07-15 14:30:00", "2020-07-15 19:00:00", "Air leak, high stress"),
)
