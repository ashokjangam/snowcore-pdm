"""PNEUMORA command center and maintenance system."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "data" / "product"
PROCESSED = ROOT / "data" / "processed"
RESEARCH = ROOT / "autoresearch"
DB_PATH = Path(os.environ.get("PNEUMORA_DB", ROOT / "data" / "cmms.sqlite"))
SEED_VERSION = 5

app = FastAPI(title="PNEUMORA")
app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")
app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")


def leak_sentence(minutes: float) -> str:
    shown = f"{minutes / 60:.1f} hours" if minutes >= 120 else f"{minutes:.0f} minutes"
    return (
        f"The compressor ran {shown} without a rest. "
        "A healthy run is about 2 minutes, so air may be leaking."
    )


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def seed(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS technicians (
            id TEXT PRIMARY KEY, name TEXT, role TEXT, shift TEXT
        );
        CREATE TABLE IF NOT EXISTS parts (
            sku TEXT PRIMARY KEY, name TEXT, stock INTEGER, reorder_at INTEGER, cost_eur REAL
        );
        CREATE TABLE IF NOT EXISTS work_orders (
            id TEXT PRIMARY KEY, warning_id TEXT, created_at TEXT, priority TEXT,
            problem TEXT, action TEXT, technician TEXT, part TEXT, status TEXT,
            asset TEXT, note TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, at TEXT, status TEXT, note TEXT
        );
        """
    )
    version = connection.execute("SELECT value FROM meta WHERE key='seed'").fetchone()
    if version and version["value"] == str(SEED_VERSION):
        return
    connection.execute("DELETE FROM events")
    connection.execute("DELETE FROM work_orders")
    connection.execute("DELETE FROM parts")
    connection.execute("DELETE FROM technicians")
    crew = [
        ("T-01", "Inês Carvalho", "Shift lead", "Days"),
        ("T-02", "Miguel Santos", "Pneumatics", "Nights"),
        ("T-03", "Rui Almeida", "Electrical", "Days"),
        ("T-04", "Beatriz Costa", "Reliability", "Days"),
        ("T-05", "João Ferreira", "Dryer systems", "Nights"),
        ("T-06", "Ana Lopes", "Planner", "Days"),
    ]
    parts = [
        ("P-100", "Seal kit", 12, 4, 86),
        ("P-110", "Air hose assembly", 6, 2, 140),
        ("P-120", "Dryer drain valve", 3, 2, 220),
        ("P-130", "Pressure switch", 4, 1, 175),
        ("P-140", "Oil filter", 8, 3, 64),
        ("P-150", "Coupling set", 15, 5, 38),
    ]
    connection.executemany("INSERT INTO technicians VALUES (?,?,?,?)", crew)
    connection.executemany("INSERT INTO parts VALUES (?,?,?,?,?)", parts)
    warnings = pd.read_parquet(PRODUCT / "warnings.parquet")
    statuses = ["ready", "progress", "parts", "done", "done"]
    problems = [
        ("Air is taking longer to recover after each compressor cycle.", "Inspect couplings, hoses and the dryer drain."),
        ("The compressor is staying loaded longer than its normal pattern.", "Walk the client-air path and listen for a leak."),
        ("Available air is falling toward the low-air point.", "Check the reservoir outlet and pressure switch."),
        ("The dryer discharge is behaving differently from the healthy pattern.", "Inspect the dryer drain before the next departure."),
    ]
    for index, row in enumerate(warnings.itertuples(), start=1):
        problem, action = problems[index % len(problems)]
        if row.risk_level == "ATTENTION":
            problem, action = (
                "Air pressure is already at the low-air point.",
                "Hold the next departure and inspect the air path now.",
            )
        status = "ready" if row.risk_level == "ATTENTION" else statuses[index % len(statuses)]
        order_id = f"PN-WO-{index:04d}"
        connection.execute(
            """INSERT INTO work_orders VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                order_id,
                row.warning_id,
                pd.Timestamp(row.raised_at).isoformat(sep=" "),
                "urgent" if row.risk_level == "ATTENTION" else "planned",
                problem,
                action,
                crew[index % len(crew)][1],
                parts[index % len(parts)][1],
                status,
                "APU-01",
                "",
            ),
        )
        connection.execute(
            "INSERT INTO events (order_id, at, status, note) VALUES (?,?,?,?)",
            (order_id, pd.Timestamp(row.raised_at).isoformat(sep=" "), status, "Opened from compressor reading"),
        )
    copilot_path = PRODUCT / "copilot_alerts.parquet"
    if copilot_path.exists():
        for index, alert in enumerate(pd.read_parquet(copilot_path).itertuples(), start=1):
            order_id = f"PN-CO-{index:04d}"
            opened = pd.Timestamp(alert.raised_at).isoformat(sep=" ")
            connection.execute(
                """INSERT INTO work_orders VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    order_id,
                    alert.alert_id,
                    opened,
                    "planned",
                    leak_sentence(float(alert.peak_loaded_minutes)),
                    "Walk the air path: hoses, couplings, client pipes and the dryer drain.",
                    crew[index % len(crew)][1],
                    parts[1][1],
                    "ready",
                    "APU-01",
                    "Draft opened by the early air-leak predictor (promoted after cross-validation on three compressors). Review before sending.",
                ),
            )
            connection.execute(
                "INSERT INTO events (order_id, at, status, note) VALUES (?,?,?,?)",
                (order_id, opened, "ready", "Drafted by the early air-leak detector"),
            )
    connection.execute("INSERT OR REPLACE INTO meta VALUES ('seed', ?)", (str(SEED_VERSION),))
    connection.commit()


