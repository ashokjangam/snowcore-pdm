"""Build deterministic PNEUMORA product artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "autoresearch"))

from pneumora.contracts import (  # noqa: E402
    DERIVED,
    FAILURES,
    SOURCE_DATASET,
    SYNTHETIC_FACTORY,
    SYNTHETIC_MAINTENANCE,
)

PROCESSED = ROOT / "data" / "processed"
PRODUCT = ROOT / "data" / "product"
CAMPAIGN = ROOT / "autoresearch" / "campaign.json"
CHAMPION = ROOT / "autoresearch" / "champion.json"
FREEZE = ROOT / "autoresearch" / "official_freeze.json"
LOUO = ROOT / "autoresearch" / "louo_study.json"
EXTERNAL = ROOT / "autoresearch" / "external_result.json"
UNIT_FRAME = PROCESSED / "units" / "METROPT3_UCI_791.parquet"
COPILOT_STATUS = "CROSS_VALIDATED_NOT_PROMOTED"


def build_copilot() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Run the frozen loaded-run detector with the label-free unit recipe."""
    from official_study import calibrate, parse_config, smooth, unit_splits

    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    _, _, bins, persistence = parse_config(freeze["detector"])
    frame = pd.read_parquet(UNIT_FRAME, columns=["timestamp", "loaded_run_minutes"]).sort_values("timestamp").reset_index(drop=True)
    _, fit_end, cal_end = unit_splits(frame)
    series = smooth(frame["loaded_run_minutes"].fillna(0).to_numpy(), bins)
    calibration = ((frame["timestamp"] >= fit_end) & (frame["timestamp"] < cal_end)).to_numpy()
    threshold = calibrate(frame.loc[calibration, "timestamp"].reset_index(drop=True), series[calibration], persistence)
    sustained = (
        pd.Series(series >= threshold).rolling(persistence, min_periods=persistence).min().fillna(0).astype(bool).to_numpy()
    )
    sustained &= (frame["timestamp"] >= cal_end).to_numpy()
    flagged = frame.loc[sustained, ["timestamp", "loaded_run_minutes"]]
    episode = flagged["timestamp"].diff().gt(pd.Timedelta(minutes=30)).cumsum()
    alerts = (
        flagged.groupby(episode)
        .agg(raised_at=("timestamp", "first"), cleared_at=("timestamp", "last"), peak_loaded_minutes=("loaded_run_minutes", "max"))
        .reset_index(drop=True)
    )
    alerts.insert(0, "alert_id", [f"PN-C-{index:04d}" for index in range(1, len(alerts) + 1)])
    alerts["detector"] = freeze["detector"]
    alerts["status_label"] = COPILOT_STATUS
    alerts["data_origin"] = DERIVED
    louo = json.loads(LOUO.read_text(encoding="utf-8"))
    external = json.loads(EXTERNAL.read_text(encoding="utf-8"))
    summary = {
        "name": "Early air-leak co-pilot",
        "status": COPILOT_STATUS,
        "detector": freeze["detector_plain"],
        "threshold_minutes": threshold,
        "persistence_minutes": persistence * 5,
        "alerts": len(alerts),
        "evidence": {
            "frozen_external_test": external["status"],
            "external_air_leaks_caught": external["pooled"]["air_leaks_caught_in_time"],
            "external_false_alerts": external["pooled"]["false_alerts"],
            "leave_one_unit_out": louo["status"],
            "louo_caught": f"{louo['held_out_pooled']['caught']} of {louo['held_out_pooled']['events']}",
            "louo_false_per_day": louo["held_out_pooled"]["false_per_day"],
            "lps_caught_same_events": f"{louo['lps_pooled_same_events']['caught']} of {louo['lps_pooled_same_events']['events']}",
        },
        "role": "Runs beside the existing low-pressure alarm. It never replaces it and opens draft work orders for human review only.",
    }
    return alerts, frame.assign(copilot_flag=sustained), summary


def merge_warning_rows(frame: pd.DataFrame, flag: pd.Series) -> pd.DataFrame:
    selected = frame.loc[flag].sort_values("timestamp").copy()
    if selected.empty:
        return selected
    step = selected["timestamp"].diff()
    gap = step.isna() | step.gt(pd.Timedelta(minutes=30))
    return selected.loc[gap].copy()


