"""PNEUMORA plain-language command center and engineering evidence."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "data" / "product"
PROCESSED = ROOT / "data" / "processed"
RESEARCH = ROOT / "autoresearch"
BLUE, COPPER, CARBON, CREAM = "#39A9DB", "#C77B50", "#182126", "#F4F1EA"

st.set_page_config(page_title="PNEUMORA", page_icon=str(ROOT / "assets" / "pneumora-icon.svg"), layout="wide")
st.markdown(
    f"""
    <style>
    .stApp {{background: #f6f8f8; color:{CARBON}}}
    [data-testid="stSidebar"] {{background:{CARBON}}}
    [data-testid="stSidebar"] * {{color:{CREAM}}}
    .pn-card {{background:white;border:1px solid #dce3e5;border-radius:18px;padding:1.25rem;
              box-shadow:0 7px 28px rgba(24,33,38,.07);margin:.35rem 0 1rem}}
    .pn-status {{border-left:8px solid var(--tone);background:white;border-radius:18px;padding:1.4rem 1.6rem}}
    .pn-status .eyebrow,.pn-small {{color:#63777f;font-size:.78rem;text-transform:uppercase;letter-spacing:.08em}}
    .pn-status h2 {{font-size:2.2rem;margin:.2rem 0;color:{CARBON}}}
    .pn-action {{background:#eaf6fb;border-radius:14px;padding:1rem 1.2rem;font-weight:650}}
    .pn-label {{display:inline-block;padding:.25rem .55rem;border-radius:999px;background:#edf1f2;
                color:#53666d;font-size:.72rem;font-weight:700}}
    .pn-warning {{background:#fff5ef;border:1px solid #efd2c0}}
    h1,h2,h3 {{color:{CARBON}}}
    div[data-testid="stMetric"] {{background:white;border:1px solid #dce3e5;padding:1rem;border-radius:14px}}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_data():
    required = [
        PRODUCT / "contract.json",
        PRODUCT / "warnings.parquet",
        PRODUCT / "work_orders.parquet",
        PRODUCT / "daily_kpis.parquet",
        PRODUCT / "factory_scenario.parquet",
        PROCESSED / "telemetry.parquet",
        PROCESSED / "data_profile.json",
        RESEARCH / "campaign.json",
    ]
    if not all(path.exists() for path in required):
        return None
    contract = json.loads(required[0].read_text(encoding="utf-8"))
    warnings = pd.read_parquet(required[1])
    orders = pd.read_parquet(required[2])
    kpis = pd.read_parquet(required[3])
    factory = pd.read_parquet(required[4])
    telemetry = pd.read_parquet(
        required[5],
        columns=["timestamp", "tp2", "tp3", "reservoirs", "motor_current", "oil_temperature", "comp", "mpg", "lps"],
    )
    profile = json.loads(required[6].read_text(encoding="utf-8"))
    campaign = json.loads(required[7].read_text(encoding="utf-8"))
    return contract, warnings, orders, kpis, factory, telemetry, profile, campaign


def logo() -> str:
    path = ROOT / "assets" / "pneumora-logo-reversed.svg"
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/svg+xml;base64,{encoded}"


def pressure_estimate(recent: pd.DataFrame) -> tuple[str, str]:
    clean = recent.dropna(subset=["timestamp", "reservoirs"]).tail(24)
    if len(clean) < 4:
        return "Not enough recent readings", "The estimate needs at least four readings."
    elapsed = (clean["timestamp"] - clean["timestamp"].iloc[0]).dt.total_seconds() / 60
    slope = float(np.polyfit(elapsed, clean["reservoirs"], 1)[0])
    current = float(clean["reservoirs"].iloc[-1])
    if slope >= -0.002 or current <= 7:
        return "Pressure is stable", "No meaningful fall toward the low-air point is visible."
    minutes = (current - 7) / -slope
    low, high = max(0, minutes * 0.7), minutes * 1.3
    return f"About {low:.0f}–{high:.0f} minutes", "Projection to 7 bar from the recent reservoir-pressure slope."


def replay_control(telemetry: pd.DataFrame) -> pd.Timestamp:
    minimum, maximum = telemetry["timestamp"].min(), telemetry["timestamp"].max()
    default = min(pd.Timestamp("2020-06-06 20:30"), maximum)
    date = st.sidebar.date_input("Replay date", value=default.date(), min_value=minimum.date(), max_value=maximum.date())
    minute = st.sidebar.slider("Time of day", 0, 1435, default.hour * 60 + default.minute, step=5)
    return pd.Timestamp(date) + pd.Timedelta(minutes=minute)


def current_warning(warnings: pd.DataFrame, now: pd.Timestamp) -> pd.Series | None:
    known = warnings[warnings["raised_at"] <= now]
    if known.empty:
        return None
    latest = known.iloc[-1]
    if now - latest["raised_at"] > pd.Timedelta(hours=2):
        return None
    return latest


def pressure_chart(recent: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=recent["timestamp"], y=recent["reservoirs"], name="Available air", line=dict(color=BLUE, width=3)))
    figure.add_trace(go.Scatter(x=recent["timestamp"], y=recent["tp3"], name="Panel pressure", line=dict(color=CARBON, width=2)))
    figure.add_hline(y=7, line_dash="dash", line_color=COPPER, annotation_text="Low-air point")
    figure.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20), paper_bgcolor="white", plot_bgcolor="white",
                         yaxis_title="Pressure (bar)", legend_orientation="h")
    return figure


def status_card(active: pd.Series | None, recent: pd.DataFrame):
    low = recent["reservoirs"].iloc[-1] < 7 if not recent.empty else False
    if low:
        state, tone, explanation = "Air may run low soon", COPPER, "Available air is already below the normal low-air point."
        action = "Stop and inspect hoses, couplings and dryer drains before the next service."
    elif active is not None:
        state, tone = "Needs attention", COPPER
        explanation = "The compressor has been working longer than its normal pattern. Air may be escaping."
        action = "Send the prepared work order and check for an air leak before the next service."
    else:
        state, tone, explanation = "Running normally", BLUE, "Pressure and compressor workload are within the learned healthy pattern."
        action = "No maintenance action is needed right now."
    st.markdown(
        f'<div class="pn-status" style="--tone:{tone}"><div class="eyebrow">Compressor status</div>'
        f"<h2>{state}</h2><p>{explanation}</p><div class='pn-action'>{action}</div></div>",
        unsafe_allow_html=True,
    )


def simple_now(now, active, telemetry, warnings, orders):
    recent = telemetry[(telemetry["timestamp"] >= now - pd.Timedelta(hours=4)) & (telemetry["timestamp"] <= now)]
    left, right = st.columns([1.2, 1])
    with left:
        status_card(active, recent)
    with right:
        estimate, note = pressure_estimate(recent)
        st.markdown(
            f'<div class="pn-card"><div class="pn-small">Estimated time until air is low</div>'
            f"<h2>{estimate}</h2><p>{note}</p><span class='pn-label'>Live estimate · not validated RUL</span></div>",
            unsafe_allow_html=True,
        )
    st.plotly_chart(pressure_chart(recent), use_container_width=True)
    if active is not None:
        match = orders[orders["warning_id"] == active["warning_id"]]
        if not match.empty:
            order = match.iloc[0]
            st.markdown(
                f'<div class="pn-card pn-warning"><div class="pn-small">Work order ready</div>'
                f"<h3>{html.escape(order['urgency'])}</h3><p>{html.escape(order['plain_problem'])}</p>"
                f"<p><b>Check first:</b> {html.escape(order['first_action'])}</p>"
                f"<p>Example assignee: {html.escape(order['technician'])} · "
                f"<span class='pn-label'>Synthetic maintenance record</span></p></div>",
                unsafe_allow_html=True,
            )
            a, b = st.columns(2)
            a.button("Mark as sent", type="primary", use_container_width=True)
            b.button("Dismiss", use_container_width=True)
    st.caption("Replay uses observed MetroPT-3 readings. Technician, parts and work-order status are demonstration records.")


def work_orders_page(orders: pd.DataFrame):
    st.header("Maintenance")
    st.write("Ready-to-use instructions, without engineering codes.")
    display = orders.rename(
        columns={
            "created_at": "Raised",
            "urgency": "When",
            "plain_problem": "What is happening",
            "first_action": "What to check first",
            "technician": "Example technician",
            "status": "Status",
        }
    )
    st.dataframe(display[["Raised", "When", "What is happening", "What to check first", "Example technician", "Status"]],
                 use_container_width=True, hide_index=True)
    st.info("These are synthetic demonstration work orders. PNEUMORA is not connected to a live CMMS.")


def factory_page(kpis: pd.DataFrame, factory: pd.DataFrame):
    st.header("Compressor performance")
    latest = kpis.iloc[-1]
    c1, c2, c3 = st.columns(3)
    c1.metric("Telemetry available", f"{latest['telemetry_coverage']:.0%}")
    c2.metric("Compressor running", f"{latest['compressor_runtime']:.0%} of day")
    c3.metric("Under strain", f"{latest['time_under_strain']:.1%} of day")
    st.subheader("Example factory score")
    st.warning("Example only — not this train's real production, quality, downtime or cost.")
    latest_scenario = factory.iloc[-1]
    a, b, c = st.columns(3)
    a.metric("Example OEE", f"{latest_scenario['oee']:.0%}")
    b.metric("Example good units", f"{latest_scenario['good_units']:,}")
    c.metric("Example downtime cost", f"€{latest_scenario['estimated_downtime_cost_eur']:,.0f}")
    st.line_chart(factory.set_index("date")[["oee"]])


def engineering_page(now, active, telemetry, profile, campaign, contract):
    st.header("Engineering evidence")
    st.caption("Same replay and warning as Simple mode; this view exposes the evidence and limits.")
    recent = telemetry[(telemetry["timestamp"] >= now - pd.Timedelta(hours=6)) & (telemetry["timestamp"] <= now)]
    tabs = st.tabs(["Why this warning", "System", "Forecast evidence", "Models", "Synthetic data", "Provenance"])
    with tabs[0]:
        if recent.empty:
            st.info("No readings at this replay time.")
        else:
            latest = recent.iloc[-1]
            cols = st.columns(4)
            cols[0].metric("Reservoir", f"{latest['reservoirs']:.2f} bar")
            cols[1].metric("Panel pressure", f"{latest['tp3']:.2f} bar")
            cols[2].metric("Motor current", f"{latest['motor_current']:.2f} A")
            cols[3].metric("Oil temperature", f"{latest['oil_temperature']:.1f} °C")
            st.plotly_chart(pressure_chart(recent), use_container_width=True)
            st.caption("Likely-cause guidance combines pressure slope, loaded fraction and cycle behavior. It is not component diagnosis.")
    with tabs[1]:
        st.markdown(
            f"""<div class="pn-card"><h3>Air path</h3>
            <p>Intake → <b>compressor</b> → dryer → pneumatic panel → reservoirs → clients</p>
            <p><span style="color:{BLUE}">Measured:</span> pressure, motor current, oil temperature and control states.
            <span style="color:{COPPER}">Warning path:</span> longer loaded operation with weakening reservoir recovery.</p>
            <p>No component is marked failed because MetroPT-3 reports only an air-leak interval.</p></div>""",
            unsafe_allow_html=True,
        )
    with tabs[2]:
        decision = campaign["decision"]
        st.metric("Promotion decision", decision["status"])
        st.write("Fit: February · Threshold: March · Observed test: four April–July episodes")
        st.json(contract["observed_evaluation"], expanded=True)
        st.caption("Headline evidence is episode-level. Row-wise accuracy is intentionally not shown.")
    with tabs[3]:
        rows = []
        for name, arm in campaign["arms"].items():
            result = arm["observed_test"]
            rows.append(
                {
                    "Arm": name.replace("_", " ").title(),
                    "Observed episodes warned": f"{result['episodes_warned_2h']}/4",
                    "False alerts/day": round(result["false_alerts_per_day"], 3),
                    "Median lead": result["median_lead_minutes"],
                    "All gates pass": all(arm.get("promotion_gates", {}).values()),
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with tabs[4]:
        st.write("Generated mechanisms: downstream leak, dryer drain held open, reduced compressor delivery.")
        st.json(campaign["synthetic_contract"], expanded=True)
        st.json(campaign["simulator"], expanded=False)
        st.caption("Synthetic rows train models only. Calibration and test contain zero generated rows.")
    with tabs[5]:
        c1, c2, c3 = st.columns(3)
        c1.metric("Observed rows", f"{profile['rows']:,}")
        c2.metric("Measured cadence", f"{profile['median_cadence_seconds']:.1f} s")
        c3.metric("Documented failures", profile["failure_episodes"])
        st.code(f"UCI DOI: {profile['source_doi']}\nSHA-256: {profile['source_sha256']}")
        st.json({"missing_by_signal": profile["missing_by_signal"], "physical_ranges": profile["physical_ranges"]})


data = load_data()
st.sidebar.image(logo(), use_container_width=True)
st.sidebar.caption("Compressor intelligence")
if data is None:
    st.title("PNEUMORA")
    st.warning("Product artifacts are not built yet. Run ingestion, campaign and product build.")
    st.stop()

contract, warnings, orders, kpis, factory, telemetry, profile, campaign = data
mode = st.sidebar.radio("View", ["Simple", "Engineering evidence"], horizontal=True)
now = replay_control(telemetry)
active = current_warning(warnings, now)
page = st.sidebar.radio("Go to", ["Now", "Maintenance", "Performance"])
st.sidebar.caption(f"Replay: {now:%d %b %Y %H:%M}")
st.sidebar.caption(f"Model: {contract['model_status']}")

if mode == "Engineering evidence":
    engineering_page(now, active, telemetry, profile, campaign, contract)
elif page == "Now":
    st.title("What needs attention now?")
    if contract["model_status"] == "NO_PROMOTION":
        st.info(
            "No predictive model passed the frozen test. This replay uses the existing "
            "low-pressure alarm, so it reacts to low air rather than claiming an early forecast."
        )
    simple_now(now, active, telemetry, warnings, orders)
elif page == "Maintenance":
    work_orders_page(orders)
else:
    factory_page(kpis, factory)