def load_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict, dict, dict]:
    telemetry = pd.read_parquet(
        PROCESSED / "telemetry.parquet",
        columns=["timestamp", "tp2", "tp3", "reservoirs", "motor_current", "oil_temperature", "comp", "mpg", "lps"],
    )
    telemetry["timestamp"] = pd.to_datetime(telemetry["timestamp"])
    series = telemetry.set_index("timestamp").resample("5min").mean().dropna(subset=["reservoirs"])
    kpis = pd.read_parquet(PRODUCT / "daily_kpis.parquet")
    factory = pd.read_parquet(PRODUCT / "factory_scenario.parquet")
    contract = json.loads((PRODUCT / "contract.json").read_text(encoding="utf-8"))
    profile = json.loads((PROCESSED / "data_profile.json").read_text(encoding="utf-8"))
    training = json.loads((RESEARCH / "training_report.json").read_text(encoding="utf-8"))
    return series, kpis, factory, contract, profile, training


SERIES, KPIS, FACTORY, CONTRACT, PROFILE, TRAINING = load_frames()
COPILOT = CONTRACT.get("copilot")
TRACK = (
    json.loads((PRODUCT / "copilot_track.json").read_text(encoding="utf-8"))
    if (PRODUCT / "copilot_track.json").exists()
    else None
)


def replay_marks() -> list[dict]:
    if TRACK is None:
        return []
    marks = [{"kind": "failure", "id": f["id"], "start": f["start"], "end": f["end"], "label": f"Reported failure {f['id']}"}
             for f in TRACK["failures"]]
    marks += [{"kind": "copilot", "id": r["alert_id"], "start": r["raised_at"], "end": r["cleared_at"],
               "label": f"Leak detector alert {r['alert_id']}"} for r in TRACK["copilot"]]
    return sorted(marks, key=lambda mark: mark["start"])
COPILOT_SERIES = (
    pd.read_parquet(PRODUCT / "copilot_series.parquet").set_index("timestamp").sort_index()
    if (PRODUCT / "copilot_series.parquet").exists()
    else None
)


def copilot_at(moment: pd.Timestamp) -> dict | None:
    if COPILOT is None or COPILOT_SERIES is None:
        return None
    window = COPILOT_SERIES.loc[moment - pd.Timedelta(minutes=10): moment]
    base = {"status": COPILOT["status"], "evidence": COPILOT["evidence"]}
    if window.empty:
        return {**base, "active": False, "loaded_minutes": 0}
    latest = window.iloc[-1]
    active = bool(window["copilot_flag"].any())
    started, longest = None, float(latest["loaded_run_minutes"] or 0)
    if active:
        flagged = COPILOT_SERIES.loc[:moment]
        flagged = flagged[flagged["copilot_flag"].fillna(False).astype(bool)]
        times = list(flagged.index)
        started = times[-1]
        for index in range(len(times) - 1, 0, -1):
            if times[index] - times[index - 1] > pd.Timedelta(minutes=30):
                break
            started = times[index - 1]
        longest = float(flagged.loc[started:moment, "loaded_run_minutes"].max())
    return {
        **base,
        "active": active,
        "loaded_minutes": round(float(latest["loaded_run_minutes"] or 0), 1),
        "started": None if started is None else started.isoformat(sep=" ", timespec="minutes"),
        "longest_minutes": round(longest, 1),
        "on_minutes": 0 if started is None else (moment - started).total_seconds() / 60,
    }
