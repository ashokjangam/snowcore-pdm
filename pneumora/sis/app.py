"""PNEUMORA early air-leak detector — Streamlit in Snowflake.

Reads observed MetroPT-3 telemetry and frozen study results. The only writes are
operator decisions through PNEUMORA.OPS.RECORD_ACTION.
"""

from __future__ import annotations

import base64
import calendar
import html
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

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
}
TIME_COLUMNS = {"ts", "start_ts", "end_ts", "removal_deadline", "copilot_first", "lps_first", "raised_at", "cleared_at", "created_at", "date"}

st.set_page_config(page_title="PNEUMORA", page_icon="🫧", layout="wide")
st.markdown(
    f"""
    <style>
    .stApp {{ background: {PAPER}; color: {INK}; }}
    .stApp [data-testid="stMain"] h1, .stApp [data-testid="stMain"] h2, .stApp [data-testid="stMain"] h3,
    .stApp [data-testid="stMain"] h4, .stApp [data-testid="stMain"] h5 {{ color: {INK}; }}
    section[data-testid="stSidebar"] {{ background: #12181b; }}
    section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{ color: #e9e3d8; }}
    section[data-testid="stSidebar"] button p {{ color: {INK}; }}
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


@st.cache_data(ttl=3600, show_spinner=False)
def load(key: str) -> pd.DataFrame:
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


def record_action(source_key: str, action: str, note: str) -> dict:
    session = snowflake_session()
    if session is None:
        return {"ok": False, "error": "Decisions are saved only inside Snowflake."}
    raw = session.sql(
        f"CALL {DATABASE}.OPS.RECORD_ACTION({sql_text(source_key, 120)}, {sql_text(action, 20)}, {sql_text(note, 500)}, CURRENT_USER())"
    ).collect()[0][0]
    return raw if isinstance(raw, dict) else json.loads(str(raw))


def action_log(limit: int = 15) -> pd.DataFrame | None:
    return live_query(
        f"SELECT ACTION_ID, CREATED_AT, LAST_SEEN_AT, SOURCE_KEY, ACTION, STATUS, NOTE, ACTOR "
        f"FROM {DATABASE}.OPS.ACTION_LOG ORDER BY LAST_SEEN_AT DESC LIMIT {int(limit)}"
    )


def decision_panel(source_key: str, context: str) -> None:
    st.markdown("#### Decide and record")
    st.caption(f"Source: `{source_key}` · {context}. Repeating a decision on the same source updates it; it never creates a duplicate.")
    note = st.text_input("Note for the crew", value="", max_chars=500, key=f"note-{source_key}",
                         placeholder="e.g. Listen for leaks at the dryer drain before the next run")
    columns = st.columns(3)
    for column, label, action in zip(columns, ("Acknowledge", "Open inspection", "Dismiss"), ("ACKNOWLEDGE", "INSPECT", "DISMISS")):
        if column.button(label, key=f"{action}-{source_key}", width="stretch"):
            result = record_action(source_key, action, note)
            if result.get("ok"):
                verb = "Updated existing" if result.get("deduplicated") else "Saved new"
                st.success(f"{verb} decision {result['action_id']} · {result['action']} · {result['status']}")
            else:
                st.warning(result.get("error", "Not saved"))
    log = action_log()
    if log is not None and not log.empty:
        st.dataframe(log, hide_index=True, width="stretch")
    elif log is None:
        st.caption("The decision log lives in PNEUMORA.OPS.ACTION_LOG and is shown when the app runs in Snowflake.")


def cortex_failure_answer(packet: dict) -> dict:
    prompt = (
        "You explain a compressor air-leak event to a maintenance crew. Use ONLY the JSON facts below. "
        "Quote the field name for every number you use. Do not name a failed component unless the 'report' field names it. "
        "answer: two plain sentences for the crew saying what the compressor did and whether the leak detector warned "
        "before the logged start or confirmed a leak already under way; never a heading. "
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


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})


def chart_layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor=CARD, plot_bgcolor=CARD,
        font=dict(color=INK, size=12), legend=dict(orientation="h", y=-0.18), hovermode="x unified",
    )
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
    fig.update_layout(height=70, margin=dict(l=4, r=4, t=4, b=4), paper_bgcolor="#12181b", plot_bgcolor="#1c2529", showlegend=False)
    return fig


# ---------- sidebar ----------
logo = next((path for path in (HERE / "assets" / "pneumora-logo-reversed.svg", HERE.parent / "assets" / "pneumora-logo-reversed.svg") if path.exists()), HERE / "missing")
with st.sidebar:
    if logo.exists():
        st.markdown(f"<img src='data:image/svg+xml;base64,{base64.b64encode(logo.read_bytes()).decode()}' style='width:100%'>", unsafe_allow_html=True)
    else:
        st.markdown("## PNEUMORA")
    st.caption("APU-01 · MetroPT-3 compressor · read-only")
    page = st.radio(
        "Page",
        ["What needs attention", "Leak alerts vs real failures", "Can it predict?", "Work orders", "Compressor performance", "Engineering evidence"],
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
    orders = load("orders")
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
    st.markdown("#### Last four hours")
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
        fig.add_vline(x=row.start_ts, line=dict(color=LOW, dash="dot", width=1), opacity=0.5)
    fig.add_trace(go.Scatter(x=FAILURES["start_ts"], y=[3] * len(FAILURES), mode="text", text=FAILURES["failure_id"],
                             textposition="top center", name="Reported failure", hovertext=FAILURES["report"], showlegend=False))
    caught = COPILOT_ALERTS["outcome"] == "caught_in_time"
    for mask, name, fill in ((caught, "Leak detector alert on a reported failure", COPPER), (~caught, "Leak detector alert, no reported failure", CARD)):
        rows = COPILOT_ALERTS[mask]
        fig.add_trace(go.Scatter(
            x=rows["raised_at"], y=[2] * len(rows), mode="markers", name=name,
            marker=dict(size=13, color=fill, line=dict(color=COPPER, width=2)),
            text=rows["alert_id"] + " · " + rows["failure_id"].fillna("no reported failure"), hovertemplate="%{text}<br>%{x}<extra></extra>",
        ))
    lps = ALERTS[ALERTS["source"] == "low_pressure_alarm"]
    lps_caught = lps["outcome"] == "caught_in_time"
    fig.add_trace(go.Scatter(x=lps.loc[~lps_caught, "raised_at"], y=[1] * int((~lps_caught).sum()), mode="markers", name="Low-pressure alarm",
                             marker=dict(symbol="line-ns", size=16, line=dict(color="#a9a29a", width=2))))
    fig.add_trace(go.Scatter(x=lps.loc[lps_caught, "raised_at"], y=[1] * int(lps_caught.sum()), mode="markers", name="Low-pressure alarm on a failure",
                             marker=dict(symbol="line-ns", size=20, line=dict(color=INK, width=4))))
    fig.update_yaxes(tickvals=[1, 2, 3], ticktext=["Existing low-pressure alarm", "Leak detector alerts", "Reported failures"], range=[0.4, 3.9], showgrid=False)
    fig.update_xaxes(showgrid=True, gridcolor="#efeae3")
    chart_layout(fig, 300)
    fig.update_layout(hovermode="closest", margin=dict(l=180, r=10, t=30, b=10))
    return fig


def zoom(failure: pd.Series) -> go.Figure:
    points = load("zoom")
    points = points[points["failure_id"] == failure["failure_id"]].sort_values("ts")
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    end = min(failure["end_ts"], points["ts"].max())
    fig.add_vrect(x0=max(failure["start_ts"], points["ts"].min()), x1=end, fillcolor=LOW, opacity=0.07, line_width=0)
    lo, hi = points["ts"].min(), points["ts"].max()
    alert = failure["copilot_first"]
    if pd.notna(alert) and lo <= alert <= hi:
        fig.add_vrect(x0=alert - pd.Timedelta(minutes=PERSISTENCE), x1=alert, fillcolor=COPPER, opacity=0.18, line_width=0)
        fig.add_annotation(x=alert - pd.Timedelta(minutes=PERSISTENCE / 2), y=0.04, yref="paper", showarrow=False,
                           text=f"{PERSISTENCE}-min check", font=dict(color=COPPER, size=11), bgcolor=CARD)
    fig.add_trace(go.Scatter(x=points["ts"], y=points["loaded"].clip(lower=0.5), name="Longest run without a rest (min, log scale)", fill="tozeroy",
                             line=dict(color=COPPER, width=1.5), fillcolor="rgba(197,107,60,.2)"))
    fig.add_trace(go.Scatter(x=points["ts"], y=points["reservoirs"], name="Reservoir pressure (bar)", line=dict(color=BLUE, width=2.5)), secondary_y=True)
    fig.add_hline(y=SUMMARY["threshold_minutes"], line=dict(color=COPPER, dash="dot"),
                  annotation_text=f"{SUMMARY['threshold_minutes']:.2f} min line", annotation_position="bottom right",
                  annotation_font=dict(color=COPPER, size=11))
    lines = [
        (failure["start_ts"], LOW, "solid", "Log: day of failure (no time given)" if failure["onset_precision"] == "day" else "Log: leak starts"),
        (alert, COPPER, "solid", "Leak detector alert"),
        (failure["lps_first"], INK, "solid", "Low-pressure alarm"),
        (failure["removal_deadline"], INK, "dash", "Last moment to act"),
    ]
    for index, (x, color, dash, label) in enumerate(lines):
        if pd.notna(x) and lo <= x <= hi:
            fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=1, yref="paper", line=dict(color=color, dash=dash, width=2))
            fig.add_annotation(x=x, y=1 - index * 0.08, yref="paper", text=label, showarrow=False, xanchor="left", xshift=4,
                               font=dict(color=color, size=11), bgcolor=CARD)
    ticks = [1, 2, 5, 15, 60, 240, 1000]
    fig.update_yaxes(type="log", title_text="run without a rest (min)", tickvals=ticks, ticktext=[str(t) for t in ticks],
                     minor=dict(showgrid=False), secondary_y=False)
    fig.update_yaxes(title_text="bar", secondary_y=True, showgrid=False)
    chart_layout(fig, 400)
    fig.update_layout(margin=dict(l=60, r=50, t=30, b=10))
    return fig


def story(failure: pd.Series) -> str:
    onset = "the start of the logged day (the log gives only the date)" if failure["onset_precision"] == "day" else "the logged start of the leak"
    if pd.isna(failure["copilot_first"]):
        co = "The leak detector did not alert in time."
    else:
        after = failure["copilot_minutes_after_start"]
        margin = span(failure["copilot_minutes_before_end"] - 120)
        if failure["onset_precision"] == "day":
            relation = f"{span(after)} into the logged day. The log has no start time, so we cannot say whether this was before or after the leak began"
        elif after < 0:
            relation = f"{span(after)} **before** {onset}, so here it did warn ahead"
        else:
            relation = f"{span(after)} **after** {onset}, so here it confirmed a leak already under way rather than predicting it"
        co = f"The leak detector alerted at {when(failure['copilot_first'])}, {relation}. That left {margin} to act before the train had to come off."
        points = load("zoom")
        hour = points[(points["failure_id"] == failure["failure_id"]) & (points["ts"] <= failure["copilot_first"])
                      & (points["ts"] > failure["copilot_first"] - pd.Timedelta(minutes=PERSISTENCE))]
        if not hour.empty:
            co += (f" Why it waited: it needs every 5-minute reading for {PERSISTENCE} minutes to show a run longer than "
                   f"{SUMMARY['threshold_minutes']:.2f} minutes. In that hour the shortest reading was {hour['loaded'].min():.1f} min, "
                   f"so the compressor never got a normal rest.")
    lps = ("The existing low-pressure alarm did not fire in time." if pd.isna(failure["lps_first"])
           else f"The existing low-pressure alarm fired at {when(failure['lps_first'])}, {span(failure['lps_minutes_after_start'])} after the logged start.")
    return f"**{failure['failure_id']} · {failure['report']}.** Logged {when(failure['start_ts'])} to {when(failure['end_ts'])}. {co} {lps}"


def page_track() -> None:
    tally, evidence = SUMMARY["tally"], SUMMARY["evidence"]
    caught = FAILURES[FAILURES["copilot_first"].notna()]
    margin = (caught["copilot_minutes_before_end"] - 120).min()
    timed = caught[caught["onset_precision"] != "day"]
    late = timed[timed["copilot_minutes_after_start"] >= 0]
    early = timed[timed["copilot_minutes_after_start"] < 0]
    undated = len(caught) - len(timed)
    normal = TELEMETRY.loc[~TELEMETRY["copilot_flag"] & (TELEMETRY["loaded_run_minutes"] > 0), "loaded_run_minutes"]
    above = (normal >= SUMMARY["threshold_minutes"]).mean() if len(normal) else float("nan")
    timing = (f"Of the {len(timed)} leaks logged to the minute, it alerted <b>after</b> the leak started on {len(late)} "
              f"({late['copilot_minutes_after_start'].min():.0f}–{late['copilot_minutes_after_start'].max():.0f} min after)")
    if len(early):
        timing += f" and before it on {len(early)} ({span(-early['copilot_minutes_after_start'].max())} ahead)"
    if undated:
        timing += f". For {undated} more the log gives only the date, so we cannot say whether it was early or late"
    st.markdown(
        f"""<div class="pn-hero" style="--tone:{COPPER}"><div class="pn-kicker">Leak predictor · promoted after cross-validation on three compressors</div>
        <h2>It predicts the breakdown hours ahead, once the leak has begun.</h2><div class="pn-lede">A healthy compressor works for about two minutes, rests, and repeats.
        With an air leak it can never fill the tanks, so it stops resting. The leak detector alerts when every 5-minute reading for
        {PERSISTENCE} minutes in a row shows a run longer than {SUMMARY['threshold_minutes']:.2f} minutes. One long reading means nothing,
        because {above:.0%} of normal readings are above that line. A full hour without a normal rest is the signal.
        That hour is why the alert always comes at least {PERSISTENCE} minutes after the compressor stops resting.</div>
        <div class="pn-action"><b>What that buys the crew.</b> {timing}. In every case it still left at least {span(margin)}
        to inspect before the train had to come off. The existing low-pressure alarm caught {tally['low_pressure_alarm']['caught_in_time']} of {tally['failures']} in time,
        because it waits until the air is already low.</div></div>""",
        unsafe_allow_html=True,
    )
    a, b, c, d = st.columns(4)
    a.metric("Failures caught in time · leak detector", f"{tally['copilot']['caught_in_time']} of {tally['failures']}")
    b.metric("Failures caught in time · existing alarm", f"{tally['low_pressure_alarm']['caught_in_time']} of {tally['failures']}")
    c.metric("Leak detector alerts with no reported failure", f"{tally['copilot']['no_reported_failure']} of {tally['copilot']['alerts']}")
    d.metric("Alarm alerts with no reported failure", f"{tally['low_pressure_alarm']['no_reported_failure']} of {tally['low_pressure_alarm']['alerts']}")
    st.markdown("#### Every alert against the maintenance log")
    show(timeline())
    st.caption("Filled circle: leak detector alert that landed on a reported failure in time. Hollow circle: alert with no reported failure. Grey ticks: existing low-pressure alarm.")

    st.markdown("#### Zoom into one failure: what the compressor did, and when each alert fired")
    choice = st.radio("Failure", list(FAILURES["failure_id"]), index=len(FAILURES) - 1, horizontal=True, label_visibility="collapsed")
    failure = FAILURES[FAILURES["failure_id"] == choice].iloc[0]
    show(zoom(failure))
    st.markdown(story(failure))
    explain_with_cortex(failure)
    target = failure["copilot_first"] if pd.notna(failure["copilot_first"]) else failure["start_ts"]
    st.button(f"Replay {choice} on the status page", on_click=lambda t=target: (set_moment(t), st.session_state.update(page="What needs attention")))

    st.markdown(f"#### All {len(COPILOT_ALERTS)} leak detector alerts")
    table = COPILOT_ALERTS.assign(
        Raised=COPILOT_ALERTS["raised_at"].map(when), Cleared=COPILOT_ALERTS["cleared_at"].map(when),
        Longest_run=COPILOT_ALERTS["peak_loaded_minutes"].map(lambda v: f"{v:.0f} min"),
        Outcome=COPILOT_ALERTS["outcome"].str.replace("_", " ").str.capitalize(),
        Against_failure=[
            "—" if pd.isna(f) else f"{f} · {span(m)} {'before' if m < 0 else 'after'} the logged start"
            for f, m in zip(COPILOT_ALERTS["failure_id"], COPILOT_ALERTS["minutes_after_start"])
        ],
    )[["alert_id", "Raised", "Cleared", "Longest_run", "Outcome", "Against_failure"]]
    st.dataframe(table.rename(columns={"alert_id": "Alert", "Longest_run": "Longest non-stop run", "Against_failure": "Against the failure"}),
                 hide_index=True, width="stretch")

    st.markdown(
        f"""<div class="pn-card"><b>Read this before trusting it</b>
        <p><b>These four failures are the ones the detector was designed on.</b> The charts above show how it behaves, but it is not independent proof.
        On data it never saw it was frozen and tested on two 2022 compressors and caught {evidence['external_air_leaks_caught']} of 3 air leaks with {evidence['external_false_alerts']} false alert.
        Holding out each compressor in turn, it predicted {evidence['air_predicted']} air leaks at least 2 h before the train had to come off,
        against the alarm's {evidence['alarm_air_predicted']}, at {evidence['prediction_false_per_day']:.3f} false alerts per healthy day (alarm {evidence['alarm_false_per_day']:.2f}).
        Every pre-declared gate passed, so it is <b>promoted</b>. Caveat: this protocol was revised after the first version failed on false alerts, and no untouched data remains.</p>
        <p><b>It predicts the breakdown, not the leak.</b> The leaks in this data start abruptly; only {evidence['pre_onset_predictions']} of 9 alerts came before the logged start.
        What it forecasts is the reported end of the failure, by which the train must come out of service: a median {evidence['median_lead_minutes'] / 60:.1f} h ahead.</p>
        <p><b>Alerts with no reported failure are not proven false.</b> Some may be unlogged faults, but we cannot verify that from this data, so they are counted against the leak detector.</p>
        <p style="color:{MUTED}">It runs beside the existing alarm and never replaces it. The work orders it opens are drafts for a person to review.</p></div>""",
        unsafe_allow_html=True,
    )


def failure_packet(failure: pd.Series) -> dict:
    points = load("zoom")
    points = points[points["failure_id"] == failure["failure_id"]]
    inside = points[(points["ts"] >= failure["start_ts"]) & (points["ts"] <= failure["end_ts"])]
    before = points[points["ts"] < failure["start_ts"]]
    percentiles = next((row for row in DOCS.get("precursor", {}).get("percentiles", [])
                        if row["unit"] == "METROPT3_UCI_791" and row["event_id"] == failure["failure_id"]), {})
    packet = {
        "failure_id": failure["failure_id"], "report": failure["report"], "onset_precision": failure["onset_precision"],
        "logged_start": failure["start_ts"], "logged_end": failure["end_ts"], "removal_deadline": failure["removal_deadline"],
        "leak_detector_first_alert": failure["copilot_first"],
        "leak_detector_minutes_after_logged_start": failure["copilot_minutes_after_start"],
        "low_pressure_alarm_first": failure["lps_first"], "low_pressure_alarm_minutes_after_logged_start": failure["lps_minutes_after_start"],
        "longest_loaded_run_minutes_during_failure": round(float(inside["loaded"].max()), 1) if not inside.empty else None,
        "lowest_reservoir_bar_during_failure": round(float(inside["reservoirs"].min()), 2) if not inside.empty else None,
        "longest_loaded_run_minutes_before_start": round(float(before["loaded"].max()), 1) if not before.empty else None,
        "healthy_normal_loaded_run_minutes": 1.8,
        "leak_index_percentile_vs_healthy": {k.replace("pctl_", ""): v for k, v in percentiles.items() if k.startswith("pctl_")},
    }
    return {k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in packet.items()}


def explain_with_cortex(failure: pd.Series) -> None:
    packet = failure_packet(failure)
    with st.expander("Root cause in plain words · Snowflake Cortex, grounded in these facts only"):
        st.json(packet, expanded=False)
        if snowflake_session() is None:
            st.caption("Cortex runs when the app is opened in Snowflake.")
            return
        if st.button(f"Explain {failure['failure_id']} with Cortex", key=f"cortex-{failure['failure_id']}"):
            with st.spinner("Cortex is reading only the facts above…"):
                try:
                    answer = cortex_failure_answer(packet)
                except Exception as exc:
                    st.error(f"Cortex could not answer: {exc}")
                    return
            st.markdown(f"**{answer.get('answer', '—')}**")
            for item in answer.get("evidence", []):
                st.markdown(f"- {item}")
            if answer.get("caveats"):
                st.warning(" · ".join(answer["caveats"]))
            if answer.get("next_check"):
                st.info(answer["next_check"])
            st.caption("Cortex received only the JSON above. It wrote no SQL and read no other table.")


def prediction_section() -> None:
    pred = DOCS.get("prediction")
    if not pred:
        st.info("Run autoresearch/prediction_study.py and scripts/export_snowflake.py to load the prediction study.")
        return
    held, alarm = pred["held_out_pooled"], pred["existing_alarm_same_events"]
    air = sum(1 for e in pred["events"] if e["kind"] == "air_leak")
    st.markdown(
        f"""<div class="pn-hero" style="--tone:{OK}"><div class="pn-kicker">Pre-declared gates · held out by compressor · {esc(pred['status'])}</div>
        <h2>Yes: it predicts the breakdown, hours ahead.</h2><div class="pn-lede">On each compressor it never saw, the leak predictor flagged
        <b>{held['air_caught']} of {air}</b> air leaks at least two hours before the train had to come out of service, a median
        <b>{held['median_margin'] / 60:.1f} h</b> ahead, with <b>{held['false_per_day']:.3f}</b> false alerts per healthy day.
        The existing low-pressure alarm predicted {alarm['air_caught']} of {air} at {alarm['false_per_day']:.2f} false alerts per day.
        A random alerter at the same rate would match this with p = {pred['random_alerter']['p_at_least_observed']:.0e}.</div>
        <div class="pn-action"><b>What it does not do.</b> It predicts the breakdown, not the leak: only {pred['pre_onset_predictions']} of 9
        alerts came before the logged start of the leak. It catches no oil leaks; the existing alarm stays on for those.</div></div>""",
        unsafe_allow_html=True,
    )
    a, b, c, d = st.columns(4)
    a.metric("Air leaks predicted ≥ 2 h ahead", f"{held['air_caught']} of {air}", f"alarm {alarm['air_caught']} of {air}")
    b.metric("Median warning before removal", f"{held['median_margin'] / 60:.1f} h")
    c.metric("False alerts per healthy day", f"{held['false_per_day']:.3f}", f"alarm {alarm['false_per_day']:.2f}", delta_color="off")
    d.metric("Warned before the leak began", f"{pred['pre_onset_predictions']} of 9")
    events = pd.DataFrame(pred["events"])
    events["warning_before_removal"] = events["minutes_before_end"].map(lambda m: "—" if pd.isna(m) else f"{m / 60:.1f} h")
    events["relative_to_leak_start"] = events["minutes_after_start"].map(
        lambda m: "—" if pd.isna(m) else f"{abs(m):.0f} min {'before' if m < 0 else 'after'}")
    st.dataframe(events.rename(columns={"held_out": "Compressor (held out)", "chosen_on_other_two": "Settings chosen on the other two",
                                        "event_id": "Failure", "kind": "Kind", "caught_in_time": "Predicted in time",
                                        "warning_before_removal": "Warning before removal", "relative_to_leak_start": "Alert vs leak start"})
                 [["Compressor (held out)", "Failure", "Kind", "Predicted in time", "Warning before removal", "Alert vs leak start",
                   "Settings chosen on the other two"]], hide_index=True, width="stretch")
    st.caption("Gates fixed in code before scoring: " + " · ".join(pred["declared_gates"].values()))
    st.markdown(f"<div class='pn-card'><b>Why there is a version 2.</b> {esc(pred['why_v2'])} {esc(pred['caveat'])}</div>",
                unsafe_allow_html=True)


def page_predict() -> None:
    prediction_section()
    doc = DOCS.get("precursor")
    st.markdown(
        f"""<div class="pn-hero" style="--tone:{BLUE}"><div class="pn-kicker">Pre-registered study · nine real failures · three compressors</div>
        <h2>Can it warn before the leak itself starts?</h2><div class="pn-lede">We tried every route we could find to warn before the logged start of a leak:
        cycle-by-cycle physics from the raw 1–10 second data, multi-day drift, supervised learning on the hours before other failures,
        synthetic failure replays, and Snowflake's own anomaly detection. The study arms were trained or tuned on two compressors and tested on the third;
        Snowflake's anomaly detection learned February–March and was tested from April.</div>
        <div class="pn-action"><b>Answer.</b> Only one of nine failures (F04) showed a measurable warning sign, about 80–95 minutes ahead.
        The other eight leaks began abruptly, so the prediction above starts once the leak has begun.</div></div>""",
        unsafe_allow_html=True,
    )
    if not doc:
        st.info("Run autoresearch/precursor_study.py and scripts/export_snowflake.py to load this study.")
        return
    rows = pd.DataFrame(doc["rows"]).rename(columns={
        "approach": "Approach", "warned_before_onset": f"Warned in the {doc['pre_onset_hours']} h before onset (of 9)",
        "caught_in_time_official": "Caught in time, official protocol (of 9)", "false_per_day": "False alerts per healthy day",
        "status": "Status", "random_p": "Chance p-value"})
    st.markdown("#### Every approach, tested on a compressor it never saw")
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption("Pass marks were fixed in code before scoring: " + " · ".join(doc["gates"].values()))

    st.markdown("#### What the signal looked like before each failure")
    pct = pd.DataFrame(doc["percentiles"])
    hours = [c for c in pct.columns if c.startswith("pctl_")]
    fig = go.Figure(go.Heatmap(
        z=pct[hours].to_numpy(dtype=float), x=[c.replace("pctl_", "").replace("h", " h") for c in hours],
        y=pct["event_id"] + " · " + pct["kind"].str.replace("_", " "), colorscale=[[0, "#e8eef0"], [0.9, "#f0d2bf"], [1, LOW]],
        zmin=0, zmax=100, colorbar=dict(title="healthy<br>percentile"), hovertemplate="%{y}<br>%{x}: %{z:.1f}th percentile<extra></extra>",
    ))
    chart_layout(fig, 360)
    fig.update_layout(hovermode="closest", margin=dict(l=150, r=10, t=30, b=40))
    fig.update_xaxes(title_text="hours relative to the logged start")
    show(fig)
    st.caption("Leak index (faster idle pressure decay, slower rise, longer loaded runs) against the same compressor's healthy weeks. "
               "Dark red means more extreme than 99% of healthy time. Only F04 turns red before 0 h.")

    st.markdown("#### If a leak grows gradually, how soon would it be caught?")
    inj = doc["injection"]
    curve = pd.DataFrame(inj["curve"])
    fig = go.Figure(go.Bar(x=[f"{f:g}×" for f in curve["leak_fraction_of_normal_idle_decay"]],
                           y=curve["detected_within_24h"] / curve["trials"], marker_color=[MUTED] + [COPPER] * (len(curve) - 1),
                           text=[f"{d}/{t}" for d, t in zip(curve["detected_within_24h"], curve["trials"])], textposition="outside"))
    fig.update_yaxes(tickformat=".0%", range=[0, 1.1], title_text="detected within 24 h")
    fig.update_xaxes(title_text="extra air loss at 24 h, as a multiple of normal idle loss (0× is the no-leak control)")
    show(chart_layout(fig, 300))
    st.caption(f"{inj['curve'][0]['trials']} real healthy days from {inj['unit']}, each with a "
               f"leak injected that ramps up over {inj['ramp_hours']} h. Origin: {inj['origin']}. The 0× bar shows alerts that would fire anyway.")

    st.markdown("#### Snowflake-native ML · SNOWFLAKE.ML.ANOMALY_DETECTION")
    summary = live_query(f"SELECT * FROM {DATABASE}.ML.NATIVE_ANOMALY_SUMMARY")
    detail = live_query(f"SELECT FAILURE_ID, START_TS, ONSET_PRECISION, FIRST_BEFORE_ONSET, FIRST_IN_TIME FROM {DATABASE}.ML.NATIVE_ANOMALY_EVAL ORDER BY START_TS")
    if summary is None or summary.empty:
        st.caption("Trained and scored inside Snowflake by sql/05_native_ml.sql; results appear when the app runs in Snowflake.")
    else:
        row = summary.iloc[0]
        a, b, c = st.columns(3)
        a.metric("Warned before onset", f"{int(row['warned_before_onset'])} of {int(row['failures'])}")
        b.metric("Caught in time", f"{int(row['caught_in_time'])} of {int(row['failures'])}")
        c.metric("False alerts per healthy day", f"{float(row['false_per_healthy_day']):.2f}")
        st.caption(str(row["method"]) + ". MetroPT-3 only, split by time rather than by compressor. "
                   "The false-alert budget is 0.14 per healthy day, so this model would not pass the study's gates either.")
        if detail is not None:
            st.dataframe(detail, hide_index=True, width="stretch")
    st.markdown(f"<div class='pn-card'><b>Read this before trusting it.</b> {esc(doc['caveat'])}</div>", unsafe_allow_html=True)


def page_orders() -> None:
    orders = load("orders").sort_values("created_at", ascending=False)
    st.info("Read-only copy of the PNEUMORA maintenance system. These are demonstration maintenance records, not real railway work orders.")
    statuses = st.multiselect("Status", sorted(orders["status"].unique()), default=sorted(orders["status"].unique()))
    view = orders[orders["status"].isin(statuses)]
    a, b, c = st.columns(3)
    a.metric("Open orders", int((~view["status"].isin(["done", "dismissed"])).sum()))
    b.metric("Urgent", int((view["priority"] == "urgent").sum()))
    c.metric("Drafted by the leak detector", int(view["order_id"].str.startswith("PN-CO-").sum()))
    st.dataframe(
        view.assign(created_at=view["created_at"].map(when))[["order_id", "created_at", "priority", "status", "problem", "action", "technician", "part", "note"]],
        hide_index=True, width="stretch",
    )
    left, right = st.columns(2)
    left.markdown("##### Parts")
    left.dataframe(load("parts").drop(columns=["data_origin"]), hide_index=True, width="stretch")
    right.markdown("##### Crew")
    right.dataframe(load("crew").drop(columns=["data_origin"]), hide_index=True, width="stretch")


def page_performance() -> None:
    kpis, factory = load("kpis"), load("factory")
    latest = kpis.iloc[-1]
    a, b, c, d = st.columns(4)
    a.metric("Telemetry coverage", f"{latest['telemetry_coverage']:.0%}")
    b.metric("Compressor running", f"{latest['compressor_runtime']:.0%}")
    c.metric("Loaded", f"{latest['loaded_time']:.0%}")
    d.metric("Under strain", f"{latest['time_under_strain']:.1%}")
    fig = go.Figure(go.Scatter(x=kpis["date"], y=kpis["loaded_time"], line=dict(color=INK, width=2), name="Loaded share"))
    for row in FAILURES.itertuples():
        fig.add_vrect(x0=row.start_ts, x1=row.end_ts + pd.Timedelta(hours=12), fillcolor=LOW, opacity=0.15, line_width=0)
    fig.update_yaxes(tickformat=".0%")
    st.markdown("#### Measured compressor load (observed telemetry)")
    show(chart_layout(fig, 300))
    st.caption("Share of each day the compressor was loaded. Red bands are reported failures.")
    st.markdown("<div class='pn-card pn-example'><b>Example factory score</b> · not this train's real production or cost. "
                "Values come from stated example assumptions.</div>", unsafe_allow_html=True)
    fig = go.Figure(go.Scatter(x=factory["date"], y=factory["oee"], line=dict(color=COPPER, width=2), name="Example OEE"))
    fig.update_yaxes(tickformat=".0%")
    show(chart_layout(fig, 260))


def page_evidence() -> None:
    evidence = DOCS["evidence"]
    profile = evidence["profile"]
    a, b, c, d = st.columns(4)
    a.metric("Observed rows", f"{profile['rows']:,}")
    b.metric("Cadence", f"{profile['cadence_seconds']} s")
    c.metric("Reported failures", "4")
    d.metric("Decision", evidence["decision"]["status"])
    external = evidence.get("external_validation")
    if external:
        st.markdown(f"#### Official-protocol study with untouched 2022 data · {external['status']}")
        st.caption(f"{external['detector']}. Target: {external['target']}.")
        st.dataframe(pd.DataFrame(external["rows"]), hide_index=True, width="stretch")
        st.markdown(" ".join(f"`{'Pass' if ok else 'Fail'} · {name.replace('_', ' ')}`" for name, ok in external["gates"].items()))
        st.caption(external["reading"])
        cross = external.get("cross_validation")
        if cross:
            st.markdown(f"#### Leave-one-compressor-out, all nine failures · {cross['status']}")
            st.dataframe(pd.DataFrame(cross["rows"]), hide_index=True, width="stretch")
            st.markdown(" ".join(f"`{'Pass' if ok else 'Fail'} · {name.replace('_', ' ')}`" for name, ok in cross["gates"].items()))
            st.caption("The budget is one false alert per seven healthy days (0.143).")
    st.markdown("#### Measured ranges")
    ranges = pd.DataFrame(profile["ranges"]).T.reset_index(names="signal")
    st.dataframe(ranges, hide_index=True, width="stretch")
    st.caption(f"UCI DOI {profile['doi']} · source SHA-256 {profile['sha256']}")
    st.markdown("#### What this product does not claim")
    for limit in evidence["limits"]:
        st.markdown(f"- {limit}")


st.title(page)
{
    "What needs attention": page_now,
    "Leak alerts vs real failures": page_track,
    "Can it predict?": page_predict,
    "Work orders": page_orders,
    "Compressor performance": page_performance,
    "Engineering evidence": page_evidence,
}[page]()