def build_work_orders(warnings: pd.DataFrame) -> pd.DataFrame:
    technicians = ["Alex Morgan", "Sam Rivera", "Jordan Lee"]
    rows = []
    for index, row in enumerate(warnings.head(40).itertuples(), start=1):
        rows.append(
            {
                "work_order_id": f"PN-WO-{index:04d}",
                "warning_id": row.warning_id,
                "created_at": row.raised_at,
                "urgency": "Inspect before next service" if row.risk_level == "ATTENTION" else "Plan inspection",
                "plain_problem": "The compressor is running longer than usual and may be losing air.",
                "first_action": "Check hoses, couplings and dryer drains for an air leak.",
                "technician": technicians[(index - 1) % len(technicians)],
                "part": ["Seal kit", "Air hose", "Dryer valve"][(index - 1) % 3],
                "status": ["Ready to send", "Completed", "Completed"][index % 3],
                "completed_at": row.raised_at + pd.Timedelta(hours=2 + index % 5),
                "labor_hours": 1.5 + (index % 4) * 0.5,
                "data_origin": SYNTHETIC_MAINTENANCE,
            }
        )
    return pd.DataFrame(rows)


def daily_kpis(telemetry: pd.DataFrame) -> pd.DataFrame:
    frame = telemetry.set_index("timestamp")
    daily = pd.DataFrame(index=frame.resample("D").size().index)
    daily["samples"] = frame.resample("D").size()
    expected = max(int(86400 / max(frame.index.to_series().diff().dt.total_seconds().median(), 1)), 1)
    daily["telemetry_coverage"] = np.clip(daily["samples"] / expected, 0, 1)
    daily["compressor_runtime"] = frame["comp"].resample("D").mean()
    daily["loaded_time"] = frame["mpg"].resample("D").mean()
    daily["time_under_strain"] = (
        (frame["motor_current"] > frame["motor_current"].quantile(0.95)).resample("D").mean()
    )
    daily["data_origin"] = DERIVED
    return daily.reset_index(names="date")