DATABASE = connect()
seed(DATABASE)


def rows(query: str, parameters: tuple = ()) -> list[dict]:
    return [dict(row) for row in DATABASE.execute(query, parameters).fetchall()]


class WorkOrderIn(BaseModel):
    problem: str = Field(min_length=3)
    action: str = Field(min_length=3)
    technician: str
    part: str
    priority: str = "planned"


class WorkOrderPatch(BaseModel):
    status: str | None = None
    technician: str | None = None
    note: str | None = None


class StockAdjust(BaseModel):
    delta: int


def estimate(recent: pd.DataFrame) -> tuple[str, str]:
    clean = recent.dropna(subset=["reservoirs"]).tail(24)
    if len(clean) < 4:
        return "Not enough recent air readings", "At least twenty minutes of readings are needed."
    elapsed = np.arange(len(clean), dtype=float) * 5
    slope = float(np.polyfit(elapsed, clean["reservoirs"].to_numpy(dtype=float), 1)[0])
    current = float(clean["reservoirs"].iloc[-1])
    if current <= 7:
        return "Air is already low", "Reservoir pressure is at or below 7 bar."
    if slope >= -0.002:
        return "Pressure is holding", "The recent air trend is not falling toward 7 bar."
    minutes = (current - 7) / -slope
    return f"{max(0, minutes * 0.7):.0f}–{minutes * 1.3:.0f} min", "Projected from the recent reservoir-pressure slope. This is not a validated life model."


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "web" / "index.html")


@app.get("/api/bootstrap")
def bootstrap() -> dict:
    open_orders = DATABASE.execute("SELECT COUNT(*) AS n FROM work_orders WHERE status NOT IN ('done','dismissed')").fetchone()["n"]
    urgent = DATABASE.execute("SELECT COUNT(*) AS n FROM work_orders WHERE priority='urgent' AND status NOT IN ('done','dismissed')").fetchone()["n"]
    return {
        "product": "PNEUMORA",
        "replay_default": "2020-06-06T20:30:00",
        "range": {"start": SERIES.index.min().isoformat(), "end": SERIES.index.max().isoformat()},
        "model_status": CONTRACT["model_status"],
        "asset": {"id": "APU-01", "name": "Air production unit", "place": "MetroPT-3 compressor"},
        "open_orders": open_orders,
        "urgent_orders": urgent,
        "copilot": COPILOT,
        "marks": replay_marks(),
    }


@app.get("/api/copilot")
def copilot_track() -> dict:
    if TRACK is None:
        raise HTTPException(404, "Leak detector track record has not been built")
    return TRACK


