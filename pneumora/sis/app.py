"""Pneumora early air-leak predictor — Streamlit in Snowflake.

Reads observed MetroPT telemetry and frozen study results. Writes go through
PNEUMORA.OPS.RECORD_ACTION, CREATE_WORK_ORDER and SET_WORK_ORDER_STATUS; outside
Snowflake they go to data/local_ops.json for the local preview.
"""

from __future__ import annotations

import calendar
import hashlib
import html
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from status_rules import status_at  # noqa: E402

LOCAL_DATA = HERE.parent / "data" / "snowflake"
DATABASE = "PNEUMORA"
INK, PAPER, CARD, COPPER, BLUE, LOW, OK, MUTED = "#1b2327", "#f3efe8", "#fffdf9", "#c56b3c", "#2f95c4", "#8d3424", "#2c7a62", "#6d645c"
TABLES = {
    "telemetry": "CORE.TELEMETRY_5M",
    "failures": "CORE.FAILURES",
    "zoom": "ML.FAILURE_ZOOM",
    "alerts": "ML.ALERTS",
    "evidence": "ML.EVIDENCE",
    "orders": "OPS.WORK_ORDERS",
    "parts": "OPS.PARTS",
    "crew": "OPS.TECHNICIANS",
    "kpis": "CORE.DAILY_KPIS",
    "factory": "OPS.FACTORY_SCENARIO",
    "cases": "ML.PREDICTION_CASES",
    "case_zoom": "ML.PREDICTION_ZOOM",
}
TIME_COLUMNS = {"ts", "start_ts", "end_ts", "removal_deadline", "copilot_first", "lps_first", "raised_at", "cleared_at", "created_at", "date",
                "first_alert", "alarm_first", "last_useful_alert"}
LOCAL_OPS = HERE.parent / "data" / "local_ops.json"
STATUS_LABELS = {"ready": "Ready", "progress": "In progress", "parts": "Waiting for parts", "done": "Done", "dismissed": "Dismissed"}
KIND_LABELS = {"air_leak": "Air leak", "oil_leak": "Oil leak"}

