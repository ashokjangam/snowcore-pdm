"""Status and reasons for a replay moment, mirroring the PNEUMORA server rules."""

from __future__ import annotations

import numpy as np
import pandas as pd

CLOSED = {"done", "dismissed"}


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


def status_at(moment: pd.Timestamp, telemetry: pd.DataFrame, orders: pd.DataFrame, persistence_minutes: int) -> dict:
    """telemetry: ts-indexed 5-minute frame; orders: work orders with created_at as Timestamp."""
    recent = telemetry.loc[moment - pd.Timedelta(hours=4): moment]
    latest = recent.iloc[-1] if not recent.empty else None
    low = bool(latest is not None and (latest["reservoirs"] < 7 or latest["lps"] > 0.2))

    open_orders = orders[(orders["created_at"] <= moment) & (~orders["status"].isin(CLOSED))]
    order = open_orders.sort_values("created_at").iloc[-1] if not open_orders.empty else None
    recent_order = order is not None and moment - order["created_at"] <= pd.Timedelta(hours=3)
    order = order if recent_order else None

    window = telemetry.loc[moment - pd.Timedelta(minutes=10): moment]
    copilot_active = bool(window["copilot_flag"].any()) if not window.empty else False
    loaded_minutes = 0.0
    if not window.empty and pd.notna(window["loaded_run_minutes"].iloc[-1]):
        loaded_minutes = round(float(window["loaded_run_minutes"].iloc[-1]), 1)

    if low:
        state, title = "low", "Air may run low soon"
        explanation = "Available air is at the low-air point. This is the existing pressure alarm, not an early forecast."
        action = "Hold the next departure and inspect hoses, couplings and the dryer drain."
    elif copilot_active:
        state, title = "watch", "Possible air leak"
        explanation = (
            f"The compressor has worked for {loaded_minutes:.0f} minutes without resting. "
            "Normally it rests every couple of minutes, so air is being held up only by non-stop work."
        )
        action = "Walk the air path before the next departure: hoses, couplings, client pipes and the dryer drain."
    elif order is not None:
        state, title = "watch", "Needs attention"
        opened = (moment - order["created_at"]).total_seconds() / 60
        explanation = (
            f"Work order {order['order_id']} was opened {opened:.0f} minutes ago because: {order['problem']} "
            "Air readings have since returned to normal, but the order keeps this flag up for 3 hours or until it is completed."
        )
        action = order["action"]
    else:
        state, title = "ok", "Running normally"
        explanation = "Air pressure and compressor workload are inside the healthy pattern for this replay."
        action = "No maintenance action is needed right now."

    estimate_text, estimate_note = estimate(recent)
    reasons = explain(moment, latest, low, copilot_active, loaded_minutes, order, estimate_text, persistence_minutes)
    decided_by = next((r["check"] for r in reasons if r["triggered"]), "Every check is inside its normal range")
    return {
        "state": state, "title": title, "explanation": explanation, "action": action,
        "estimate": estimate_text, "estimate_note": estimate_note,
        "reasons": reasons, "decided_by": decided_by,
        "copilot_active": copilot_active, "loaded_minutes": loaded_minutes,
        "order": None if order is None else order.to_dict(), "recent": recent,
    }


def explain(moment, latest, low, copilot_active, loaded_minutes, order, estimate_text, persistence_minutes) -> list[dict]:
    if latest is None:
        return [{"check": "Readings", "reading": "No readings in the last four hours", "normal": "Readings every 10 seconds",
                 "triggered": False, "source": "Observed telemetry"}]
    age = (moment - latest.name).total_seconds() / 60
    return [
        {
            "check": "Existing low-pressure alarm",
            "reading": f"Reservoir {float(latest['reservoirs']):.2f} bar; low-pressure switch on {float(latest['lps']) * 100:.0f}% of the last 5 min",
            "normal": "Reservoir above 7 bar and switch off",
            "triggered": low,
            "source": "Observed telemetry (train's own alarm)",
        },
        {
            "check": "Early air-leak predictor",
            "reading": f"Compressor working non-stop for {loaded_minutes:.0f} min",
            "normal": f"Healthy runs last about 2 min; the leak predictor alerts after about {persistence_minutes} min non-stop",
            "triggered": copilot_active,
            "source": "Promoted detector, cross-validated on three compressors",
        },
        {
            "check": "Open work order",
            "reading": f"{order['order_id']} opened {order['created_at']:%d %b %H:%M}" if order is not None else "None opened in the last 3 hours",
            "normal": "No open order from the last 3 hours",
            "triggered": order is not None,
            "source": "PNEUMORA maintenance system (demonstration records)",
        },
        {
            "check": "Air trend",
            "reading": estimate_text,
            "normal": "Pressure is holding",
            "triggered": False,
            "source": "Projection from the last two hours; shown for context, not used for the status",
        },
        {
            "check": "Latest reading",
            "reading": f"{age:.0f} min before the replay time",
            "normal": "Within 5 minutes",
            "triggered": False,
            "source": "Gaps usually mean the train was powered off",
        },
    ]
