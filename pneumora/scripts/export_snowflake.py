"""Export the PNEUMORA product as Snowflake load files (gzip CSV, one per table).

The export imports the local server against a throwaway maintenance database so
every table holds exactly what the local app serves.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "snowflake"
TS = "%Y-%m-%d %H:%M:%S"

os.environ["PNEUMORA_DB"] = str(Path(tempfile.mkdtemp()) / "export-cmms.sqlite")
sys.path.insert(0, str(ROOT))
from server import main as server  # noqa: E402


def stamp(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.strftime(TS)


def telemetry_5m() -> pd.DataFrame:
    frame = server.SERIES.reset_index()[["timestamp", "reservoirs", "tp3", "motor_current", "oil_temperature", "mpg", "lps"]]
    copilot = server.COPILOT_SERIES[["loaded_run_minutes", "copilot_flag"]].reset_index()
    frame = frame.merge(copilot, on="timestamp", how="left")
    frame["copilot_flag"] = frame["copilot_flag"].astype("boolean").fillna(False).astype(bool)
    frame["timestamp"] = stamp(frame["timestamp"])
    frame["data_origin"] = "OBSERVED_TELEMETRY"
    return frame.rename(columns={"timestamp": "ts"}).round(4)


def failures(track: dict) -> pd.DataFrame:
    rows = [{key: value for key, value in failure.items() if key != "series"} for failure in track["failures"]]
    return pd.DataFrame(rows).rename(columns={"id": "failure_id", "start": "start_ts", "end": "end_ts"})


def failure_zoom(track: dict) -> pd.DataFrame:
    rows = [{"failure_id": failure["id"], **point} for failure in track["failures"] for point in failure["series"]]
    return pd.DataFrame(rows).rename(columns={"t": "ts"})


def alerts(track: dict) -> pd.DataFrame:
    copilot = pd.DataFrame(track["copilot"])
    lps = pd.DataFrame(track["low_pressure_alarm"])
    lps["alert_id"] = [f"PN-L-{index:04d}" for index in range(1, len(lps) + 1)]
    lps["peak_loaded_minutes"] = float("nan")
    columns = ["source", "alert_id", "raised_at", "cleared_at", "outcome", "failure_id",
               "minutes_after_start", "minutes_before_end", "peak_loaded_minutes"]
    return pd.concat([copilot[columns], lps[columns]], ignore_index=True)


PRECURSOR_ARMS = {
    "label_free_cycle_physics": "Cycle physics + multi-day drift (label-free)",
    "gbm_precursor": "Supervised on the 6 h before other failures",
    "gbm_onset": "Supervised on the first 2 h of other failures",
    "gbm_replay": "Supervised + synthetic attenuated failure replays",
}


def precursor() -> dict:
    study = json.loads((ROOT / "autoresearch" / "precursor_study.json").read_text(encoding="utf-8"))
    rows = [{"approach": "Existing low-pressure alarm", **{k: study["existing_alarm_same_events"][k] for k in
             ("warned_before_onset", "caught_in_time_official", "false_per_day")}, "status": "EXISTING_ALARM"}]
    for key, label in PRECURSOR_ARMS.items():
        stats = study["summary"][key]
        rows.append({"approach": label, **{k: stats["held_out"][k] for k in ("warned_before_onset", "caught_in_time_official", "false_per_day")},
                     "status": stats["status"], "random_p": stats["random_alerter"]["p"]})
    rolling = study["exploratory_rolling_baseline"]
    rows.append({"approach": "Rolling 7-day baseline (designed after seeing data)",
                 **{k: rolling["pooled"][k] for k in ("warned_before_onset", "caught_in_time_official", "false_per_day")},
                 "status": rolling["status"], "random_p": rolling["random_alerter"]["p"]})
    warned = [e for e in rolling["events"] if e["warned_before_onset"]]
    return {
        "gates": study["declared_gates"],
        "pre_onset_hours": study["pre_onset_window_hours"],
        "any_promoted": study["any_promoted"],
        "rows": rows,
        "warned_events": warned,
        "percentiles": study["precursor_percentiles"],
        "injection": study["injection_sensitivity"],
        "caveat": study["caveat"],
    }


def prediction() -> dict:
    study = json.loads((ROOT / "autoresearch" / "prediction_study.json").read_text(encoding="utf-8"))
    events = [{"held_out": fold["held_out"], "chosen_on_other_two": fold["chosen"], **event}
              for fold in study["folds"] for event in fold["events"]]
    return {key: study[key] for key in ("target", "declared_gates", "gates", "status", "why_v2", "caveat",
                                        "held_out_pooled", "existing_alarm_same_events", "pre_onset_predictions",
                                        "random_alerter")} | {"events": events}


def evidence(track: dict) -> pd.DataFrame:
    summary = {key: value for key, value in track.items() if key not in {"copilot", "low_pressure_alarm", "failures"}}
    documents = {
        "track_summary": summary,
        "copilot_contract": server.COPILOT,
        "evidence": server.evidence(),
        "model_status": {"model_status": server.CONTRACT["model_status"]},
        "precursor": precursor(),
        "prediction": prediction(),
    }
    return pd.DataFrame([{"doc_key": key, "doc_json": json.dumps(value, default=str)} for key, value in documents.items()])


def cmms_tables() -> dict[str, pd.DataFrame]:
    orders = pd.DataFrame(server.rows("SELECT * FROM work_orders ORDER BY created_at"))
    orders = orders.rename(columns={"id": "order_id"})
    orders["data_origin"] = "SYNTHETIC_MAINTENANCE_RECORD"
    parts = pd.DataFrame(server.rows("SELECT * FROM parts ORDER BY sku"))
    parts["data_origin"] = "SYNTHETIC_MAINTENANCE_RECORD"
    crew = pd.DataFrame(server.rows("SELECT * FROM technicians ORDER BY id")).rename(columns={"id": "technician_id"})
    crew["data_origin"] = "SYNTHETIC_MAINTENANCE_RECORD"
    return {"WORK_ORDERS": orders, "PARTS": parts, "TECHNICIANS": crew}


def daily() -> dict[str, pd.DataFrame]:
    kpis = server.KPIS.copy()
    kpis["date"] = pd.to_datetime(kpis["date"]).dt.strftime("%Y-%m-%d")
    factory = server.FACTORY.copy()
    factory["date"] = pd.to_datetime(factory["date"]).dt.strftime("%Y-%m-%d")
    return {"DAILY_KPIS": kpis, "FACTORY_SCENARIO": factory}


def main() -> None:
    if server.TRACK is None:
        raise SystemExit("Run scripts/build_product.py first: copilot_track.json is missing")
    OUT.mkdir(parents=True, exist_ok=True)
    tables = {
        "TELEMETRY_5M": telemetry_5m(),
        "FAILURES": failures(server.TRACK),
        "FAILURE_ZOOM": failure_zoom(server.TRACK),
        "ALERTS": alerts(server.TRACK),
        "EVIDENCE": evidence(server.TRACK),
        **cmms_tables(),
        **daily(),
    }
    manifest = {}
    for name, frame in tables.items():
        path = OUT / f"{name.lower()}.csv.gz"
        frame.columns = [column.upper() for column in frame.columns]
        frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
        manifest[name] = {
            "file": path.name,
            "rows": len(frame),
            "columns": list(frame.columns),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({name: item["rows"] for name, item in manifest.items()}, indent=2))


if __name__ == "__main__":
    main()