def factory_scenario(kpis: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(20260930)
    scenario = kpis[["date"]].copy()
    scenario["planned_minutes"] = 960
    scenario["downtime_minutes"] = np.round(
        15 + 80 * kpis["time_under_strain"].fillna(0) + rng.uniform(0, 20, len(kpis)), 1
    )
    scenario["ideal_units"] = 480
    scenario["total_units"] = np.maximum(
        0, np.round(450 - scenario["downtime_minutes"] / 3 + rng.normal(0, 8, len(kpis)))
    ).astype(int)
    scenario["good_units"] = np.maximum(
        0, scenario["total_units"] - rng.integers(0, 8, len(kpis))
    )
    scenario["availability"] = 1 - scenario["downtime_minutes"] / scenario["planned_minutes"]
    scenario["performance"] = np.clip(scenario["total_units"] / scenario["ideal_units"], 0, 1)
    scenario["quality"] = scenario["good_units"] / scenario["total_units"].replace(0, np.nan)
    scenario["oee"] = scenario["availability"] * scenario["performance"] * scenario["quality"]
    scenario["estimated_downtime_cost_eur"] = scenario["downtime_minutes"] * 12.5
    scenario["data_origin"] = SYNTHETIC_FACTORY
    scenario["disclaimer"] = "Example assumptions, not this train's real production or cost"
    return scenario


def classify(raised: pd.Timestamp) -> tuple[str, str | None, float | None, float | None]:
    need = pd.Timedelta(minutes=120)
    for failure in FAILURES:
        start, end = pd.Timestamp(failure.start), pd.Timestamp(failure.end)
        if start - need <= raised <= end:
            after = (raised - start).total_seconds() / 60
            before_end = (end - raised).total_seconds() / 60
            outcome = "caught_in_time" if raised <= end - need else "too_late"
            return outcome, failure.episode_id, round(after, 1), round(before_end, 1)
    return "no_reported_failure", None, None, None


def build_track(copilot_alerts: pd.DataFrame, summary: dict) -> dict:
    frame = pd.read_parquet(
        UNIT_FRAME, columns=["timestamp", "loaded_run_minutes", "lps_fraction_30m", "reservoirs_mean_30m", "duty_60m"]
    ).sort_values("timestamp").reset_index(drop=True)
    start = pd.Timestamp(copilot_alerts["raised_at"].min()).normalize() if len(copilot_alerts) else frame["timestamp"].min()
    test = frame[frame["timestamp"] >= start].reset_index(drop=True)
    flags = test["lps_fraction_30m"].fillna(0).to_numpy() > 0
    flagged = test.loc[flags, "timestamp"]
    gap = pd.Timedelta(minutes=30)
    lps_starts = flagged[flagged.diff().isna() | flagged.diff().gt(gap)].tolist()
    lps_ends = flagged[flagged.diff(-1).isna() | flagged.diff(-1).abs().gt(gap)].tolist()

    def rows(starts, ends, source):
        out = []
        for raised, cleared in zip(starts, ends):
            outcome, failure_id, after, before_end = classify(pd.Timestamp(raised))
            out.append({"source": source, "raised_at": str(raised), "cleared_at": str(cleared), "outcome": outcome,
                        "failure_id": failure_id, "minutes_after_start": after, "minutes_before_end": before_end})
        return out

    copilot_rows = rows(copilot_alerts["raised_at"], copilot_alerts["cleared_at"], "copilot")
    for row, peak, alert_id in zip(copilot_rows, copilot_alerts["peak_loaded_minutes"], copilot_alerts["alert_id"]):
        row["alert_id"] = alert_id
        row["peak_loaded_minutes"] = round(float(peak), 1)
    lps_rows = rows(lps_starts, lps_ends, "low_pressure_alarm")
    failures = []
    for failure in FAILURES:
        fstart, fend = pd.Timestamp(failure.start), pd.Timestamp(failure.end)
        first = {}
        for source, items in (("copilot", copilot_rows), ("low_pressure_alarm", lps_rows)):
            hits = [r for r in items if r["failure_id"] == failure.episode_id and r["outcome"] == "caught_in_time"]
            first[source] = hits[0] if hits else None
        window = test[(test["timestamp"] >= fstart - pd.Timedelta(hours=6))
                      & (test["timestamp"] <= min(fend, fstart + pd.Timedelta(hours=24)) + pd.Timedelta(hours=2))]
        failures.append({
            "id": failure.episode_id, "start": str(fstart), "end": str(fend), "report": failure.report,
            "removal_deadline": str(fend - pd.Timedelta(minutes=120)), "onset_precision": failure.onset_precision,
            "copilot_first": first["copilot"]["raised_at"] if first["copilot"] else None,
            "copilot_minutes_after_start": first["copilot"]["minutes_after_start"] if first["copilot"] else None,
            "copilot_minutes_before_end": first["copilot"]["minutes_before_end"] if first["copilot"] else None,
            "lps_first": first["low_pressure_alarm"]["raised_at"] if first["low_pressure_alarm"] else None,
            "lps_minutes_after_start": first["low_pressure_alarm"]["minutes_after_start"] if first["low_pressure_alarm"] else None,
            "series": [
                {"t": str(r.timestamp), "loaded": round(float(r.loaded_run_minutes or 0), 1),
                 "reservoirs": None if pd.isna(r.reservoirs_mean_30m) else round(float(r.reservoirs_mean_30m), 2),
                 "lps": round(float(r.lps_fraction_30m or 0), 2)}
                for r in window.itertuples()
            ],
        })

    def tally(items):
        return {
            "alerts": len(items),
            "caught_in_time": len({r["failure_id"] for r in items if r["outcome"] == "caught_in_time"}),
            "no_reported_failure": sum(r["outcome"] == "no_reported_failure" for r in items),
        }

    return {
        "status": summary["status"],
        "window": [str(start), str(frame["timestamp"].max())],
        "threshold_minutes": summary["threshold_minutes"],
        "persistence_minutes": summary["persistence_minutes"],
        "copilot": copilot_rows,
        "low_pressure_alarm": lps_rows,
        "failures": failures,
        "tally": {"copilot": tally(copilot_rows), "low_pressure_alarm": tally(lps_rows), "failures": len(FAILURES)},
        "evidence": summary["evidence"],
        "data_origin": DERIVED,
    }


def main() -> int:
    campaign = json.loads(CAMPAIGN.read_text(encoding="utf-8"))
    champion = json.loads(CHAMPION.read_text(encoding="utf-8"))
    telemetry = pd.read_parquet(PROCESSED / "telemetry.parquet")
    features = pd.read_parquet(PROCESSED / "features_5m.parquet")
    predictions = pd.read_parquet(PRODUCT / "predictions.parquet")
    # If no predictive model passes, retain the existing low-pressure alarm as
    # a reactive safety feed. Never silently operate a rejected candidate.
    model_name = champion["champion"] or "lps_existing_alarm"
    threshold = campaign["arms"][model_name]["threshold"]
    prediction = predictions[["timestamp", model_name]].rename(columns={model_name: "risk_score"})
    joined = features.merge(prediction, on="timestamp", how="inner")
    warnings = merge_warning_rows(joined, joined["risk_score"] >= threshold)
    warnings = warnings[
        [
            "timestamp",
            "risk_score",
            "loaded_fraction_2h",
            "cycle_starts_2h",
            "tp3_reservoir_gap",
            "tp3_slope_120m",
            "reservoirs_slope_120m",
        ]
    ].rename(columns={"timestamp": "raised_at"})
    warnings.insert(0, "warning_id", [f"PN-W-{index:05d}" for index in range(1, len(warnings) + 1)])
    warnings["risk_level"] = np.where(warnings["risk_score"] >= warnings["risk_score"].quantile(0.9), "ATTENTION", "WATCH")
    warnings["model_status"] = champion["status"]
    warnings["data_origin"] = DERIVED
    work_orders = build_work_orders(warnings)
    kpis = daily_kpis(telemetry)
    scenario = factory_scenario(kpis)
    copilot_alerts, copilot_series, copilot = build_copilot()
    PRODUCT.mkdir(parents=True, exist_ok=True)
    copilot_alerts.to_parquet(PRODUCT / "copilot_alerts.parquet", index=False)
    copilot_series.to_parquet(PRODUCT / "copilot_series.parquet", index=False)
    track = build_track(copilot_alerts, copilot)
    (PRODUCT / "copilot_track.json").write_text(json.dumps(track, indent=2), encoding="utf-8")
    warnings.to_parquet(PRODUCT / "warnings.parquet", index=False)
    work_orders.to_parquet(PRODUCT / "work_orders.parquet", index=False)
    kpis.to_parquet(PRODUCT / "daily_kpis.parquet", index=False)
    scenario.to_parquet(PRODUCT / "factory_scenario.parquet", index=False)
    profile = json.loads((PROCESSED / "data_profile.json").read_text(encoding="utf-8"))
    contract = {
        "product": "PNEUMORA",
        "source_dataset": SOURCE_DATASET,
        "source_doi": profile["source_doi"],
        "model_status": champion["status"],
        "active_model": model_name,
        "warning_feed_operational": champion["warning_feed_enabled"],
        "fallback_is_reactive_existing_alarm": champion["champion"] is None,
        "observed_evaluation": campaign["arms"][model_name]["observed_test"],
        "copilot": copilot,
        "truth_contract": {
            "forecast_metrics": "OBSERVED_METROPT3 only",
            "work_orders": SYNTHETIC_MAINTENANCE,
            "factory_score": SYNTHETIC_FACTORY,
        },
        "limits": [
            "Four observed air-leak episodes from one compressor.",
            "Likely-cause text is guidance, not component diagnosis.",
            "Time-to-low-air is a live pressure projection, not validated RUL.",
            "Work orders, factory score and costs are demonstration records.",
        ],
    }
    (PRODUCT / "contract.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")
    print(json.dumps({"warnings": len(warnings), "work_orders": len(work_orders), "status": champion["status"],
                      "copilot_alerts": len(copilot_alerts), "copilot_threshold": copilot["threshold_minutes"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