def explain(moment: pd.Timestamp, latest, low: bool, copilot: dict | None, order, estimate_text: str) -> list[dict]:
    """Every check behind the status, in the order the status logic applies them."""
    if latest is None:
        return [{"check": "Readings", "reading": "No readings in the last four hours", "normal": "Readings every 10 seconds",
                 "triggered": False, "source": "Observed telemetry"}]
    reservoir = float(latest["reservoirs"])
    lps = float(latest["lps"])
    age = (moment - pd.Timestamp(latest["timestamp"])).total_seconds() / 60
    reasons = [
        {
            "check": "Air pressure right now",
            "reading": f"Reservoir {reservoir:.2f} bar; low-pressure switch on {lps * 100:.0f}% of the last 5 min",
            "normal": "Reservoir above 7 bar and switch off",
            "triggered": low,
            "source": "Observed reservoir pressure",
        }
    ]
    if copilot is not None:
        threshold = COPILOT["persistence_minutes"] if COPILOT else 60
        reasons.append({
            "check": "Early air-leak predictor",
            "reading": (
                f"This cycle {copilot['loaded_minutes']:.0f} min; longest since the warning started is {copilot.get('longest_minutes', copilot['loaded_minutes']):.0f} min"
            ),
            "normal": f"Healthy cycles last about 2 min. The warning turns on after cycles stay longer than that for about {threshold} min.",
            "triggered": bool(copilot["active"]),
            "source": "Promoted detector, cross-validated on three compressors",
        })
    reasons.append({
        "check": "Open work order",
        "reading": f"{order['id']} opened {pd.Timestamp(order['created_at']).strftime('%d %b %H:%M')}" if order else "None opened in the last 3 hours",
        "normal": "No open order from the last 3 hours",
        "triggered": order is not None,
        "source": "PNEUMORA maintenance system (demonstration records)",
    })
    reasons.append({
        "check": "Air trend",
        "reading": estimate_text,
        "normal": "Pressure is holding",
        "triggered": False,
        "source": "Projection from the last two hours; shown for context, not used for the status",
    })
    reasons.append({
        "check": "Latest reading",
        "reading": f"{age:.0f} min before the replay time",
        "normal": "Within 5 minutes",
        "triggered": False,
        "source": "Gaps usually mean the train was powered off",
    })
    return reasons


@app.get("/api/now")
def now(at: str) -> dict:
    moment = pd.Timestamp(at)
    recent = SERIES.loc[moment - pd.Timedelta(hours=4): moment].reset_index()
    latest = recent.iloc[-1] if not recent.empty else None
    low = bool(latest is not None and (latest["reservoirs"] < 7 or latest["lps"] > 0.2))
    order = DATABASE.execute(
        """
        SELECT * FROM work_orders
        WHERE created_at <= ? AND status NOT IN ('done','dismissed')
        ORDER BY created_at DESC LIMIT 1
        """,
        (moment.strftime("%Y-%m-%d %H:%M:%S"),),
    ).fetchone()
    recent_order = order and moment - pd.Timestamp(order["created_at"]) <= pd.Timedelta(hours=3)
    copilot = copilot_at(moment)
    if low:
        state, title = "low", "Air may run low soon"
        explanation = "Available air is already at the low point. This is the pressure reading right now."
        action = "Hold the next departure and inspect hoses, couplings and the dryer drain."
    elif copilot and copilot["active"]:
        state, title = "watch", "Possible air leak"
        started = pd.Timestamp(copilot["started"]) if copilot.get("started") else moment
        if copilot.get("on_minutes", 0) < 15:
            explanation = (
                f"Cycles have stayed longer than the normal 2 minutes for about an hour, so the warning just turned on. "
                f"This cycle is {copilot['loaded_minutes']:.0f} min. The warning stays up as later cycles get longer; "
                f"it does not mean this one cycle is the whole problem."
            )
        else:
            explanation = (
                f"This warning has been on since {started:%H:%M}. This cycle is {copilot['loaded_minutes']:.0f} min. "
                f"The longest cycle since the warning started is {copilot['longest_minutes']:.0f} min. "
                f"Healthy cycles last about 2 minutes. The minutes change with each cycle; the warning does not."
            )
        action = "Walk the air path before the next departure: hoses, couplings, client pipes and the dryer drain."
    elif recent_order:
        state, title = "watch", "Needs attention"
        opened = (moment - pd.Timestamp(order["created_at"])).total_seconds() / 60
        explanation = (
            f"Work order {order['id']} was opened {opened:.0f} minutes ago because: {order['problem']} "
            "Air readings have since returned to normal, but the order keeps this flag up for 3 hours or until it is completed."
        )
        action = order["action"]
    else:
        state, title = "ok", "Running normally"
        explanation = "Air pressure and compressor workload are inside the healthy pattern for this replay."
        action = "No maintenance action is needed right now."
    estimate_text, estimate_note = estimate(recent)
    reasons = explain(moment, latest, low, copilot, order if recent_order else None, estimate_text)
    decided_by = next((r["check"] for r in reasons if r["triggered"]), "Every check is inside its normal range")
    points = [
        {
            "t": pd.Timestamp(row.timestamp).isoformat(),
            "reservoirs": round(float(row.reservoirs), 3),
            "tp3": round(float(row.tp3), 3),
            "current": round(float(row.motor_current), 3),
        }
        for row in recent.itertuples()
    ]
    sensors = None
    if latest is not None:
        sensors = {
            "reservoirs": round(float(latest["reservoirs"]), 2),
            "tp3": round(float(latest["tp3"]), 2),
            "current": round(float(latest["motor_current"]), 2),
            "oil": round(float(latest["oil_temperature"]), 1),
            "loaded": round(float(latest["mpg"]), 2),
        }
    return {
        "state": state,
        "title": title,
        "explanation": explanation,
        "action": action,
        "estimate": estimate_text,
        "estimate_note": estimate_note,
        "series": points,
        "sensors": sensors,
        "order": dict(order) if recent_order else None,
        "reasons": reasons,
        "decided_by": decided_by,
        "model_status": CONTRACT["model_status"],
        "copilot": copilot,
    }


