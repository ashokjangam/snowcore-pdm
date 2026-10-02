"""TRIDENT OPS — evidence-first Predictive Maintenance and OEE Command Center."""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from modules.contracts import (  # noqa: E402
    APP_DATABASE,
    METROPT_DATABASE,
    PIADE_DATABASE,
    PIADE_LINES,
    clean_action,
    clean_line,
    evidence_label,
    metropt_timing,
    rca_prompt,
    sql_literal,
)

st.set_page_config(
    page_title="TRIDENT OPS",
    page_icon="🔱",
    layout="wide",
    initial_sidebar_state="expanded",
)

INK = "#EAF3F7"
MUTED = "#91A4B1"
TEAL = "#31D7C5"
CYAN = "#36A9E1"
AMBER = "#F2B84B"
RED = "#EF6A72"
PANEL = "#101D27"
GRID = "#223440"


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{background:
          radial-gradient(circle at 90% 0%, rgba(49,215,197,.08), transparent 26rem),
          linear-gradient(180deg,#071119 0%,#09151d 100%);}}
        [data-testid="stSidebar"] {{background:#08131b;border-right:1px solid {GRID}}}
        [data-testid="stSidebar"] p,[data-testid="stSidebar"] label {{color:{INK}!important}}
        h1,h2,h3,h4 {{letter-spacing:-.02em}}
        .trident-hero {{border:1px solid {GRID};border-radius:18px;padding:20px 22px;
          background:linear-gradient(115deg,rgba(49,215,197,.10),rgba(16,29,39,.8) 55%);
          margin-bottom:14px}}
        .trident-kicker {{font-size:11px;text-transform:uppercase;letter-spacing:.15em;color:{TEAL};font-weight:800}}
        .trident-title {{font-size:35px;font-weight:800;color:{INK};line-height:1.05;margin:5px 0 8px}}
        .trident-lede {{max-width:850px;color:#B5C4CD;font-size:15px}}
        .passport {{display:inline-flex;gap:7px;align-items:center;border:1px solid {GRID};
          border-radius:999px;padding:5px 10px;margin:2px 5px 2px 0;background:#0B1821;
          color:#C8D5DC;font-size:11px}}
        .passport b {{color:{TEAL};text-transform:uppercase;letter-spacing:.06em}}
        .firewall {{border:1px dashed {AMBER};border-radius:12px;padding:12px 14px;
          color:#E7D6AA;background:rgba(242,184,75,.06);font-size:13px}}
        .evidence-card {{border:1px solid {GRID};border-radius:14px;padding:14px 16px;
          background:{PANEL};min-height:116px}}
        .evidence-card .eyebrow {{font-size:10px;text-transform:uppercase;letter-spacing:.11em;color:{MUTED}}}
        .evidence-card .value {{font-size:25px;font-weight:800;color:{INK};margin:2px 0}}
        .evidence-card .note {{font-size:12px;color:{MUTED}}}
        .status-good {{color:{TEAL}}}.status-warn {{color:{AMBER}}}.status-bad {{color:{RED}}}
        div[data-testid="stMetric"] {{border:1px solid {GRID};border-radius:12px;padding:10px 12px;background:{PANEL}}}
        .stButton>button {{border-radius:10px;border:1px solid {GRID};font-weight:700}}
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_css()


@st.cache_resource
def active_session():
    from snowflake.snowpark.context import get_active_session

    return get_active_session()


@st.cache_data(ttl=120, show_spinner=False)
def query(label: str, sql: str) -> pd.DataFrame:
    del label
    try:
        frame = active_session().sql(sql).to_pandas()
        frame.columns = [str(column).upper() for column in frame.columns]
        return frame
    except Exception as exc:  # local preview or a missing grant
        st.warning(f"Snowflake query unavailable: {exc}")
        return pd.DataFrame()


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def pct(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}%}"
    except (TypeError, ValueError):
        return "—"


def num(value: Any, digits: int = 0) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def hero(kicker: str, title: str, lede: str) -> None:
    st.markdown(
        f"""<div class="trident-hero"><div class="trident-kicker">{esc(kicker)}</div>
        <div class="trident-title">{esc(title)}</div><div class="trident-lede">{esc(lede)}</div></div>""",
        unsafe_allow_html=True,
    )


def passport(origin: str, source: str, as_of: str = "") -> None:
    label = evidence_label(origin)
    date = f"<span>· {esc(as_of)}</span>" if as_of else ""
    st.markdown(
        f"""<span class="passport"><b>{esc(label)}</b><span>{esc(source)}</span>{date}</span>""",
        unsafe_allow_html=True,
    )


def evidence_card(label: str, value: str, note: str, tone: str = "") -> None:
    st.markdown(
        f"""<div class="evidence-card"><div class="eyebrow">{esc(label)}</div>
        <div class="value {esc(tone)}">{esc(value)}</div><div class="note">{esc(note)}</div></div>""",
        unsafe_allow_html=True,
    )


def no_join_firewall() -> None:
    st.markdown(
        """<div class="firewall"><b>NO-JOIN FIREWALL</b> · PIADE is a packaging plant;
        MetroPT is a train air compressor. They share no asset or event key. TRIDENT OPS
        presents two evidence lanes and never combines their scores, failures, OEE or work orders.</div>""",
        unsafe_allow_html=True,
    )


def piade_kpi() -> pd.DataFrame:
    return query("PIADE KPI", f"SELECT * FROM {PIADE_DATABASE}.GOLD.V_EXECUTIVE_KPI")


def fleet() -> pd.DataFrame:
    return query(
        "PIADE fleet",
        f"SELECT * FROM {PIADE_DATABASE}.GOLD.V_EXECUTIVE_FLEET ORDER BY LAST_RISK_SCORE DESC",
    )


def action_queue() -> pd.DataFrame:
    return query(
        "PIADE actions",
        f"""SELECT * FROM {PIADE_DATABASE}.GOLD.V_EXECUTIVE_ACTION_QUEUE
            ORDER BY ACTION_RANK LIMIT 30""",
    )


def page_command_center() -> None:
    hero(
        "PIADE · observed operations",
        "Where the hours go—and who should act",
        "Weighted OEE and loss ownership from two years of real packaging-line state and count logs. "
        "Risk is a next-hour ranking, not remaining useful life.",
    )
    data = piade_kpi()
    if data.empty:
        return
    row = data.iloc[0]
    a, b, c, d = st.columns(4)
    with a:
        evidence_card("Weighted OEE", pct(row.get("SITE_WEIGHTED_OEE")), "A × P × Q from summed site totals")
    with b:
        evidence_card("Availability", pct(row.get("AVAILABILITY")), f"{num(row.get('BREAKDOWN_HOURS'),1)} fault h")
    with c:
        evidence_card("Waiting / idle", f"{num(row.get('IDLE_HOURS'),1)} h", "A planning loss, not automatically maintenance")
    with d:
        evidence_card("Model vs persistence", num(row.get("MODEL_AUC"), 3), f"baseline AUC {num(row.get('BASELINE_AUC'),3)}")
    passport(str(row.get("DATA_ORIGIN")), "SNOWCORE_REAL.GOLD.V_EXECUTIVE_KPI", str(row.get("DATA_AS_OF", "")))

    view = fleet()
    if not view.empty:
        st.markdown("### Fleet evidence radar")
        cols = st.columns(5)
        for index, asset in view.sort_values("MACHINE_CODE").reset_index(drop=True).iterrows():
            with cols[index % 5]:
                trust = str(asset.get("MODEL_VS_BASELINE_TRUST", "")).replace("_", " ").title()
                evidence_card(
                    str(asset.get("MACHINE_CODE")),
                    pct(asset.get("OEE")),
                    f"{asset.get('RISK_BAND','—')} · score {num(asset.get('LAST_RISK_SCORE'),3)} · {trust}",
                    "status-warn" if str(asset.get("RISK_BAND")) in {"ELEVATED", "HIGH"} else "status-good",
                )
        fig = px.scatter(
            view,
            x="OEE",
            y="LAST_RISK_SCORE",
            size="BREAKDOWN_HOURS",
            color="RISK_BAND",
            hover_name="MACHINE_CODE",
            color_discrete_map={"LOW": TEAL, "MODERATE": CYAN, "ELEVATED": AMBER, "HIGH": RED},
            labels={"OEE": "Weighted OEE", "LAST_RISK_SCORE": "Next-hour risk rank"},
        )
        fig.update_layout(height=340, paper_bgcolor=PANEL, plot_bgcolor=PANEL, font_color=INK)
        st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})

    queue = action_queue()
    if not queue.empty:
        st.markdown("### Ownership before optimisation")
        st.caption(
            "Scenario exposure only · euro values combine observed operations with synthetic ERP assumptions; "
            "they are prioritisation aids, not measured financial loss."
        )
        owner = queue.groupby("OWNER_FUNCTION", as_index=False)["PRODUCTION_EXPOSURE_EUR"].sum()
        fig = px.bar(
            owner,
            x="OWNER_FUNCTION",
            y="PRODUCTION_EXPOSURE_EUR",
            color="OWNER_FUNCTION",
            labels={"PRODUCTION_EXPOSURE_EUR": "Scenario production exposure (€)"},
        )
        fig.update_layout(height=260, showlegend=False, paper_bgcolor=PANEL, plot_bgcolor=PANEL, font_color=INK)
        st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})
        st.dataframe(
            queue[["PRIORITY", "OWNER_FUNCTION", "MACHINE_CODE", "RISK_STATE", "EVIDENCE", "RECOMMENDED_ACTION"]],
            hide_index=True,
            width="stretch",
        )
    no_join_firewall()


def root_causes(line: str) -> pd.DataFrame:
    line = clean_line(line)
    return query(
        f"RCA {line}",
        f"""SELECT * FROM {PIADE_DATABASE}.GOLD.V_ROOT_CAUSE_ALARM
            WHERE MACHINE_CODE={sql_literal(line)}
            ORDER BY RANK_IN_LINE LIMIT 10""",
    )


def record_action(line: str, source_key: str, action: str, note: str) -> Any:
    line = clean_line(line)
    action = clean_action(action)
    result = active_session().sql(
        f"""CALL {APP_DATABASE}.OPS.RECORD_TRIAGE_ACTION(
            'PLANT_B', {sql_literal(line)}, {sql_literal(source_key)},
            {sql_literal(action)}, {sql_literal(note)}, CURRENT_USER())"""
    ).collect()
    query.clear()
    return result[0][0] if result else None


def cortex_explanation(line: str, facts: pd.DataFrame) -> dict[str, Any]:
    records = facts.head(5).where(pd.notna(facts), None).to_dict(orient="records")
    prompt = rca_prompt(line, records)
    sql = (
        "SELECT AI_COMPLETE("
        "model => 'llama3.3-70b', "
        f"prompt => {sql_literal(prompt, 12000)}, "
        "response_format => TYPE OBJECT("
        "answer STRING, evidence ARRAY(STRING), caveats ARRAY(STRING), next_question STRING)"
        ") AS RESPONSE"
    )
    raw = active_session().sql(sql).collect()[0][0]
    return raw if isinstance(raw, dict) else json.loads(str(raw))


def page_triage() -> None:
    hero(
        "Capability 2 · evidence to action",
        "Root cause without invented causes",
        "Alarm codes are anonymised. The console shows recurring patterns, asks Cortex to narrate only bounded rows, "
        "and records every operator decision in an idempotent Snowflake flight recorder.",
    )
    line = st.selectbox("Packaging line", PIADE_LINES, index=1)
    facts = root_causes(line)
    if facts.empty:
        return
    top = facts.iloc[0]
    x, y, z = st.columns(3)
    with x:
        evidence_card("Dominant alarm", str(top.get("ALARM_CODE")), f"{pct(float(top.get('SHARE_OF_LINE_BREAKDOWN_PCT',0))/100)} of fault hours")
    with y:
        evidence_card("Short-stop precursor", pct(top.get("PRECURSOR_RATE")), "same code within the prior hour")
    with z:
        evidence_card("Repeats within 24h", pct(top.get("REPEAT_24H_RATE")), "observed recurrence, not diagnosed cause")
    passport(str(top.get("DATA_ORIGIN")), "SNOWCORE_REAL.GOLD.V_ROOT_CAUSE_ALARM")

    st.markdown("#### Evidence, not a guessed component")
    top_codes = facts.head(8).sort_values("BREAKDOWN_HOURS")
    fig = px.bar(
        top_codes,
        x="BREAKDOWN_HOURS",
        y="ALARM_CODE",
        orientation="h",
        color="PATTERN",
        labels={"BREAKDOWN_HOURS": "Long-breakdown hours", "ALARM_CODE": "Anonymised alarm"},
    )
    fig.update_layout(height=310, paper_bgcolor=PANEL, plot_bgcolor=PANEL, font_color=INK)
    st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})
    st.caption("The publisher does not disclose component identity. TRIDENT OPS refuses to manufacture one.")

    if st.button("Narrate these five rows with Cortex", type="primary"):
        with st.spinner("Cortex is reading the bounded evidence packet…"):
            try:
                answer = cortex_explanation(line, facts)
                st.markdown(f"**Answer**  \n{answer.get('answer','—')}")
                for item in answer.get("evidence", []):
                    st.markdown(f"- {item}")
                if answer.get("caveats"):
                    st.warning(" · ".join(answer["caveats"]))
                if answer.get("next_question"):
                    st.info(f"Next inspection question: {answer['next_question']}")
                st.caption("Cortex received only the five rows shown here and generated no SQL.")
            except Exception as exc:
                st.error(f"Cortex could not produce a bounded answer: {exc}")

    st.markdown("### Decide, persist, reload")
    queue = action_queue()
    queue = queue[queue["MACHINE_CODE"].astype(str) == line] if not queue.empty else queue
    selected = queue.iloc[0] if not queue.empty else {}
    source_key = str(selected.get("ACTION_KEY", f"MANUAL|{line}"))
    st.caption(f"Source key: {source_key}")
    note = st.text_input("Operator note", value=f"Review evidence for {line}", max_chars=500)
    a, b, c = st.columns(3)
    for column, label, action in (
        (a, "Acknowledge evidence", "ACKNOWLEDGE"),
        (b, "Open inspection action", "INSPECTION"),
        (c, "Snooze for review", "SNOOZE"),
    ):
        if column.button(label, width="stretch"):
            try:
                result = record_action(line, source_key, action, note)
                st.success(f"Flight recorder updated: {result}")
            except Exception as exc:
                st.error(f"Action was not written: {exc}")

    log = query(
        "Flight recorder",
        f"""SELECT ACTION_ID,CREATED_AT,LAST_SEEN_AT,MACHINE_CODE,ACTION,STATUS,NOTE,ACTOR
            FROM {APP_DATABASE}.OPS.TRIAGE_ACTION
            ORDER BY CREATED_AT DESC LIMIT 20""",
    )
    if not log.empty:
        st.dataframe(log, hide_index=True, width="stretch")


def page_sensor_evidence() -> None:
    hero(
        "MetroPT · observed compressor sensors",
        "Detection evidence, not a forecast claim",
        "Pressure, motor current, oil temperature and compressor load come from a different public asset. "
        "The frozen detector is CROSS_VALIDATED_NOT_PROMOTED and usually alerts after the leak starts.",
    )
    failures = query("MetroPT failures", f"SELECT * FROM {METROPT_DATABASE}.CORE.FAILURES ORDER BY START_TS")
    alerts = query("MetroPT alerts", f"SELECT * FROM {METROPT_DATABASE}.ML.ALERTS ORDER BY RAISED_AT")
    if failures.empty:
        return
    labels = [
        metropt_timing(row.get("COPILOT_MINUTES_AFTER_START"), row.get("ONSET_PRECISION"))
        for _, row in failures.iterrows()
    ]
    failures = failures.copy()
    failures["TIMING"] = [value for value, _ in labels]
    failures["LANE"] = [lane.upper() for _, lane in labels]
    detector_minutes = pd.to_numeric(failures["COPILOT_MINUTES_AFTER_START"], errors="coerce")
    stamped = int(detector_minutes.notna().sum())
    at_or_after = int((detector_minutes.dropna() >= 0).sum())
    before = int((detector_minutes.dropna() < 0).sum())
    lps_stamped = int(pd.to_numeric(failures["LPS_MINUTES_AFTER_START"], errors="coerce").notna().sum())

    a, b, c, d = st.columns(4)
    with a:
        evidence_card("Model status", "NO PROMOTION", "No learned before-onset model passed", "status-bad")
    with b:
        evidence_card("Logged episodes", str(len(failures)), "MetroPT-3 development records shown below")
    with c:
        evidence_card(
            "Detector timestamps",
            str(stamped),
            f"{at_or_after} at/after onset; {before} before onset in this population",
        )
    with d:
        evidence_card("Low-pressure timestamps", str(lps_stamped), "baseline timestamps in the same rows")
    passport("OBSERVED_METROPT3", "PNEUMORA.CORE.FAILURES + ML.ALERTS", "2020–2022")

    points = []
    for _, row in failures.iterrows():
        points.append(
            {
                "id": row["FAILURE_ID"],
                "source": "TRIDENT detector",
                "minutes": row["COPILOT_MINUTES_AFTER_START"],
            }
        )
        if pd.notna(row.get("LPS_MINUTES_AFTER_START")):
            points.append({"id": row["FAILURE_ID"], "source": "Low-pressure alarm", "minutes": row["LPS_MINUTES_AFTER_START"]})
    chart_data = pd.DataFrame(points)
    if not chart_data.empty:
        fig = px.scatter(
            chart_data,
            x="minutes",
            y="id",
            color="source",
            symbol="source",
            color_discrete_map={"TRIDENT detector": TEAL, "Low-pressure alarm": RED},
            labels={"minutes": "Signed minutes versus logged failure start", "id": "Failure"},
        )
        fig.add_vline(x=0, line_dash="dash", line_color=AMBER, annotation_text="logged onset")
        fig.update_layout(height=320, paper_bgcolor=PANEL, plot_bgcolor=PANEL, font_color=INK)
        st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})
    display_failures = failures[
        ["FAILURE_ID", "REPORT", "START_TS", "COPILOT_FIRST", "TIMING", "LANE", "LPS_FIRST"]
    ].rename(columns={"COPILOT_FIRST": "DETECTOR_FIRST"})
    st.dataframe(display_failures, hide_index=True, width="stretch")
    if not alerts.empty:
        st.caption(
            f"Development track: {len(alerts[alerts['SOURCE']=='copilot'])} TRIDENT detector alerts; "
            f"{len(alerts[(alerts['SOURCE']=='copilot') & alerts['FAILURE_ID'].isna()])} matched no reported failure."
        )
    no_join_firewall()


def page_model_evidence() -> None:
    hero(
        "Capability 1 · model accountability",
        "A model earns a place beside its baseline",
        "TRIDENT OPS exposes what was selected, what was held out, and whether an automated inspection beat random timing. "
        "Promotion eligibility is not the same as production promotion.",
    )
    champion = query(
        "PIADE champion",
        f"SELECT * FROM {PIADE_DATABASE}.ML.V_PIADE_RESEARCH_CHAMPION LIMIT 1",
    )
    orders = query(
        "PIADE risk orders",
        f"SELECT * FROM {PIADE_DATABASE}.GOLD.V_RISK_WORK_ORDER_SUMMARY WHERE SCOPE='FLEET'",
    )
    if champion.empty:
        return
    row = champion.iloc[0]
    a, b, c, d = st.columns(4)
    with a:
        evidence_card("Rolling-validation AUC", num(row.get("CHAMPION_MEAN_AUC"), 4), f"baseline {num(row.get('BASELINE_MEAN_AUC'),4)}")
    with b:
        evidence_card("Blind top-decile precision", pct(row.get("REUSED_HOLDOUT_TOP10_PRECISION")), "December 2021; read after selection")
    with c:
        evidence_card("Trials", num(row.get("EVALUATED_TRIALS")), f"{row.get('MODEL_FAMILY','—')} champion")
    with d:
        evidence_card("Applied to production", str(row.get("CONTRACT_APPLIED_TO_PRODUCTION")), "human-controlled contract")
    passport("MODEL", "SNOWCORE_REAL.ML.V_PIADE_RESEARCH_CHAMPION", "blind holdout: Dec 2021")

    if not orders.empty:
        result = orders.iloc[0]
        st.markdown("### Replay of automated inspections")
        x, y, z = st.columns(3)
        x.metric("Orders raised", num(result.get("AUTO_WORK_ORDERS")))
        y.metric("Confirmed within 4h", num(result.get("CONFIRMED_WITHIN_4H")), pct(result.get("HIT_RATE")))
        z.metric("Lift over random timing", f"{num(result.get('LIFT_VS_RANDOM'),2)}×", f"coverage {pct(result.get('COVERAGE_RATE'))}")
        st.warning(
            "These are synthetic IT orders replayed against observed stops. A hit is not proof that inspection prevented downtime."
        )
    st.info(
        "The 25-trial search improved mean AUC by roughly 0.0001 over the baseline. "
        "The practical ceiling is missing signal, not another algorithm."
    )


def page_flight_recorder() -> None:
    hero(
        "Capability 3 · auditability",
        "The black box remembers the decision",
        "Every operator action is stored with a deterministic idempotency key, source action, user and timestamp. "
        "A double click returns the existing action instead of creating a duplicate.",
    )
    log = query(
        "Full flight recorder",
        f"""SELECT ACTION_ID,IDEMPOTENCY_KEY,CREATED_AT,LAST_SEEN_AT,PLANT_CODE,MACHINE_CODE,
                   SOURCE_KEY,ACTION,STATUS,NOTE,ACTOR,DATA_ORIGIN
            FROM {APP_DATABASE}.OPS.TRIAGE_ACTION ORDER BY CREATED_AT DESC LIMIT 200""",
    )
    if log.empty:
        st.info("No operator actions have been recorded yet.")
    else:
        st.dataframe(log, hide_index=True, width="stretch")
    no_join_firewall()
    st.markdown("### Evidence contract")
    st.markdown(
        """
        - **Observed:** copied from the published source.
        - **Derived:** deterministic calculation from observed rows.
        - **Model:** evaluated output with a named holdout and baseline.
        - **Scenario:** invented ERP, work-order history or money; never presented as fact.
        - **Operator-entered:** a real action taken in this prototype.
        """
    )
    st.caption("Cross-plant questions must be split into two questions. Cortex is never given mixed-plant evidence.")


PAGES = {
    "Command Center": page_command_center,
    "Triage + cited RCA": page_triage,
    "Sensor Evidence": page_sensor_evidence,
    "Model Evidence": page_model_evidence,
    "Flight Recorder": page_flight_recorder,
}

with st.sidebar:
    st.markdown("## 🔱 TRIDENT OPS")
    st.caption("Three capabilities. Two evidence lanes. Zero fabricated joins.")
    page = st.radio("Mission", list(PAGES), label_visibility="collapsed")
    st.markdown("---")
    st.markdown("**Evidence lanes**")
    st.caption("PIADE · packaging operations and OEE")
    st.caption("MetroPT · compressor sensor evidence")
    st.markdown("---")
    st.caption("TRidents · CoCo CLI Hackathon GCC Edition")

st.title(page)
PAGES[page]()