st.set_page_config(page_title="Pneumora", page_icon="🫧", layout="wide")
st.markdown(
    f"""
    <style>
    .stApp {{ background: {PAPER}; color: {INK}; }}
    .stApp [data-testid="stMain"] h1, .stApp [data-testid="stMain"] h2, .stApp [data-testid="stMain"] h3,
    .stApp [data-testid="stMain"] h4, .stApp [data-testid="stMain"] h5 {{ color: {INK}; }}
    section[data-testid="stSidebar"] {{ background: #10161a; border-right: 1px solid #243036; }}
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ padding: 16px 16px 28px; }}
    section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{ color: #f4f1ea; }}
    section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{ color: #d7e4e8; font-size: 13px; font-weight: 650; }}
    section[data-testid="stSidebar"] h3 {{
        margin: 22px 0 10px; padding-top: 16px; border-top: 1px solid #2a3940;
        font-size: 12px; letter-spacing: .16em; text-transform: uppercase; color: #8fd0e0;
    }}
    section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label {{
        display: flex; align-items: center; gap: 8px; margin: 0 0 4px; padding: 8px 10px; border-radius: 10px;
    }}
    section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label p {{ color: #f4f1ea; font-size: 15px; }}
    section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked) {{
        background: #243238;
    }}
    section[data-testid="stSidebar"] [data-testid="stButton"] button {{ width: 100%; min-height: 42px; }}
    section[data-testid="stSidebar"] button p {{ color: {INK}; }}
    section[data-testid="stSidebar"] [data-baseweb="select"] > div,
    section[data-testid="stSidebar"] [data-testid="stDateInput"] input {{
        background: #1b2429; color: #f4f1ea; border-color: #3a4c53;
    }}
    .pn-hero {{ background:{CARD}; border:1px solid rgba(27,35,39,.1); border-left:8px solid var(--tone);
               border-radius:22px; padding:24px 28px; box-shadow:0 18px 50px rgba(27,35,39,.06); }}
    .pn-kicker {{ font-size:12px; letter-spacing:.16em; text-transform:uppercase; color:{MUTED}; }}
    .pn-hero h2 {{ font-family: Georgia, 'Palatino Linotype', serif; font-size:48px; line-height:1; margin:6px 0 10px; color:{INK}; }}
    .pn-lede {{ font-size:17px; color:{INK}; max-width:70ch; }}
    .pn-action {{ background:#f6f3ee; border-radius:14px; padding:12px 14px; margin-top:10px; color:{INK}; }}
    .pn-chip {{ display:inline-block; padding:4px 10px; border-radius:999px; font-size:12px; background:#e6f0ea; color:#1f5c3a; margin:6px 6px 0 0; }}
    .pn-chip.warn {{ background:#f6e3d8; color:#8a3d17; }}
    .pn-card {{ background:{CARD}; border:1px solid rgba(27,35,39,.1); border-radius:18px; padding:16px 18px; margin:10px 0; }}
    .pn-example {{ border:1.5px dashed {COPPER}; background:#fff8f3; }}
    .pn-cal {{ display:grid; grid-template-columns:repeat(7,1fr); gap:2px; font-size:11px; text-align:center; color:#dfe5e2; }}
    .pn-cal em {{ font-style:normal; color:#7f9094; }}
    .pn-cal span {{ position:relative; padding:4px 0 9px; border-radius:6px; }}
    .pn-cal span.picked {{ background:{COPPER}; color:white; }}
    .pn-cal span.off {{ color:#46555a; }}
    .pn-cal i {{ position:absolute; bottom:2px; width:5px; height:5px; border-radius:50%; }}
    .pn-cal i.f {{ background:#e0624a; left:calc(50% - 6px); }}
    .pn-cal i.c {{ background:#f0a46f; left:calc(50% + 1px); }}
    .pn-lockup {{ display:flex; align-items:center; gap:12px; margin:2px 0 8px; }}
    .pn-word {{ font-family: Arial, Helvetica, sans-serif; font-weight:700; letter-spacing:.14em; font-size:20px; line-height:1; color:#F4F1EA; }}
    .pn-brand {{ font-family: Georgia, 'Palatino Linotype', serif; font-size:34px; line-height:1; color:#f3efe8; margin:6px 0 6px; }}
    .pn-tag {{ font-size:13px; line-height:1.3; color:#d7e4e8; margin:6px 0 0; }}
    .pn-side-label {{ font-size:12px; letter-spacing:.16em; text-transform:uppercase; color:#8fd0e0; margin:18px 0 8px; }}
    .pn-legend {{ font-size:11px; color:#9aabae; }}
    .pn-legend b {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin:0 4px 0 8px; vertical-align:middle; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def snowflake_session():
    try:
        from snowflake.snowpark.context import get_active_session

        return get_active_session()
    except Exception:
        return None


def _source_stamp(key: str) -> str:
    """Part of the cache key, so a rerun cannot keep columns from an older export."""
    if snowflake_session() is not None:
        return "snowflake"
    path = LOCAL_DATA / f"{TABLES[key].split('.')[1].lower()}.csv.gz"
    if not path.exists():
        return "missing"
    stat = path.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


@st.cache_data(ttl=3600, show_spinner=False)
def _load_cached(key: str, _stamp: str) -> pd.DataFrame:
    session = snowflake_session()
    name = TABLES[key]
    if session is not None:
        frame = session.table(f"{DATABASE}.{name}").to_pandas()
    else:
        frame = pd.read_csv(LOCAL_DATA / f"{name.split('.')[1].lower()}.csv.gz")
    frame.columns = [column.lower() for column in frame.columns]
    for column in TIME_COLUMNS & set(frame.columns):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def load(key: str) -> pd.DataFrame:
    return _load_cached(key, _source_stamp(key))


def sql_text(value, limit: int = 4000) -> str:
    return "'" + str(value if value is not None else "")[:limit].replace("\\", "\\\\").replace("'", "''") + "'"


def live_query(sql: str) -> pd.DataFrame | None:
    """Run a query in Snowflake; None outside Snowflake or if the object is missing."""
    session = snowflake_session()
    if session is None:
        return None
    try:
        frame = session.sql(sql).to_pandas()
    except Exception:
        return None
    frame.columns = [column.lower() for column in frame.columns]
    return frame


def local_ops() -> dict:
    if LOCAL_OPS.exists():
        return json.loads(LOCAL_OPS.read_text(encoding="utf-8"))
    return {"orders": [], "status": {}, "actions": []}


def save_local_ops(ops: dict) -> None:
    LOCAL_OPS.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_OPS.write_text(json.dumps(ops, indent=2, default=str), encoding="utf-8")


def key_of(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in ("APU-01",) + parts).encode()).hexdigest()


def call(sql: str) -> dict:
    raw = snowflake_session().sql(sql).collect()[0][0]
    return raw if isinstance(raw, dict) else json.loads(str(raw))


def record_action(source_key: str, action: str, note: str) -> dict:
    if snowflake_session() is not None:
        return call(f"CALL {DATABASE}.OPS.RECORD_ACTION({sql_text(source_key, 120)}, {sql_text(action, 20)}, {sql_text(note, 500)}, CURRENT_USER())")
    ops, key = local_ops(), key_of(source_key, action)
    now = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    existing = next((a for a in ops["actions"] if a["key"] == key), None)
    if existing:
        existing["last_seen_at"], existing["note"] = now, note or existing["note"]
    else:
        existing = {"key": key, "action_id": f"PN-ACT-{key[:16]}", "created_at": now, "last_seen_at": now, "source_key": source_key,
                    "action": action, "status": "DISMISSED" if action == "DISMISS" else "OPEN", "note": note, "actor": "local preview"}
        ops["actions"].append(existing)
    save_local_ops(ops)
    return {"ok": True, "deduplicated": existing["created_at"] != existing["last_seen_at"], **existing}


def action_log(limit: int = 15) -> pd.DataFrame:
    live = live_query(
        f"SELECT ACTION_ID, CREATED_AT, LAST_SEEN_AT, SOURCE_KEY, ACTION, STATUS, NOTE, ACTOR "
        f"FROM {DATABASE}.OPS.ACTION_LOG ORDER BY LAST_SEEN_AT DESC LIMIT {int(limit)}"
    )
    if live is not None:
        return live
    rows = pd.DataFrame(local_ops()["actions"])
    return rows.drop(columns="key").sort_values("last_seen_at", ascending=False).head(limit) if not rows.empty else rows


def create_work_order(source_key: str, priority: str, problem: str, action: str, technician: str, part: str,
                      note: str, at: pd.Timestamp) -> dict:
    """Same source and problem returns the existing order instead of opening a duplicate."""
    at_text = pd.Timestamp(at).strftime("%Y-%m-%d %H:%M:%S")
    if snowflake_session() is not None:
        return call(
            f"CALL {DATABASE}.OPS.CREATE_WORK_ORDER({sql_text(source_key, 120)}, {sql_text(at_text, 19)}, {sql_text(priority, 20)}, "
            f"{sql_text(problem, 300)}, {sql_text(action, 300)}, {sql_text(technician, 80)}, {sql_text(part, 80)}, "
            f"{sql_text(note, 500)}, CURRENT_USER())"
        )
    ops, key = local_ops(), key_of(source_key or at_text, problem)
    order_id = f"PN-WO-U{key[:6].upper()}"
    if any(o["order_id"] == order_id for o in ops["orders"]):
        return {"ok": True, "order_id": order_id, "deduplicated": True}
    ops["orders"].append({"order_id": order_id, "warning_id": source_key or None, "created_at": at_text, "priority": priority,
                          "problem": problem, "action": action, "technician": technician, "part": part, "status": "ready",
                          "asset": "APU-01", "note": note, "data_origin": "OPERATOR_ENTRY"})
    save_local_ops(ops)
    return {"ok": True, "order_id": order_id, "deduplicated": False}


def set_order_status(order_id: str, status: str, note: str) -> dict:
    if status not in STATUS_LABELS:
        return {"ok": False, "error": "Unknown status"}
    if snowflake_session() is not None:
        return call(f"CALL {DATABASE}.OPS.SET_WORK_ORDER_STATUS({sql_text(order_id, 40)}, {sql_text(status, 20)}, {sql_text(note, 500)}, CURRENT_USER())")
    ops = local_ops()
    ops["status"][order_id] = status
    save_local_ops(ops)
    return {"ok": True, "order_id": order_id, "status": status}


def work_orders() -> pd.DataFrame:
    frame = live_query(f"SELECT * FROM {DATABASE}.OPS.WORK_ORDERS")
    if frame is None:
        frame = load("orders").copy()
        ops = local_ops()
        if ops["orders"]:
            frame = pd.concat([frame, pd.DataFrame(ops["orders"])], ignore_index=True)
        for order_id, status in ops["status"].items():
            frame.loc[frame["order_id"] == order_id, "status"] = status
    frame["created_at"] = pd.to_datetime(frame["created_at"], errors="coerce")
    return frame


def saved_where() -> str:
    return "Saved in Snowflake" if snowflake_session() is not None else "Saved on this computer (local preview)"


def decision_panel(source_key: str, context: str) -> None:
    st.markdown("#### What will you do?")
    st.caption(f"{context} · {saved_where()}. Pressing the same button twice never creates a duplicate.")
    note = st.text_input("Note for the crew", value="", max_chars=500, key=f"note-{source_key}",
                         placeholder="e.g. Listen for leaks at the dryer drain before the next run")
    columns = st.columns(4)
    if columns[0].button("Create work order", key=f"WO-{source_key}", type="primary", width="stretch"):
        match = COPILOT_ALERTS[COPILOT_ALERTS["alert_id"] == source_key]
        minutes = float(match.iloc[0]["peak_loaded_minutes"]) if not match.empty and pd.notna(match.iloc[0]["peak_loaded_minutes"]) else None
        problem = leak_sentence(minutes) if minutes is not None else "The compressor is working without its normal rests: possible air leak."
        result = create_work_order(source_key, "urgent", problem,
                                   "Walk the air path: hoses, couplings, client pipes and the dryer drain.",
                                   load("crew")["name"].iloc[0], load("parts")["name"].iloc[0], note, current_moment())
        if result.get("ok"):
            st.success(f"{'Already open' if result.get('deduplicated') else 'Opened'} work order {result['order_id']}. See the Work orders page.")
        else:
            st.warning(result.get("error", "Not saved"))
    for column, label, action in zip(columns[1:], ("Acknowledge", "Inspect", "Dismiss"), ("ACKNOWLEDGE", "INSPECT", "DISMISS")):
        if column.button(label, key=f"{action}-{source_key}", width="stretch"):
            result = record_action(source_key, action, note)
            if result.get("ok"):
                verb = "Updated" if result.get("deduplicated") else "Saved"
                st.success(f"{verb}: {result['action']} · {result['action_id']}")
            else:
                st.warning(result.get("error", "Not saved"))
    log = action_log()
    if not log.empty:
        with st.expander(f"Decision log ({len(log)})"):
            st.dataframe(log, hide_index=True, width="stretch")


def cortex_failure_answer(packet: dict) -> dict:
    prompt = (
        "You explain a compressor failure to a maintenance crew. Use ONLY the JSON facts below. "
        "Quote the field name for every number you use. Do not name a failed component unless the 'report' field names it. "
        "answer: two plain sentences for the crew saying what the compressor did, and whether Pneumora warned before the "
        "logged start or once the failure was under way; never a heading. "
        "evidence: one item per number used, each naming its field. "
        "caveats: what these facts cannot tell us, such as where the leak is. "
        "If onset_precision is 'day', say the timing before or after onset is unknown. "
        "next_check must start with 'At the next inspection,' and name one physical leak check, such as a leak-down "
        "test or listening for escaping air at fittings and drain valves; never a data check. "
        "Facts: " + json.dumps(packet, default=str)
    )
    sql = (
        "SELECT AI_COMPLETE(model => 'llama3.3-70b', "
        f"prompt => {sql_text(prompt, 12000)}, "
        "response_format => TYPE OBJECT(answer STRING, evidence ARRAY(STRING), caveats ARRAY(STRING), next_check STRING)) AS R"
    )
    raw = snowflake_session().sql(sql).collect()[0][0]
    return raw if isinstance(raw, dict) else json.loads(str(raw))


@st.cache_data(ttl=3600, show_spinner=False)
def documents() -> dict:
    frame = load("evidence")
    return {row.doc_key: json.loads(row.doc_json) for row in frame.itertuples()}


@st.cache_data(ttl=3600, show_spinner=False)
def telemetry_indexed() -> pd.DataFrame:
    frame = load("telemetry").set_index("ts").sort_index()
    frame["copilot_flag"] = frame["copilot_flag"].astype(str).str.lower().isin({"true", "1"})
    return frame


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def when(value) -> str:
    return "—" if value is None or pd.isna(value) else pd.Timestamp(value).strftime("%d %b %H:%M")


def span(minutes: float) -> str:
    return f"{minutes / 60:.1f} h" if abs(minutes) >= 120 else f"{abs(minutes):.0f} min"


def leak_sentence(minutes: float) -> str:
    shown = f"{minutes / 60:.1f} hours" if minutes >= 120 else f"{minutes:.0f} minutes"
    return f"The compressor ran {shown} without a rest. A healthy run is about 2 minutes, so air may be leaking."


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})


def chart_layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=70, r=30, t=50, b=60), paper_bgcolor=CARD, plot_bgcolor=CARD,
        font=dict(color=INK, size=12), legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0), hovermode="x unified",
    )
    fig.update_xaxes(automargin=True, tickfont=dict(color=INK, size=11), title_font=dict(color=INK, size=12))
    fig.update_yaxes(automargin=True, tickfont=dict(color=INK, size=11), title_font=dict(color=INK, size=12))
    return fig


# ---------- replay state ----------
TELEMETRY = telemetry_indexed()
RANGE_START, RANGE_END = TELEMETRY.index.min(), TELEMETRY.index.max()
ALERTS = load("alerts")
FAILURES = load("failures").sort_values("start_ts")
COPILOT_ALERTS = ALERTS[ALERTS["source"] == "copilot"].sort_values("raised_at")
DOCS = documents()
SUMMARY = DOCS["track_summary"]
PERSISTENCE = int(SUMMARY["persistence_minutes"])


def marks() -> pd.DataFrame:
    failure_marks = pd.DataFrame({
        "kind": "failure", "id": FAILURES["failure_id"], "start": FAILURES["start_ts"], "end": FAILURES["end_ts"],
        "label": "Reported failure " + FAILURES["failure_id"] + " · " + FAILURES["report"],
    })
    copilot_marks = pd.DataFrame({
        "kind": "copilot", "id": COPILOT_ALERTS["alert_id"], "start": COPILOT_ALERTS["raised_at"], "end": COPILOT_ALERTS["cleared_at"],
        "label": "Leak detector alert " + COPILOT_ALERTS["alert_id"] + COPILOT_ALERTS["failure_id"].fillna("").map(lambda f: f" (on {f})" if f else " (no reported failure)"),
    })
    return pd.concat([failure_marks, copilot_marks], ignore_index=True).sort_values("start").reset_index(drop=True)


MARKS = marks()


def ceil5(moment: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(moment).ceil("5min")


def set_moment(moment: pd.Timestamp) -> None:
    moment = ceil5(moment)
    st.session_state["replay_day"] = moment.date()
    st.session_state["replay_time"] = moment.time()


if "replay_day" not in st.session_state:
    set_moment(pd.Timestamp("2020-06-06 20:30"))


def current_moment() -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(st.session_state["replay_day"], st.session_state["replay_time"]))


def jump(direction: int) -> None:
    now = current_moment()
    starts = MARKS["start"].map(ceil5)
    target = starts[starts > now].min() if direction > 0 else starts[starts < now].max()
    if pd.notna(target):
        set_moment(target)
        st.session_state["page"] = "What needs attention"


def jump_to_event() -> None:
    choice = st.session_state.get("event_pick")
    if choice and choice in EVENT_OPTIONS:
        set_moment(EVENT_OPTIONS[choice])
        st.session_state["page"] = "What needs attention"


EVENT_OPTIONS = {f"{when(row.start)} · {row.label}": row.start for row in MARKS.itertuples()}


def month_calendar(day: date) -> str:
    year, month = day.year, day.month
    first_weekday, days = calendar.monthrange(year, month)
    month_start = pd.Timestamp(year=year, month=month, day=1)
    month_end = month_start + pd.offsets.MonthBegin(1)
    inside = MARKS[(MARKS["start"] < month_end) & (MARKS["end"] >= month_start)]
    cells = [f"<em>{w}</em>" for w in "MTWTFSS"] + ["<span></span>"] * first_weekday
    for d in range(1, days + 1):
        start = pd.Timestamp(year=year, month=month, day=d)
        hits = inside[(inside["start"] < start + pd.Timedelta(days=1)) & (inside["end"] >= start)]
        kinds = set(hits["kind"])
        off = start.date() < RANGE_START.date() or start.date() > RANGE_END.date()
        classes = " ".join(c for c in ["picked" if start.date() == day else "", "off" if off else ""] if c)
        dots = ("<i class='f'></i>" if "failure" in kinds else "") + ("<i class='c'></i>" if "copilot" in kinds else "")
        cells.append(f"<span class='{classes}'>{d}{dots}</span>")
    return (f"<div class='pn-cal'>{''.join(cells)}</div>"
            "<div class='pn-legend'><b style='background:#e0624a'></b>Reported failure<b style='background:#f0a46f'></b>Leak detector alert</div>")


def day_strip(day: date, moment: pd.Timestamp) -> go.Figure:
    start = pd.Timestamp(day)
    end = start + pd.Timedelta(days=1)
    fig = go.Figure()
    for row in MARKS[(MARKS["start"] < end) & (MARKS["end"] >= start)].itertuples():
        x0, x1 = max(row.start, start), min(max(row.end, row.start + pd.Timedelta(minutes=10)), end)
        y0, y1 = (0, 1) if row.kind == "failure" else (0.25, 0.75)
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1, line_width=0,
                      fillcolor="rgba(224,98,74,.75)" if row.kind == "failure" else "#f0a46f")
    fig.add_shape(type="line", x0=moment, x1=moment, y0=-0.2, y1=1.2, line=dict(color="white", width=2))
    fig.update_xaxes(type="date", range=[start, end], tickformat="%H:%M", dtick=6 * 3600 * 1000, color="#9aabae", showgrid=False)
    fig.update_yaxes(visible=False, range=[-0.2, 1.2])
    fig.update_layout(height=80, margin=dict(l=6, r=6, t=4, b=22), paper_bgcolor="#12181b", plot_bgcolor="#1c2529", showlegend=False)
    return fig


# ---------- sidebar ----------
PAGES = ["What needs attention", "Leak copilot", "Work orders", "Compressor health", "Engineering evidence"]
if st.session_state.get("page") not in PAGES:
    st.session_state["page"] = PAGES[0]
MARK = """<svg viewBox="20 28 270 250" width="58" height="54" aria-hidden="true">
<path d="M151 28C84 28 31 82 31 151C31 220 84 272 151 272C200 272 243 244 263 202" fill="none" stroke="#F4F1EA" stroke-width="15" stroke-linecap="round"/>
<path d="M151 59C101 59 62 99 62 151C62 202 101 241 151 241C187 241 219 220 233 189" fill="none" stroke="#76C9F0" stroke-width="11" stroke-linecap="round"/>
<path d="M151 91C119 91 94 117 94 151C94 184 119 210 151 210C174 210 195 197 204 177" fill="none" stroke="#F4F1EA" stroke-width="8" stroke-linecap="round"/>
<path d="M151 151H274" fill="none" stroke="#E2A17C" stroke-width="7" stroke-linecap="round"/>
<circle cx="151" cy="151" r="9" fill="#76C9F0"/>
<circle cx="274" cy="151" r="7" fill="#E2A17C"/>
</svg>"""
with st.sidebar:
    st.markdown(
        f"<div class='pn-lockup'>{MARK}<div><div class='pn-word'>PNEUMORA</div><div class='pn-tag'>Early air-leak copilot</div></div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div class='pn-side-label'>Pages</div>", unsafe_allow_html=True)
    page = st.radio(
        "Page",
        PAGES,
        key="page", label_visibility="collapsed",
    )
    st.markdown("### Replay")
    left, right = st.columns(2)
    left.button("‹ Previous alert", on_click=jump, args=(-1,), width="stretch")
    right.button("Next alert ›", on_click=jump, args=(1,), width="stretch")
    st.selectbox("Jump to an event", list(EVENT_OPTIONS), index=None, placeholder="Pick a failure or leak detector alert",
                 key="event_pick", on_change=jump_to_event)
    st.date_input("Day", min_value=RANGE_START.date(), max_value=RANGE_END.date(), key="replay_day")
    st.markdown(month_calendar(st.session_state["replay_day"]), unsafe_allow_html=True)
    st.slider("Time of day", min_value=time(0, 0), max_value=time(23, 55), step=timedelta(minutes=5), key="replay_time", format="HH:mm")
    moment = current_moment()
    show(day_strip(st.session_state["replay_day"], moment))
    st.caption(f"Replaying **{moment:%d %b %Y, %H:%M}**. Bars show failures and leak detector alerts on this day; the white line is the replay time.")


# ---------- pages ----------
def page_now() -> None:
    orders = work_orders()
    status = status_at(moment, TELEMETRY, orders, PERSISTENCE)
    tone = {"ok": OK, "watch": COPPER, "low": LOW}[status["state"]]
    chip = (f"<span class='pn-chip {'warn' if status['copilot_active'] else ''}'>Early air-leak predictor · "
            f"{'alerting' if status['copilot_active'] else 'quiet'} · promoted, cross-validated on 3 compressors</span>")
    hero, side = st.columns([1.6, 0.8])
    with hero:
        st.markdown(
            f"""<div class="pn-hero" style="--tone:{tone}"><div class="pn-kicker">APU-01 · {moment:%d %b %H:%M}</div>
            <h2>{esc(status['title'])}</h2><div class="pn-lede">{esc(status['explanation'])}</div>
            <div class="pn-action"><b>Next action.</b> {esc(status['action'])}</div>{chip}</div>""",
            unsafe_allow_html=True,
        )
        with st.popover(f"Why “{status['title']}”?"):
            st.markdown(f"**Decided by:** {status['decided_by']}. Checks run top to bottom; the first one that fires sets the status.")
            reasons = pd.DataFrame(status["reasons"])
            reasons.insert(0, "Result", reasons.pop("triggered").map({True: "Fired", False: "OK"}))
            st.dataframe(reasons.rename(columns=str.capitalize), hide_index=True, width="stretch")
    with side:
        st.markdown(
            f"""<div class="pn-hero" style="--tone:{BLUE}"><div class="pn-kicker">Time until air is low</div>
            <h2 style="font-size:34px">{esc(status['estimate'])}</h2><div class="pn-lede" style="font-size:14px">{esc(status['estimate_note'])}</div></div>""",
            unsafe_allow_html=True,
        )
    question_box(
        {"status": status["title"], "explanation": status["explanation"], "minutes_without_a_rest": status["loaded_minutes"],
         "next_action": status["action"]},
        ["Why is this the status?", "What should the crew do?"],
        f"{status['explanation']} {status['action']}",
        "now",
    )
    recent = status["recent"]
    if recent.empty:
        st.info("No readings in the four hours before this replay time. The train was probably powered off.")
        return
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=recent.index, y=recent["reservoirs"], name="Reservoir pressure (bar)", line=dict(color=BLUE, width=3)))
    fig.add_trace(go.Scatter(x=recent.index, y=recent["loaded_run_minutes"], name="Non-stop run (min)", line=dict(color=COPPER, width=2),
                             fill="tozeroy", fillcolor="rgba(197,107,60,.15)"), secondary_y=True)
    fig.add_hline(y=7, line=dict(color=BLUE, dash="dash"), annotation_text="7 bar low-air point")
    fig.update_yaxes(title_text="bar", secondary_y=False)
    fig.update_yaxes(title_text="minutes", secondary_y=True, rangemode="tozero")
    st.markdown("#### Recent readings (up to four hours)")
    show(chart_layout(fig, 320))
    order = status["order"]
    if order:
        st.markdown(
            f"""<div class="pn-card"><div class="pn-kicker" style="color:{LOW}">{esc(order['priority'])} · {esc(order['order_id'])}</div>
            <b>{esc(order['problem'])}</b><p><b>Check first.</b> {esc(order['action'])}</p>
            <p style="color:{MUTED};font-size:12px">{esc(order['technician'])} · {esc(order['part'])} · {esc(order['status'])} · demonstration maintenance record</p></div>""",
            unsafe_allow_html=True,
        )
    active = COPILOT_ALERTS[(COPILOT_ALERTS["raised_at"] <= moment) & (COPILOT_ALERTS["cleared_at"].fillna(moment) >= moment)]
    if not active.empty:
        decision_panel(str(active.iloc[-1]["alert_id"]), "leak detector alert active at this replay time")
    elif order:
        decision_panel(str(order["order_id"]), "open demonstration work order")


def timeline() -> go.Figure:
    fig = go.Figure()
    for row in FAILURES.itertuples():
        fig.add_shape(type="rect", x0=row.start_ts, x1=max(row.end_ts, row.start_ts + pd.Timedelta(hours=8)), y0=2.6, y1=3.4,
                      fillcolor=LOW, line_width=0)
    fig.add_trace(go.Scatter(x=FAILURES["start_ts"], y=[3] * len(FAILURES), mode="text", text=FAILURES["failure_id"],
                             textposition="top center", name="Reported failure", hovertext=FAILURES["report"], showlegend=False))
    caught = COPILOT_ALERTS["outcome"] == "caught_in_time"
    for mask, name, fill in ((caught, "Pneumora alert on a real failure", COPPER), (~caught, "Pneumora alert, no failure reported", CARD)):
        rows = COPILOT_ALERTS[mask]
        fig.add_trace(go.Scatter(
            x=rows["raised_at"], y=[2] * len(rows), mode="markers", name=name,
            marker=dict(size=13, color=fill, line=dict(color=COPPER, width=2)),
            text=rows["alert_id"] + " · " + rows["failure_id"].fillna("no failure reported"), hovertemplate="%{text}<br>%{x}<extra></extra>",
        ))
    chart_layout(fig, 280)
    fig.update_yaxes(tickvals=[2, 3], ticktext=["Pneumora", "Reported failures"], range=[1.4, 3.9], showgrid=False)
    fig.update_xaxes(showgrid=True, gridcolor="#efeae3", tickformat="%b %Y")
    fig.update_layout(hovermode="closest", margin=dict(l=170, r=20, t=60, b=50))
    return fig


def flags(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    for column in columns:
        frame[column] = frame[column].astype(str).str.lower().isin({"true", "1"})
    return frame


CASES = flags(load("cases"), ("predicted_in_time", "alarm_in_time")).sort_values("case_id").reset_index(drop=True)
CASE_ZOOM = flags(load("case_zoom"), ("alerting", "alarm_on"))


def case_label(case: pd.Series) -> str:
    return f"{case['event_id']} · {KIND_LABELS.get(case['kind'], case['kind'])} · compressor {case['case_id'][0]}"


def hours_text(minutes) -> str:
    return "missed" if minutes is None or pd.isna(minutes) else f"{minutes / 60:.1f} h"


def scoreboard() -> go.Figure:
    labels = [case_label(case) for _, case in CASES.iterrows()]
    fig = go.Figure()
    minutes = CASES["minutes_before_end"].where(CASES["predicted_in_time"])
    fig.add_trace(go.Bar(
        y=labels, x=(minutes / 60).fillna(0), orientation="h", name="Pneumora", marker_color=COPPER,
        text=[hours_text(m) for m in minutes], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>Pneumora: %{text}<extra></extra>",
    ))
    chart_layout(fig, 480)
    fig.update_layout(barmode="group", hovermode="closest", bargap=0.3, margin=dict(l=210, r=70, t=60, b=60))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title_text="Hours of warning before the train had to come out of service", rangemode="tozero", showgrid=True, gridcolor="#efeae3")
    return fig


def case_chart(case: pd.Series) -> go.Figure:
    points = CASE_ZOOM[CASE_ZOOM["case_id"] == case["case_id"]].sort_values("ts")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=0.06,
                        specs=[[{"secondary_y": True}], [{}]])
    fig.add_vrect(x0=case["start_ts"], x1=case["end_ts"], fillcolor=LOW, opacity=0.08, line_width=0)
    fig.add_trace(go.Scatter(x=points["ts"], y=points["loaded_run_minutes"].clip(lower=0.5), name="Minutes pumping without a rest",
                             fill="tozeroy", line=dict(color=COPPER, width=1.5), fillcolor="rgba(197,107,60,.2)"), row=1, col=1)
    fig.add_trace(go.Scatter(x=points["ts"], y=points["pressure"], name="Air pressure (bar)", line=dict(color=BLUE, width=2)),
                  row=1, col=1, secondary_y=True)
    on = points[points["alerting"]]
    fig.add_trace(go.Scatter(x=on["ts"], y=[1] * len(on), mode="markers", name="Pneumora alerting", showlegend=False,
                             marker=dict(symbol="square", size=8, color=COPPER), hovertemplate="Pneumora alerting<br>%{x}<extra></extra>"),
                  row=2, col=1)
    lo, hi = points["ts"].min(), points["ts"].max()
    marks_ = [(case["start_ts"], LOW, "solid", "Failure logged"), (case["first_alert"], COPPER, "solid", "Pneumora warns"),
              (case["end_ts"], INK, "dash", "Train must be out of service")]
    for index, (x, color, dash, text) in enumerate(marks_):
        if pd.notna(x) and lo <= x <= hi:
            fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=1, xref="x", yref="paper", line=dict(color=color, dash=dash, width=2))
            fig.add_annotation(x=x, y=0.98 - index * 0.08, xref="x", yref="paper", text=text, showarrow=False, xanchor="left", xshift=4,
                               font=dict(color=color, size=11), bgcolor=CARD)
    if pd.isna(case["first_alert"]):
        fig.add_annotation(x=0.5, y=0.55, xref="paper", yref="paper", text="Pneumora did not warn on this failure",
                           showarrow=False, font=dict(color=LOW, size=16), bgcolor=CARD)
    chart_layout(fig, 480)
    ticks = [1, 2, 5, 15, 60, 240, 1000]
    fig.update_yaxes(type="log", title_text="minutes without a rest", tickvals=ticks, ticktext=[str(t) for t in ticks],
                     row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="bar", showgrid=False, row=1, col=1, secondary_y=True)
    fig.update_yaxes(tickvals=[1], ticktext=["Pneumora"], range=[0.4, 1.8], showgrid=False, row=2, col=1)
    fig.update_xaxes(tickformat="%d %b<br>%H:%M", row=2, col=1)
    return fig


def case_verdict(case: pd.Series) -> tuple[str, str]:
    lasted = (case["end_ts"] - case["start_ts"]).total_seconds() / 60
    if case["predicted_in_time"]:
        after = case["minutes_after_start"]
        mine = hours_text(case["minutes_before_end"])
        mine_note = f"before the train had to come off · {span(after)} {'before the failure was logged' if after < 0 else 'after it started'}"
    elif case["kind"] == "oil_leak":
        mine, mine_note = "Missed", "This was logged as an oil leak. Pneumora only watches for air leaks."
    elif lasted < 120:
        mine, mine_note = "Missed", f"It lasted {lasted:.0f} min. A useful warning has to arrive 2 h before the train comes off, which was already impossible once it started."
    else:
        mine, mine_note = "Missed", "No alert in time"
    return mine, mine_note


def tile(column, title: str, value: str, note: str, tone: str) -> None:
    column.markdown(
        f"<div class='pn-card' style='border-left:6px solid {tone}'><div class='pn-kicker'>{esc(title)}</div>"
        f"<div style='font-size:32px;font-family:Georgia,serif;line-height:1.2'>{esc(value)}</div>"
        f"<div style='color:{MUTED};font-size:13px'>{esc(note)}</div></div>",
        unsafe_allow_html=True,
    )


def page_track() -> None:
    pred = DOCS["prediction"]
    held = pred["held_out_pooled"]
    air = int((CASES["kind"] == "air_leak").sum())
    a, b, c, d = st.columns(4)
    tile(a, "Air leaks warned in time", f"{held['air_caught']} of {air}", "E2 is the one air leak with no warning", COPPER)
    tile(b, "Typical warning", f"{held['median_margin'] / 60:.1f} h", "before the train had to come off", COPPER)
    tile(c, "False alarms per healthy day", f"{held['false_per_day']:.2f}", "about one alert every 18 healthy days", OK)
    tile(d, "Also missed", "E3 and X2", "both are oil leaks, which this detector does not watch", MUTED)

    st.markdown("#### Every real failure: how much warning did each system give?")
    show(scoreboard())
    st.caption(f"{len(CASES)} reported failures on 3 real compressors. Each compressor was tested with settings tuned only on the other two.")

    st.markdown("#### Look at one failure")
    labels = {case_label(case): case["case_id"] for _, case in CASES.iterrows()}
    choice = st.radio("Failure", list(labels), horizontal=True, label_visibility="collapsed", key="case_pick")
    case = CASES[CASES["case_id"] == labels[choice]].iloc[0]
    mine, mine_note = case_verdict(case)
    left, right = st.columns(2)
    tile(left, "Pneumora", mine, mine_note, COPPER if case["predicted_in_time"] else LOW)
    tile(right, case["compressor"], KIND_LABELS.get(case["kind"], case["kind"]),
         f"logged {when(case['start_ts'])} → {when(case['end_ts'])}", BLUE)
    show(case_chart(case))
    st.caption("Red shading: the logged failure. Orange: how long the compressor pumped without its normal 2-minute rest. "
               "Blue: air pressure. Bottom strip: when Pneumora was alerting.")
    explain_with_cortex(case)
    if case["case_id"].startswith("A-"):
        target = case["first_alert"] if pd.notna(case["first_alert"]) else case["start_ts"]
        st.button(f"Replay {case['event_id']} on the status page",
                  on_click=lambda t=target: (set_moment(t), st.session_state.update(page="What needs attention")))

    st.markdown("#### Compressor A over six months: every alert, including the wrong ones")
    show(timeline())
    st.caption("Filled circle: Pneumora alert on a real failure. Hollow circle: Pneumora alert with no failure reported.")
    with st.expander(f"All {len(COPILOT_ALERTS)} Pneumora alerts on compressor A"):
        table = COPILOT_ALERTS.assign(
            Raised=COPILOT_ALERTS["raised_at"].map(when), Cleared=COPILOT_ALERTS["cleared_at"].map(when),
            Longest_run=COPILOT_ALERTS["peak_loaded_minutes"].map(lambda v: f"{v:.0f} min"),
            Outcome=COPILOT_ALERTS["outcome"].str.replace("_", " ").str.capitalize(),
            Failure=COPILOT_ALERTS["failure_id"].fillna("—"),
        )[["alert_id", "Raised", "Cleared", "Longest_run", "Outcome", "Failure"]]
        st.dataframe(table.rename(columns={"alert_id": "Alert", "Longest_run": "Longest run without a rest"}), hide_index=True, width="stretch")

    st.markdown(
        f"""<div class="pn-card"><b>Before you trust it</b><ul>
        <li><b>It predicts the breakdown, not the leak.</b> Only {pred['pre_onset_predictions']} of {len(CASES)} warnings came before the failure was logged.</li>
        <li><b>It does not catch oil leaks.</b> E3 and X2 are oil leaks, so there is no Pneumora warning on those graphs.</li>
        <li><b>All {len(CASES)} failures were seen while building it.</b> No untouched data is left, so this is cross-validation, not a blind test.</li>
        <li>Alerts with no reported failure count against Pneumora, even though some may be unlogged faults.</li></ul></div>""",
        unsafe_allow_html=True,
    )


def failure_packet(case: pd.Series) -> dict:
    points = CASE_ZOOM[CASE_ZOOM["case_id"] == case["case_id"]]
    inside = points[(points["ts"] >= case["start_ts"]) & (points["ts"] <= case["end_ts"])]
    before = points[points["ts"] < case["start_ts"]]
    resting = before.loc[before["loaded_run_minutes"] > 0, "loaded_run_minutes"]
    logged = FAILURES.set_index("failure_id")
    on_a = case["case_id"].startswith("A-") and case["event_id"] in logged.index
    percentiles = next((row for row in DOCS.get("precursor", {}).get("percentiles", [])
                        if row["unit"] == case["unit"] and row["event_id"] == case["event_id"]), {})

    def biggest(frame: pd.DataFrame, column: str, fn):
        return round(float(fn(frame[column])), 2) if not frame.empty else None

    packet = {
        "failure_id": case["event_id"], "compressor": case["compressor"],
        "report": logged.at[case["event_id"], "report"] if on_a else KIND_LABELS.get(case["kind"], case["kind"]),
        "onset_precision": logged.at[case["event_id"], "onset_precision"] if on_a else "minute",
        "logged_start": case["start_ts"], "logged_end_train_out_of_service": case["end_ts"],
        "pneumora_first_alert": case["first_alert"], "pneumora_minutes_after_logged_start": case["minutes_after_start"],
        "pneumora_minutes_before_end": case["minutes_before_end"],
        "longest_run_without_rest_minutes_during_failure": biggest(inside, "loaded_run_minutes", np.max),
        "lowest_air_pressure_bar_during_failure": biggest(inside, "pressure", np.min),
        "longest_run_without_rest_minutes_12h_before": biggest(before, "loaded_run_minutes", np.max),
        "typical_run_minutes_12h_before": round(float(resting.median()), 2) if not resting.empty else None,
        "leak_index_percentile_vs_healthy": {k.replace("pctl_", ""): v for k, v in percentiles.items() if k.startswith("pctl_")},
    }
    return {k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in packet.items()}


def plain_case_answer(case: pd.Series) -> str:
    if case["predicted_in_time"]:
        after = case["minutes_after_start"]
        when_text = "before the failure was logged" if after < 0 else "after the failure was logged"
        return (
            f"Pneumora warned {hours_text(case['minutes_before_end'])} before the train had to come out of service, "
            f"{span(abs(after))} {when_text}. The orange line is how long the compressor kept pumping without its usual "
            f"2-minute rest. A long run like that is the air-leak sign. Walk the hoses, couplings and the dryer drain."
        )
    if case["kind"] == "oil_leak":
        return (
            f"{case['event_id']} was logged as an oil leak. Pneumora only watches how long the compressor pumps without a rest, "
            "which is an air-leak sign. There is no warning line because this detector is not built to see an oil leak."
        )
    lasted = (case["end_ts"] - case["start_ts"]).total_seconds() / 60
    return (
        f"{case['event_id']} was logged as an air leak lasting {lasted:.0f} minutes. A warning only counts if it arrives "
        "at least 2 hours before the train had to come off. That deadline had already passed when the leak was logged, "
        "and Pneumora did not warn before it either. This is the one air leak in the 6-of-7 result."
    )


def ask_cortex(question: str, facts: dict) -> dict:
    prompt = (
        "You answer one question from a maintenance crew. Use ONLY the JSON facts. "
        "If the facts do not contain the answer, say what is missing. "
        "Do not name a failed component unless a report field names it. "
        "answer: two or three plain sentences. "
        "next_check: one physical check starting with 'At the next inspection,' or an empty string if the facts do not support one. "
        "Question: " + question + " Facts: " + json.dumps(facts, default=str)
    )
    sql = (
        "SELECT AI_COMPLETE(model => 'llama3.3-70b', "
        f"prompt => {sql_text(prompt, 12000)}, "
        "response_format => TYPE OBJECT(answer STRING, next_check STRING)) AS R"
    )
    raw = snowflake_session().sql(sql).collect()[0][0]
    return raw if isinstance(raw, dict) else json.loads(str(raw))


def question_box(facts: dict, suggestions: list[str], local_text: str, key: str) -> None:
    with st.expander("Ask why this happened, or what to do"):
        st.markdown(local_text)
        question = st.text_input("Ask something else", key=f"q-{key}", placeholder=suggestions[0])
        if snowflake_session() is None:
            st.caption("That answer is written from the readings. In Snowflake, the same question goes to Cortex and Cortex may only use these facts.")
            return
        chosen = question.strip() or suggestions[0]
        if st.button("Ask Cortex", key=f"cx-{key}"):
            with st.spinner("Cortex is reading only these facts…"):
                try:
                    answer = ask_cortex(chosen, facts)
                except Exception as exc:
                    st.error(f"Cortex could not answer: {exc}")
                    return
            st.markdown(f"**{answer.get('answer', '—')}**")
            if answer.get("next_check"):
                st.info(answer["next_check"])
            st.caption("Cortex received only the facts for this view. It wrote no SQL and read no other table.")


def explain_with_cortex(case: pd.Series) -> None:
    packet = failure_packet(case)
    question_box(
        packet,
        ["Why is the warning where it is?", "What should the crew check?", "Why is there no warning?"],
        plain_case_answer(case),
        case["case_id"],
    )


def page_orders() -> None:
    crew, parts = load("crew"), load("parts")
    st.caption(f"Maintenance list for compressor A. The starting orders are demonstration records, not real railway orders. {saved_where()}.")
    with st.form("new-order", clear_on_submit=True):
        st.markdown("#### Create a work order")
        sources = ["Nothing specific"] + [f"{row.alert_id} · {when(row.raised_at)}" for row in COPILOT_ALERTS.itertuples()]
        left, right = st.columns(2)
        source = left.selectbox("Raised from", sources)
        priority = right.selectbox("Priority", ["urgent", "planned"])
        problem = st.text_input("Problem", "The compressor is working without its normal rests: possible air leak.")
        action = st.text_input("What to check", "Walk the air path: hoses, couplings, client pipes and the dryer drain.")
        left, right = st.columns(2)
        technician = left.selectbox("Technician", list(crew["name"]))
        part = right.selectbox("Part to bring", list(parts["name"]))
        note = st.text_input("Note", "")
        if st.form_submit_button("Create work order", type="primary"):
            if not problem.strip():
                st.warning("Describe the problem first.")
            else:
                key = "" if source == sources[0] else source.split(" · ")[0]
                result = create_work_order(key, priority, problem.strip(), action.strip(), technician, part, note, current_moment())
                if result.get("ok"):
                    st.success(f"{'Already open' if result.get('deduplicated') else 'Created'} work order {result['order_id']}.")
                else:
                    st.warning(result.get("error", "Not saved"))

    orders = work_orders().sort_values("created_at", ascending=False)
    open_orders = orders[~orders["status"].isin(["done", "dismissed"])]
    with st.form("update-order"):
        st.markdown("#### Update an order")
        left, right = st.columns([2, 1])
        options = {f"{row.order_id} · {row.problem[:70]}": row.order_id for row in open_orders.itertuples()}
        target = left.selectbox("Order", list(options) or ["No open orders"])
        status = right.selectbox("New status", list(STATUS_LABELS), format_func=STATUS_LABELS.get, index=1)
        note = st.text_input("Note", "", key="update-note")
        if st.form_submit_button("Update order") and options:
            result = set_order_status(options[target], status, note)
            if result.get("ok"):
                st.success(f"{options[target]} is now {STATUS_LABELS[status].lower()}.")
            else:
                st.warning(result.get("error", "Not saved"))

    orders = work_orders().sort_values("created_at", ascending=False)
    is_open = ~orders["status"].isin(["done", "dismissed"])
    a, b, c, d = st.columns(4)
    a.metric("Open", int(is_open.sum()))
    b.metric("Urgent and open", int((is_open & (orders["priority"] == "urgent")).sum()))
    c.metric("Drafted by Pneumora", int(orders["order_id"].str.startswith("PN-CO-").sum()))
    d.metric("Created by you", int((orders["data_origin"] == "OPERATOR_ENTRY").sum()))
    shown = st.multiselect("Show", list(STATUS_LABELS), default=["ready", "progress", "parts"], format_func=STATUS_LABELS.get)
    view = orders[orders["status"].isin(shown)]
    st.dataframe(
        view.assign(created_at=view["created_at"].map(when), status=view["status"].map(STATUS_LABELS).fillna(view["status"]),
                    origin=view["data_origin"].map({"OPERATOR_ENTRY": "You"}).fillna("Demonstration"))
        [["order_id", "created_at", "priority", "status", "problem", "action", "technician", "part", "note", "origin"]]
        .rename(columns={"order_id": "Order", "created_at": "Opened", "priority": "Priority", "status": "Status", "problem": "Problem",
                         "action": "What to check", "technician": "Technician", "part": "Part", "note": "Note", "origin": "Created by"}),
        hide_index=True, width="stretch",
    )
    with st.expander("Parts and crew"):
        left, right = st.columns(2)
        left.dataframe(parts.drop(columns=["data_origin"]), hide_index=True, width="stretch")
        right.dataframe(crew.drop(columns=["data_origin"]), hide_index=True, width="stretch")


def failure_bands(fig: go.Figure) -> None:
    for row in FAILURES.itertuples():
        fig.add_vrect(x0=row.start_ts, x1=row.end_ts + pd.Timedelta(hours=12), fillcolor=LOW, opacity=0.18, line_width=0)


def page_health() -> None:
    st.markdown(
        "<div class='pn-card'>How hard compressor A works, day by day. A healthy compressor pumps for about two minutes, then rests. "
        "A leak makes it pump without resting. <b>Red bands are reported failures.</b></div>",
        unsafe_allow_html=True,
    )
    day = TELEMETRY.resample("D")
    daily = pd.DataFrame({
        "longest_run": day["loaded_run_minutes"].max(),
        "hours_of_data": day["reservoirs"].count() * 5 / 60,
        "alert_hours": day["copilot_flag"].sum() * 5 / 60,
    })
    seen = daily[daily["hours_of_data"] > 0]
    running = TELEMETRY.loc[TELEMETRY["loaded_run_minutes"] > 0, "loaded_run_minutes"]
    a, b, c, d = st.columns(4)
    a.metric("Days with readings", f"{len(seen)}")
    b.metric("Typical run before a rest", f"{running.median():.1f} min")
    c.metric("Days Pneumora alerted", f"{int((seen['alert_hours'] > 0).sum())}")
    d.metric("Reported failures", f"{len(FAILURES)}")

    st.markdown("#### Longest run without a rest, each day")
    runs = seen["longest_run"].clip(lower=0.5)
    fig = go.Figure(go.Scatter(x=seen.index, y=runs, mode="lines+markers", line=dict(color=COPPER, width=1.5),
                               marker=dict(size=5), name="Longest run (min)"))
    failure_bands(fig)
    fig.add_hline(y=60, line=dict(color=INK, dash="dash"), annotation_text="one hour non-stop", annotation_position="top left")
    chart_layout(fig, 320)
    top = max(float(runs.max()) * 1.5, 120)
    fig.update_yaxes(type="log", range=[np.log10(0.5), np.log10(top)], title_text="minutes",
                     tickvals=[1, 2, 5, 15, 60, 240, 1000], ticktext=["1", "2", "5", "15", "60", "240", "1000"])
    fig.update_xaxes(title_text="day", tickformat="%d %b")
    show(fig)

    st.markdown("#### Hours Pneumora was alerting, each day")
    fig = go.Figure(go.Bar(x=seen.index, y=seen["alert_hours"], marker_color=COPPER, name="Alert hours"))
    failure_bands(fig)
    chart_layout(fig, 280)
    fig.update_yaxes(title_text="hours", rangemode="tozero")
    fig.update_xaxes(title_text="day", tickformat="%d %b")
    show(fig)
    st.caption("Bars inside a red band are useful warnings. Bars outside one are false alarms.")

    st.markdown("#### Example factory score (OEE) · not measured")
    factory = load("factory")
    st.markdown(
        f"<div class='pn-card pn-example'>OEE = availability × speed × quality. This line is an <b>example factory</b> built from "
        f"stated assumptions around this compressor's downtime. It is not this train's real production or cost.</div>",
        unsafe_allow_html=True,
    )
    fig = go.Figure(go.Scatter(x=factory["date"], y=factory["oee"], line=dict(color=COPPER, width=2), name="Example OEE"))
    chart_layout(fig, 260)
    fig.update_yaxes(tickformat=".0%", title_text="example OEE")
    fig.update_xaxes(title_text="day", tickformat="%d %b")
    show(fig)


def before_onset_research() -> None:
    doc = DOCS.get("precursor")
    if not doc:
        return
    st.markdown("#### Can it warn before the leak itself starts? (research)")
    st.caption("We tried cycle physics from the raw data, multi-day drift, supervised learning, synthetic failure replays and Snowflake anomaly "
               "detection. Only F04 showed a measurable sign, about 80–95 minutes ahead; the other leaks began suddenly.")
    rows = pd.DataFrame(doc["rows"]).rename(columns={
        "approach": "Approach", "warned_before_onset": f"Warned in the {doc['pre_onset_hours']} h before onset (of 9)",
        "caught_in_time_official": "Caught in time (of 9)", "false_per_day": "False alerts per healthy day",
        "status": "Status", "random_p": "Chance p-value"})
    st.dataframe(rows, hide_index=True, width="stretch")
    pct = pd.DataFrame(doc["percentiles"])
    hours = [c for c in pct.columns if c.startswith("pctl_")]
    fig = go.Figure(go.Heatmap(
        z=pct[hours].to_numpy(dtype=float), x=[c.replace("pctl_", "").replace("h", " h") for c in hours],
        y=pct["event_id"] + " · " + pct["kind"].str.replace("_", " "), colorscale=[[0, "#e8eef0"], [0.9, "#f0d2bf"], [1, LOW]],
        zmin=0, zmax=100, colorbar=dict(title="healthy<br>percentile"), hovertemplate="%{y}<br>%{x}: %{z:.1f}th percentile<extra></extra>",
    ))
    chart_layout(fig, 360)
    fig.update_layout(hovermode="closest", margin=dict(l=140, r=20, t=40, b=60))
    fig.update_xaxes(title_text="hours relative to the logged start")
    show(fig)
    st.caption("Leak signal against the same compressor's healthy weeks. Dark red: more extreme than 99% of healthy time.")
    inj = doc["injection"]
    curve = pd.DataFrame(inj["curve"])
    fig = go.Figure(go.Bar(x=[f"{f:g}×" for f in curve["leak_fraction_of_normal_idle_decay"]],
                           y=curve["detected_within_24h"] / curve["trials"], marker_color=[MUTED] + [COPPER] * (len(curve) - 1),
                           text=[f"{d}/{t}" for d, t in zip(curve["detected_within_24h"], curve["trials"])], textposition="outside"))
    chart_layout(fig, 300)
    fig.update_yaxes(tickformat=".0%", range=[0, 1.15], title_text="detected within 24 h")
    fig.update_xaxes(title_text="injected extra air loss (× normal idle loss; 0× = no leak)")
    show(fig)
    st.caption(f"Leaks injected into {inj['curve'][0]['trials']} real healthy days from {inj['unit']}, ramping over {inj['ramp_hours']} h. "
               f"Origin: {inj['origin']}.")
    summary = live_query(f"SELECT * FROM {DATABASE}.ML.NATIVE_ANOMALY_SUMMARY")
    if summary is not None and not summary.empty:
        row = summary.iloc[0]
        a, b, c = st.columns(3)
        a.metric("Snowflake anomaly model · warned before onset", f"{int(row['warned_before_onset'])} of {int(row['failures'])}")
        b.metric("Caught in time", f"{int(row['caught_in_time'])} of {int(row['failures'])}")
        c.metric("False alerts per healthy day", f"{float(row['false_per_healthy_day']):.2f}")
        st.caption(str(row["method"]) + ". Compressor A only, split by time.")
    else:
        st.caption("SNOWFLAKE.ML.ANOMALY_DETECTION is trained and scored by sql/05_native_ml.sql; its results appear when the app runs in Snowflake.")


def page_evidence() -> None:
    evidence, pred = DOCS["evidence"], DOCS["prediction"]
    profile = evidence["profile"]
    a, b, c, d = st.columns(4)
    a.metric("Readings (compressor A)", f"{profile['rows']:,}")
    b.metric("Reading every", f"{profile['cadence_seconds']} s")
    c.metric("Reported failures", f"{len(CASES)} on 3 compressors")
    d.metric("Predictor status", "Promoted" if pred["status"] == "PROMOTED_CROSS_VALIDATED" else "Not promoted")
    st.markdown("#### Pass marks fixed before scoring")
    shown_gates = {key: text for key, text in pred["declared_gates"].items() if "alarm" not in key}
    st.dataframe(pd.DataFrame([{"Pass mark": text, "Result": "Pass" if pred["gates"][key] else "Fail"}
                               for key, text in shown_gates.items()]), hide_index=True, width="stretch")
    st.caption(f"{pred['why_v2']} {pred['caveat']}")
    st.dataframe(CASES[["case_id", "compressor", "kind", "predicted_in_time", "minutes_before_end", "config"]],
                 hide_index=True, width="stretch")
    external = evidence.get("external_validation")
    if external:
        with st.expander(f"Earlier study on untouched 2022 data · {external['status']}"):
            st.caption(f"{external['detector']}. Target: {external['target']}.")
            st.dataframe(pd.DataFrame(external["rows"]), hide_index=True, width="stretch")
            st.caption(external["reading"])
    before_onset_research()
    st.markdown("#### Measured ranges (compressor A)")
    ranges = pd.DataFrame(profile["ranges"]).T.reset_index(names="signal")
    st.dataframe(ranges, hide_index=True, width="stretch")
    st.caption(f"UCI DOI {profile['doi']} · source SHA-256 {profile['sha256']}")
    st.markdown("#### What this product does not claim")
    for limit in evidence["limits"]:
        st.markdown(f"- {limit}")


st.title(page)
{
    "What needs attention": page_now,
    "Leak copilot": page_track,
    "Work orders": page_orders,
    "Compressor health": page_health,
    "Engineering evidence": page_evidence,
}[page]()