@app.get("/api/maintenance")
def maintenance() -> dict:
    orders = rows("SELECT * FROM work_orders ORDER BY created_at DESC")
    events = rows("SELECT * FROM events ORDER BY id")
    by_order: dict[str, list[dict]] = {}
    for event in events:
        by_order.setdefault(event["order_id"], []).append(event)
    for order in orders:
        order["events"] = by_order.get(order["id"], [])
    return {
        "asset": {"id": "APU-01", "name": "Air production unit", "location": "MetroPT-3 compressor"},
        "technicians": rows("SELECT * FROM technicians"),
        "parts": rows("SELECT * FROM parts ORDER BY sku"),
        "orders": orders,
    }


@app.post("/api/work-orders")
def create_order(payload: WorkOrderIn) -> dict:
    count = DATABASE.execute("SELECT COUNT(*) AS n FROM work_orders").fetchone()["n"] + 1
    order_id = f"PN-WO-{count:04d}"
    created = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    DATABASE.execute(
        "INSERT INTO work_orders VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (order_id, None, created, payload.priority, payload.problem, payload.action,
         payload.technician, payload.part, "ready", "APU-01", ""),
    )
    DATABASE.execute(
        "INSERT INTO events (order_id, at, status, note) VALUES (?,?,?,?)",
        (order_id, created, "ready", "Created in PNEUMORA"),
    )
    DATABASE.commit()
    return {"id": order_id}


@app.patch("/api/work-orders/{order_id}")
def update_order(order_id: str, payload: WorkOrderPatch) -> dict:
    current = DATABASE.execute("SELECT * FROM work_orders WHERE id=?", (order_id,)).fetchone()
    if current is None:
        raise HTTPException(404, "Work order not found")
    allowed = {"ready", "progress", "parts", "done", "dismissed"}
    status = payload.status or current["status"]
    if status not in allowed:
        raise HTTPException(400, "Unknown status")
    technician = payload.technician or current["technician"]
    note = payload.note if payload.note is not None else current["note"]
    DATABASE.execute(
        "UPDATE work_orders SET status=?, technician=?, note=? WHERE id=?",
        (status, technician, note, order_id),
    )
    if status != current["status"] or payload.note:
        DATABASE.execute(
            "INSERT INTO events (order_id, at, status, note) VALUES (?,?,?,?)",
            (order_id, datetime.now().replace(microsecond=0).isoformat(sep=" "), status, payload.note or "Status updated"),
        )
    DATABASE.commit()
    return {"id": order_id, "status": status}


@app.post("/api/parts/{sku}/adjust")
def adjust_part(sku: str, payload: StockAdjust) -> dict:
    part = DATABASE.execute("SELECT * FROM parts WHERE sku=?", (sku,)).fetchone()
    if part is None:
        raise HTTPException(404, "Part not found")
    stock = max(0, part["stock"] + payload.delta)
    DATABASE.execute("UPDATE parts SET stock=? WHERE sku=?", (stock, sku))
    DATABASE.commit()
    return {"sku": sku, "stock": stock}


@app.get("/api/performance")
def performance() -> dict:
    daily = []
    for row in KPIS.tail(120).itertuples():
        daily.append({
            "date": pd.Timestamp(row.date).date().isoformat(),
            "coverage": round(float(row.telemetry_coverage), 3),
            "runtime": round(float(row.compressor_runtime), 3),
            "loaded": round(float(row.loaded_time), 3),
            "strain": round(float(row.time_under_strain), 3),
        })
    example = []
    for row in FACTORY.tail(120).itertuples():
        example.append({
            "date": pd.Timestamp(row.date).date().isoformat(),
            "oee": None if pd.isna(row.oee) else round(float(row.oee), 3),
            "good_units": int(row.good_units),
            "cost": round(float(row.estimated_downtime_cost_eur), 0),
        })
    return {"measured": daily, "example_factory": example}


@app.get("/api/training")
def training() -> dict:
    return TRAINING


def external_validation() -> dict | None:
    development_path = RESEARCH / "official_study.json"
    external_path = RESEARCH / "external_result.json"
    if not (development_path.exists() and external_path.exists()):
        return None
    development = json.loads(development_path.read_text(encoding="utf-8"))
    external = json.loads(external_path.read_text(encoding="utf-8"))
    final = development["final_result"]
    lps_dev = development["unit"]["lps_existing_alarm"]
    lps_false = sum(unit["lps_existing_alarm"]["false_alerts"] for unit in external["units"].values())
    lps_caught = sum(unit["lps_existing_alarm"]["caught_in_time"] for unit in external["units"].values())
    pooled = external["pooled"]
    return {
        "detector": "Compressor stays loaded for about an hour without stopping",
        "target": development["target"],
        "status": external["status"],
        "gates": external["gates"],
        "rows": [
            {"study": "MetroPT-3 development", "who": "PNEUMORA detector", "caught": f"{final['caught_in_time']} of 4",
             "false_alerts": final["false_alerts"], "days": round(final["healthy_days"])},
            {"study": "MetroPT-3 development", "who": "Existing low-pressure alarm", "caught": f"{lps_dev['caught_in_time']} of 4",
             "false_alerts": lps_dev["false_alerts"], "days": round(lps_dev["healthy_days"])},
            {"study": "Untouched 2022 data", "who": "PNEUMORA detector", "caught": f"{pooled['all_events_caught_in_time']} of 5",
             "false_alerts": pooled["false_alerts"], "days": round(pooled["healthy_days"])},
            {"study": "Untouched 2022 data", "who": "Existing low-pressure alarm", "caught": f"{lps_caught} of 5",
             "false_alerts": lps_false, "days": round(pooled["healthy_days"])},
        ],
        "reading": "The detector is far quieter than the existing alarm but did not catch more failures or catch them sooner on untouched data, so it stays a research result.",
        "cross_validation": cross_validation(),
    }


def cross_validation() -> dict | None:
    path = RESEARCH / "louo_study.json"
    if not path.exists():
        return None
    study = json.loads(path.read_text(encoding="utf-8"))
    model, lps = study["held_out_pooled"], study["lps_pooled_same_events"]
    return {
        "status": study["status"],
        "gates": study["gates"],
        "rows": [
            {"who": "PNEUMORA, chosen without the held-out unit", "caught": f"{model['caught']} of {model['events']}",
             "air": model["air_caught"], "false_alerts": model["false_alerts"], "per_day": round(model["false_per_day"], 3)},
            {"who": "Existing low-pressure alarm", "caught": f"{lps['caught']} of {lps['events']}",
             "air": lps["air_caught"], "false_alerts": lps["false_alerts"], "per_day": round(lps["false_per_day"], 3)},
        ],
    }


@app.get("/api/evidence")
def evidence() -> dict:
    return {
        "external_validation": external_validation(),
        "profile": {
            "rows": PROFILE["rows"],
            "cadence_seconds": PROFILE["median_cadence_seconds"],
            "started_at": PROFILE["started_at"],
            "ended_at": PROFILE["ended_at"],
            "doi": PROFILE["source_doi"],
            "sha256": PROFILE["source_sha256"],
            "ranges": PROFILE["physical_ranges"],
            "missing": PROFILE["missing_by_signal"],
        },
        "decision": TRAINING["decision"],
        "limits": CONTRACT["limits"],
        "truth": CONTRACT["truth_contract"],
    }
