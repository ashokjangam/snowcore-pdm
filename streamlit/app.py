"""SnowCore PdM — Predictive Maintenance & OEE Command Center.

Streamlit in Snowflake. Reads SNOWCORE_REAL only.

NAMING, because it has caused confusion:

    PLANT_B  ==  PIADE   ==  5 packaging lines  (s_1 .. s_5)
    PLANT_A  ==  CoMoPI  ==  8 closure machines (A001, A005, B002, ...)

PIADE does not contain a Plant A. CoMoPI does not contain a Plant B. They are
two separate published datasets and "Plant A" / "Plant B" are labels we applied
to each one as a whole.

The two are never aggregated into a single number, because they are unrelated
factories with no shared machine, time window or key. They ARE unified at the
decision layer on the Action queue page: one ranked list of what to do next,
with each row carrying the strength of the evidence behind it.
"""

from __future__ import annotations

import html

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from snowflake.snowpark.context import get_active_session

DB = "SNOWCORE_REAL"

st.set_page_config(
    page_title="SnowCore | Maintenance & OEE",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="expanded",
)

INK = "#1b2c3a"
INK2 = "#5b6f80"
LINE = "#dce5ec"
ACCENT = "#0b7482"
SERIES = ["#0b7482", "#4b8bbe", "#e59f23", "#6fbc8b", "#8a6f9c", "#c4645c"]

# NOTE ON SIDEBAR CSS
# The previous version used `[data-testid="stSidebar"] * {color:...}`. The
# universal selector reaches inside Streamlit's own widget internals and
# repaints parts that are not text, which is what made sidebar controls render
# badly. Every rule below targets a specific element instead.
st.markdown(
    """
    <style>
      .block-container { padding-top:1.3rem; padding-bottom:3rem; max-width:1520px; }

      /* ---------- sidebar ---------- */
      [data-testid="stSidebar"] { background:#0d2233; }
      [data-testid="stSidebar"] .stMarkdown p,
      [data-testid="stSidebar"] .stMarkdown div,
      [data-testid="stSidebar"] .stMarkdown li { color:#d7e5ef; }
      [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p { color:#8fa8ba; }
      [data-testid="stSidebar"] [role="radiogroup"] label p { color:#e6eff6; font-size:.9rem; }
      [data-testid="stSidebar"] [role="radiogroup"] label {
        padding:.34rem .55rem; border-radius:7px;
      }
      [data-testid="stSidebar"] [role="radiogroup"] label:hover { background:#16344a; }
      .sb-brand { font-size:1.15rem; font-weight:700; color:#ffffff;
                  letter-spacing:.02em; margin-bottom:.1rem; }
      .sb-tag   { font-size:.76rem; color:#7f9db2; line-height:1.45; margin-bottom:1rem; }
      .sb-rule  { height:1px; background:#1d3c53; margin:1.05rem 0; }
      .sb-h     { font-size:.67rem; letter-spacing:.13em; text-transform:uppercase;
                  color:#6e91a8; margin-bottom:.45rem; }
      .sb-map   { font-size:.79rem; color:#bcd2e0; line-height:1.55; margin-bottom:.6rem; }
      .sb-map b { color:#ffffff; }
      .sb-map span { color:#7f9db2; }

      /* ---------- hero ---------- */
      .hero { background:linear-gradient(120deg,#0d2233,#134763 62%,#0b7482);
              color:#fff; padding:1.15rem 1.5rem; border-radius:14px; margin-bottom:.9rem; }
      .hero h1 { font-size:1.72rem; margin:0; font-weight:670; letter-spacing:-.015em; }
      .hero p  { color:#c5e2ea; margin:.3rem 0 0; font-size:.92rem; }

      /* ---------- badges ---------- */
      .badge { display:inline-block; padding:.2rem .55rem; border-radius:999px;
               font-size:.71rem; font-weight:700; margin-right:.3rem; }
      .observed  { background:#dff5e8; color:#155d37; }
      .derived   { background:#e0efff; color:#114b7a; }
      .synthetic { background:#fff0cf; color:#78520b; }

      /* ---------- callouts ---------- */
      .caveat { border-left:4px solid #e59f23; background:#fff9eb;
                padding:.75rem .95rem; border-radius:0 8px 8px 0; color:#4b380c;
                font-size:.875rem; line-height:1.6; margin:.6rem 0; }
      .caveat b { color:#3a2b07; }
      .plain  { border-left:4px solid #b9c9d6; background:#f6f9fb;
                padding:.75rem .95rem; border-radius:0 8px 8px 0; color:#42586a;
                font-size:.875rem; line-height:1.6; margin:.6rem 0; }
      .plain b { color:#1b2c3a; }

      /* ---------- metric cards ---------- */
      div[data-testid="stMetric"] { background:#fff; border:1px solid #dce5ec;
              padding:.7rem .9rem; border-radius:12px; }
      div[data-testid="stMetricLabel"] p { font-weight:700; font-size:.78rem; color:#5b6f80; }
      div[data-testid="stMetricValue"] { font-size:1.62rem; color:#1b2c3a; }

      /* ---------- explainer panels ---------- */
      .card { background:#fff; border:1px solid #dce5ec; border-radius:12px;
              padding:1rem 1.15rem; height:100%; }
      .card-h { font-size:1rem; font-weight:670; color:#1b2c3a; margin:0 0 .1rem; }
      .card-s { font-size:.73rem; font-weight:650; letter-spacing:.06em;
                text-transform:uppercase; color:#8698a7; margin-bottom:.55rem; }
      .card-p { font-size:.855rem; color:#5b6f80; line-height:1.55; margin:0 0 .6rem; }
      .kv { display:flex; gap:.55rem; font-size:.84rem; padding:.34rem 0;
            border-top:1px solid #eef3f7; line-height:1.5; }
      .kv-k { flex:0 0 5rem; font-size:.69rem; font-weight:700; letter-spacing:.06em;
              text-transform:uppercase; color:#8698a7; padding-top:.14rem; }
      .kv-v { color:#5b6f80; }
      .kv-v b { color:#1b2c3a; }
      .yes { color:#13864d; font-weight:660; }
      .no  { color:#ba3131; font-weight:660; }

      /* ---------- cortex ---------- */
      .cortex { background:#fff; border:1px solid #dce5ec; border-radius:12px;
                padding:.95rem 1.1rem; }
      .cortex-h { font-size:.68rem; font-weight:700; letter-spacing:.12em;
                  text-transform:uppercase; color:#8698a7; margin-bottom:.5rem; }
      .cortex-b { font-size:.885rem; color:#1b2c3a; line-height:1.62; }
      .cortex-f { font-size:.73rem; color:#8698a7; margin-top:.6rem;
                  border-top:1px solid #eef3f7; padding-top:.5rem; }

      /* ---------- misc ---------- */
      .stTabs [data-baseweb="tab"] { font-size:.885rem; font-weight:600; }
      div[data-testid="stDataFrame"] { border:1px solid #dce5ec; border-radius:10px; }
      #MainMenu, footer { visibility:hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------


@st.cache_resource
def _session():
    return get_active_session()


@st.cache_data(ttl=900, show_spinner=False)
def query(sql: str) -> pd.DataFrame:
    return _session().sql(sql).to_pandas()


def lit(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


_BADGE = {
    "OBSERVED": ("observed", "Observed"),
    "DERIVED_FROM_OBSERVED": ("derived", "Derived"),
    "SYNTHETIC_IT": ("synthetic", "Synthetic"),
}


def badges(*origins: str) -> None:
    out = "".join(
        f'<span class="badge {_BADGE[o][0]}">{_BADGE[o][1]}</span>'
        for o in origins if o in _BADGE
    )
    st.markdown(out, unsafe_allow_html=True)


def caveat(html_text: str) -> None:
    st.markdown(f'<div class="caveat">{html_text}</div>', unsafe_allow_html=True)


def plain(html_text: str) -> None:
    st.markdown(f'<div class="plain">{html_text}</div>', unsafe_allow_html=True)


def pct(value, digits: int = 1) -> str:
    return "—" if value is None or pd.isna(value) else f"{float(value) * 100:.{digits}f}%"


def num(value, digits: int = 0) -> str:
    return "—" if value is None or pd.isna(value) else f"{float(value):,.{digits}f}"


def style_fig(fig: go.Figure, height: int = 330, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=6, r=6, t=28 if legend else 8, b=6),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12, color=INK2), showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0,
                    title=None, font=dict(size=11)),
        hoverlabel=dict(bgcolor="white", bordercolor=LINE,
                        font=dict(color=INK, size=12)),
        colorway=SERIES,
    )
    fig.update_xaxes(showgrid=False, linecolor=LINE, ticks="outside",
                     tickcolor=LINE, title=None, tickfont=dict(size=11))
    fig.update_yaxes(gridcolor="#eef3f7", zeroline=False,
                     linecolor="rgba(0,0,0,0)", title=None, tickfont=dict(size=11))
    return fig


def chart(fig: go.Figure) -> None:
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


@st.cache_data(ttl=900, show_spinner=False)
def briefings() -> pd.DataFrame:
    return query(
        f"""SELECT BRIEFING_KEY, NARRATIVE, INPUT_ORIGIN, MODEL_USED
            FROM {DB}.GOLD.CORTEX_BRIEFING"""
    )


def cortex_brief(key: str, label: str = "Cortex briefing") -> None:
    rows = briefings()
    row = rows[rows["BRIEFING_KEY"] == key]
    if row.empty:
        return
    item = row.iloc[0]
    css, chip = _BADGE.get(str(item["INPUT_ORIGIN"]), ("derived", "Derived"))
    st.markdown(
        f'<div class="cortex"><div class="cortex-h">{esc(label)} '
        f'<span class="badge {css}">{chip}</span></div>'
        f'<div class="cortex-b">{esc(item["NARRATIVE"])}</div>'
        f'<div class="cortex-f">Written inside Snowflake by Cortex '
        f'({esc(item["MODEL_USED"])}) from aggregate figures only — it never '
        f'sees a raw row.</div></div>',
        unsafe_allow_html=True,
    )


def hero(title: str, sub: str) -> None:
    st.markdown(
        f'<div class="hero"><h1>{esc(title)}</h1><p>{esc(sub)}</p></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Page — Overview
# ---------------------------------------------------------------------------


def page_overview() -> None:
    hero("Maintenance & OEE Command Center",
         "Two real packaging datasets, measured honestly and never blended.")

    with st.expander("Start here — what am I actually looking at?", expanded=True):
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            st.markdown(
                '<div class="card">'
                '<div class="card-s">Dataset 1 of 2</div>'
                '<p class="card-h">Plant B = PIADE</p>'
                '<p class="card-p">5 packaging lines, named s_1 to s_5. Every '
                'production interval with its machine state, stop alarm code, '
                'package counters and line speed.</p>'
                '<div class="kv"><span class="kv-k">Gives</span><span class="kv-v">'
                '<b>Real OEE</b>, downtime Pareto, next-hour stop risk</span></div>'
                '<div class="kv"><span class="kv-k">Lacks</span><span class="kv-v">'
                '<span class="no">No sensors.</span> No vibration, temperature or '
                'pressure anywhere in it.</span></div>'
                '</div>', unsafe_allow_html=True)
        with c2:
            st.markdown(
                '<div class="card">'
                '<div class="card-s">Dataset 2 of 2</div>'
                '<p class="card-h">Plant A = CoMoPI</p>'
                '<p class="card-p">8 closure machines. Sixteen anonymised analogue '
                'sensor channels aggregated into ten-minute windows, plus alarm '
                'counters per window.</p>'
                '<div class="kv"><span class="kv-k">Gives</span><span class="kv-v">'
                '<b>Condition drift</b> against each machine\u2019s own baseline</span></div>'
                '<div class="kv"><span class="kv-k">Lacks</span><span class="kv-v">'
                '<span class="no">No production counts.</span> OEE and lost output '
                'cannot be computed for it, at all.</span></div>'
                '</div>', unsafe_allow_html=True)

        st.markdown("")
        plain(
            "<b>PIADE is Plant B. CoMoPI is Plant A.</b> There is no Plant A inside "
            "PIADE — the labels name each whole dataset, not a subdivision of one. "
            "They are two different factories published by two different teams, with "
            "no shared machine, no shared time window and no key that joins them."
        )
        caveat(
            "<b>Neither dataset ships any IT records.</b> No work orders, no "
            "technicians, no costs, no maintenance history. Every euro in this "
            "application is generated by us from that plant\u2019s own observed stop "
            "events and is labelled synthetic wherever it appears. The OT-to-IT link "
            "is a constructed demonstration, not a discovered finding."
        )

    st.markdown("#### The numbers that matter")
    oee = query(
        f"""SELECT OEE, AVAILABILITY, PERFORMANCE, QUALITY, PLANNED_HOURS,
                   RUN_HOURS, BREAKDOWN_HOURS, IDLE_HOURS, SLOW_RUNNING_HOURS
            FROM {DB}.GOLD.V_OEE_ROLLUP
            WHERE PLANT_CODE='PLANT_B' AND MACHINE_CODE IS NULL"""
    ).iloc[0]
    cost = query(
        f"""SELECT SUM(MAINTENANCE_COST) AS MAINT, SUM(IDLE_FORGONE_MARGIN) AS IDLE
            FROM {DB}.GOLD.V_COST_BY_MACHINE WHERE PLANT_CODE='PLANT_B'"""
    ).iloc[0]
    model = query(
        f"""SELECT AUC, TOP_DECILE_PRECISION, BASELINE_TOP_DECILE_PRECISION, BASE_RATE
            FROM {DB}.ML.PLANT_B_MODEL_METRICS WHERE SCOPE='FLEET'"""
    ).iloc[0]
    health = query(
        f"""SELECT COUNT(DISTINCT MACHINE_CODE) AS MACHINES, AVG(HEALTH_INDEX_AVG) AS AVG_H
            FROM {DB}.GOLD.V_PLANT_A_HEALTH WHERE ANY_SCORED_PERIOD"""
    ).iloc[0]

    a, b, c, d, e = st.columns(5)
    a.metric(
        "Plant B OEE", pct(oee["OEE"]),
        help="Availability × Performance × Quality for the whole PIADE site. "
             "Computed by summing seconds and packages across the entire period, "
             "then dividing once. Averaging the daily percentages instead would "
             "give 43.2%, which is wrong because it weights a quiet day the same "
             "as a full one.",
    )
    b.metric(
        "Hours spent waiting", num(oee["IDLE_HOURS"]),
        f"vs {num(oee['BREAKDOWN_HOURS'])} h broken", delta_color="off",
        help="Idle means the line was available and running nothing, with no alarm "
             "raised. Breakdown means a fault was recorded. Waiting is over three "
             "times larger, and it belongs to planning rather than maintenance.",
    )
    c.metric(
        "Waiting vs repair cost", f"{float(cost['IDLE'])/float(cost['MAINT']):.1f}×",
        help="Forgone margin from idle time divided by total maintenance cost. "
             "Both sides are synthetic euros resting on chosen rates, so trust the "
             "ratio and the hours behind it, not the absolute figures.",
    )
    d.metric(
        "Stop-risk precision", pct(model["TOP_DECILE_PRECISION"]),
        f"baseline {pct(model['BASELINE_TOP_DECILE_PRECISION'])}", delta_color="off",
        help="Of the riskiest 10% of hours the model flags, this share really did "
             "suffer a heavy stop. The number underneath is what you would get from "
             "the trivial rule 'this hour already had downtime'. The gap between the "
             "two is the model's actual contribution.",
    )
    e.metric(
        "Plant A health", f"{float(health['AVG_H']):.1f}/100",
        f"{int(health['MACHINES'])} machines scored", delta_color="off",
        help="Distance from each machine's own early-life baseline across 16 sensor "
             "channels. 100 means indistinguishable from baseline. This is NOT a "
             "failure probability — it was tested and does not predict alarms.",
    )

    st.markdown("#### Why Plant B has two pages")
    plain(
        "The problem statement asks for two different things, and Plant B is the only "
        "dataset that can answer both. They are the same lines seen in opposite "
        "directions in time, which is why they are separate pages rather than one."
    )
    t1, t2 = st.columns(2, gap="medium")
    with t1:
        st.markdown(
            '<div class="card"><div class="card-s">Looking backward · diagnostic</div>'
            '<p class="card-h">Plant B · OEE &amp; loss</p>'
            '<p class="card-p">Answers <b>“where did my production time actually '
            'go?”</b> over the whole recorded history. Splits every lost hour into '
            'waiting, faulted, or running below rate, ranks the causes, and assigns '
            'each one an owner.</p>'
            '<div class="kv"><span class="kv-k">Use it</span><span class="kv-v">'
            'To decide what to fix structurally this quarter.</span></div>'
            '<div class="kv"><span class="kv-k">Horizon</span><span class="kv-v">'
            'Months of history, aggregated.</span></div></div>',
            unsafe_allow_html=True)
    with t2:
        st.markdown(
            '<div class="card"><div class="card-s">Looking forward · predictive</div>'
            '<p class="card-h">Plant B · Stop risk</p>'
            '<p class="card-p">Answers <b>“which hour should I watch next?”</b> '
            'Scores every machine-hour for the chance that the following hour loses '
            'more than 10% of its time to unplanned downtime.</p>'
            '<div class="kv"><span class="kv-k">Use it</span><span class="kv-v">'
            'To decide where to stand during today\u2019s shift.</span></div>'
            '<div class="kv"><span class="kv-k">Horizon</span><span class="kv-v">'
            'One hour ahead, per machine.</span></div></div>',
            unsafe_allow_html=True)

    st.markdown("#### Where the time goes at Plant B")
    parts = [
        ("Producing at rate", float(oee["RUN_HOURS"]) - float(oee["SLOW_RUNNING_HOURS"]), "#0b7482"),
        ("Running below rate", float(oee["SLOW_RUNNING_HOURS"]), "#4b8bbe"),
        ("Waiting — idle, no alarm", float(oee["IDLE_HOURS"]), "#e59f23"),
        ("Faulted — breakdown", float(oee["BREAKDOWN_HOURS"]), "#c4645c"),
    ]
    fig = go.Figure()
    for name, hours, colour in parts:
        fig.add_bar(y=["Plant B"], x=[hours], name=name, orientation="h",
                    marker_color=colour,
                    hovertemplate=f"{name}<br>%{{x:,.0f}} h<extra></extra>")
    fig.update_layout(barmode="stack")
    fig.update_yaxes(showticklabels=False)
    fig.update_xaxes(ticksuffix=" h")
    chart(style_fig(fig, height=150))

    g1, g2 = st.columns(2, gap="medium")
    with g1:
        cortex_brief("PLANT_B_OEE", "Cortex readout — production")
    with g2:
        cortex_brief("PLANT_B_COST", "Cortex readout — who owns the cost")


# ---------------------------------------------------------------------------
# Page — Action queue (the cross-site answer)
# ---------------------------------------------------------------------------


def page_actions() -> None:
    hero("Action queue",
         "One ranked list across both sites — unified by decision, not by data.")

    plain(
        "<b>This is how the two datasets come together.</b> Their measurements are "
        "never added up, because that would be meaningless. What is shared is the "
        "<b>decision</b>: every signal from either site is turned into a row saying "
        "who should act, what was observed, and how strong the evidence is. A real "
        "command centre does exactly this — it does not care which system a signal "
        "came from, only what to do next and how much to trust it."
    )
    caveat(
        "<b>Read the Evidence column before acting on any row.</b> "
        "<span class='badge observed'>Observed</span> means it is in the published "
        "data. <span class='badge derived'>Derived</span> means we computed it from "
        "published values. <span class='badge synthetic'>Synthetic</span> means the "
        "money is invented. Rows are ranked within each owner, never across owners, "
        "because hours at one site and drifted channels at the other are different "
        "units and cannot be compared on one scale."
    )

    rows: list[dict] = []

    # --- Plant B, planning: the waiting problem -----------------------------
    idle = query(
        f"""SELECT MACHINE_CODE, IDLE_HOURS, IDLE_INCIDENTS, PCT_COST_FROM_IDLING
            FROM {DB}.GOLD.V_COST_BY_MACHINE
            WHERE PLANT_CODE='PLANT_B' AND IDLE_HOURS > 0
            ORDER BY IDLE_HOURS DESC"""
    )
    for _, r in idle.iterrows():
        rows.append({
            "Owner": "Planning",
            "Site": "Plant B · PIADE",
            "Asset": r["MACHINE_CODE"],
            "Signal": "Line idle with no alarm",
            "Observed": f"{float(r['IDLE_HOURS']):,.0f} h across "
                        f"{int(r['IDLE_INCIDENTS']):,} incidents of 30 min or more",
            "Magnitude": float(r["IDLE_HOURS"]),
            "Unit": "idle hours",
            "Evidence": "Observed",
            "Suggested action": "Investigate scheduling and upstream material flow. "
                                "No fault was raised, so this is not a repair job.",
        })

    # --- Plant B, maintenance: the real fault causes ------------------------
    faults = query(
        f"""SELECT CAUSE_CODE, STOP_COUNT, STOP_HOURS, MEDIAN_STOP_MIN, STOP_PATTERN
            FROM {DB}.GOLD.V_DOWNTIME_PARETO
            WHERE PLANT_CODE='PLANT_B' AND LOSS_NATURE='FAULTED'
            ORDER BY STOP_HOURS DESC LIMIT 6"""
    )
    for _, r in faults.iterrows():
        rows.append({
            "Owner": "Maintenance",
            "Site": "Plant B · PIADE",
            "Asset": f"Cause {r['CAUSE_CODE']}",
            "Signal": f"Recurring fault — {str(r['STOP_PATTERN']).replace('_', ' ').lower()}",
            "Observed": f"{int(r['STOP_COUNT']):,} stops, {float(r['STOP_HOURS']):,.0f} h lost, "
                        f"median {float(r['MEDIAN_STOP_MIN']):.1f} min",
            "Magnitude": float(r["STOP_HOURS"]),
            "Unit": "fault hours",
            "Evidence": "Observed",
            "Suggested action": "Alarm codes are anonymised by the publisher, so treat "
                                "this as a pattern to standardise a response around, "
                                "not a diagnosed component.",
        })

    # --- Plant B, maintenance: live risk, only where the model earns it -----
    metrics = query(
        f"""SELECT SCOPE, TOP_DECILE_PRECISION, BASELINE_TOP_DECILE_PRECISION
            FROM {DB}.ML.PLANT_B_MODEL_METRICS WHERE SCOPE <> 'FLEET'"""
    )
    trusted = metrics[
        metrics["TOP_DECILE_PRECISION"] > metrics["BASELINE_TOP_DECILE_PRECISION"]
    ]["SCOPE"].tolist()
    if trusted:
        flagged = query(
            f"""SELECT MACHINE_CODE, COUNT(*) AS FLAGGED_HOURS,
                       SUM(IFF(ACTUAL_HEAVY_STOP=1,1,0)) AS CONFIRMED
                FROM {DB}.GOLD.V_PLANT_B_RISK
                WHERE IS_FLAGGED = 1
                  AND MACHINE_CODE IN ({",".join(lit(t) for t in trusted)})
                GROUP BY MACHINE_CODE ORDER BY FLAGGED_HOURS DESC"""
        )
        for _, r in flagged.iterrows():
            hit = float(r["CONFIRMED"]) / float(r["FLAGGED_HOURS"]) * 100
            rows.append({
                "Owner": "Maintenance",
                "Site": "Plant B · PIADE",
                "Asset": r["MACHINE_CODE"],
                "Signal": "Hours flagged by the stop-risk model",
                "Observed": f"{int(r['FLAGGED_HOURS']):,} hours flagged on the holdout, "
                            f"{hit:.0f}% followed by a real heavy stop",
                "Magnitude": float(r["FLAGGED_HOURS"]),
                "Unit": "flagged hours",
                "Evidence": "Derived",
                "Suggested action": "Use as a watch list only. The model is a smoothed "
                                    "persistence rule and beats the do-nothing baseline "
                                    "on this line, but only modestly.",
            })
    untrusted = metrics[
        metrics["TOP_DECILE_PRECISION"] <= metrics["BASELINE_TOP_DECILE_PRECISION"]
    ]["SCOPE"].tolist()
    for code in untrusted:
        rows.append({
            "Owner": "Data gap",
            "Site": "Plant B · PIADE",
            "Asset": code,
            "Signal": "Model does not beat doing nothing",
            "Observed": "On the chronological holdout the matched baseline is at "
                        "least as precise as the model",
            "Magnitude": 0.0,
            "Unit": "—",
            "Evidence": "Derived",
            "Suggested action": "Do not deploy the risk score here. Fall back to the "
                                "simple rule until more history is available.",
        })

    # --- Plant A, reliability: drift ---------------------------------------
    drift = query(
        f"""SELECT MACHINE_CODE, COUNT(DISTINCT CHANNEL) AS CHANNELS,
                   LISTAGG(DISTINCT CHANNEL, ', ') WITHIN GROUP (ORDER BY CHANNEL) AS NAMES
            FROM {DB}.ML.PLANT_A_CHANNEL_DRIFT
            WHERE IS_DRIFTED GROUP BY MACHINE_CODE ORDER BY CHANNELS DESC"""
    )
    for _, r in drift.iterrows():
        rows.append({
            "Owner": "Reliability",
            "Site": "Plant A · CoMoPI",
            "Asset": r["MACHINE_CODE"],
            "Signal": "Sensor channels drifted from baseline",
            "Observed": f"{int(r['CHANNELS'])} channels sustained beyond 2 robust SD: "
                        f"{r['NAMES']}",
            "Magnitude": float(r["CHANNELS"]),
            "Unit": "drifted channels",
            "Evidence": "Derived",
            "Suggested action": "Inspect at the next planned stop. This means the "
                                "machine no longer behaves as it did when recording "
                                "began — it does NOT mean a failure is imminent.",
        })

    # --- Plant A, data gap --------------------------------------------------
    gaps = query(
        f"""WITH scored AS (
              SELECT MACHINE_CODE, COUNT_IF(IS_SCORED_PERIOD) AS W
              FROM {DB}.ML.PLANT_A_HEALTH GROUP BY MACHINE_CODE
            )
            SELECT f.MACHINE_CODE, COALESCE(s.W, 0) AS W
            FROM {DB}.GOLD.V_FLEET f LEFT JOIN scored s USING (MACHINE_CODE)
            WHERE f.PLANT_CODE='PLANT_A' AND COALESCE(s.W, 0) < 30
            ORDER BY f.MACHINE_CODE"""
    )
    for _, r in gaps.iterrows():
        rows.append({
            "Owner": "Data gap",
            "Site": "Plant A · CoMoPI",
            "Asset": r["MACHINE_CODE"],
            "Signal": "Not enough history to assess",
            "Observed": f"only {int(r['W'])} windows after its baseline period",
            "Magnitude": 0.0,
            "Unit": "—",
            "Evidence": "Observed",
            "Suggested action": "Show as unassessed, never as healthy. Extend "
                                "collection before drawing any conclusion.",
        })

    queue = pd.DataFrame(rows)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total actions", len(queue))
    k2.metric("Planning owns", int((queue["Owner"] == "Planning").sum()),
              help="Waiting time. The line was available and no fault was raised.")
    k3.metric("Maintenance owns", int((queue["Owner"] == "Maintenance").sum()),
              help="Recorded faults and machine-hours flagged as elevated risk.")
    k4.metric("Blocked by data", int((queue["Owner"] == "Data gap").sum()),
              help="Assets we deliberately refuse to score, rather than guessing.")

    order = ["Planning", "Maintenance", "Reliability", "Data gap"]
    blurb = {
        "Planning": "The largest single loss on either site. Nothing here is a repair job.",
        "Maintenance": "Real recorded faults, plus the machine-hours the model earns the right to flag.",
        "Reliability": "Condition drift at Plant A. Worth an inspection, not an intervention.",
        "Data gap": "Where the honest answer is that we cannot tell. Listed so it is not mistaken for good news.",
    }
    for owner in order:
        block = queue[queue["Owner"] == owner]
        if block.empty:
            continue
        block = block.sort_values("Magnitude", ascending=False)
        st.markdown(f"#### {owner}")
        st.caption(blurb[owner])
        st.dataframe(
            block[["Site", "Asset", "Signal", "Observed", "Evidence", "Suggested action"]],
            hide_index=True, use_container_width=True,
            column_config={
                "Site": st.column_config.TextColumn(width="small"),
                "Asset": st.column_config.TextColumn(width="small"),
                "Signal": st.column_config.TextColumn(width="medium"),
                "Observed": st.column_config.TextColumn(width="large"),
                "Evidence": st.column_config.TextColumn(width="small"),
                "Suggested action": st.column_config.TextColumn(width="large"),
            },
        )


# ---------------------------------------------------------------------------
# Page — Plant B OEE
# ---------------------------------------------------------------------------


def page_plant_b() -> None:
    hero("Plant B · OEE and where production is lost",
         "PIADE — 5 packaging lines. Looking backward over the full recorded history.")
    badges("OBSERVED", "DERIVED_FROM_OBSERVED")

    with st.expander("How to read this page"):
        st.markdown(
            "**OEE** multiplies three fractions, so a good score needs all three. "
            "**Availability** is run time over planned time — it drops when the line "
            "is stopped. **Performance** is what came out against what the line's own "
            "best demonstrated speed would have produced in that run time — it drops "
            "when the line runs slowly. **Quality** is packages out over packages in — "
            "it drops when product is lost in the process.\n\n"
            "Every figure is recomputed from summed seconds and package counts. "
            "None of them is an average of daily percentages, which would let a "
            "half-hour shift count as much as a full day."
        )

    fleet = query(
        f"""SELECT * FROM {DB}.GOLD.V_OEE_ROLLUP
            WHERE PLANT_CODE='PLANT_B' AND MACHINE_CODE IS NULL"""
    ).iloc[0]
    machines = query(
        f"""SELECT MACHINE_CODE, DAYS_OBSERVED, PLANNED_HOURS, RUN_HOURS,
                   BREAKDOWN_HOURS, IDLE_HOURS, SLOW_RUNNING_HOURS,
                   AVAILABILITY, PERFORMANCE, QUALITY, OEE
            FROM {DB}.GOLD.V_OEE_ROLLUP
            WHERE PLANT_CODE='PLANT_B' AND MACHINE_CODE IS NOT NULL
            ORDER BY MACHINE_CODE"""
    )

    a, b, c, d, e = st.columns(5)
    a.metric("OEE", pct(fleet["OEE"]),
             help="Availability × Performance × Quality, for the whole site.")
    b.metric("Availability", pct(fleet["AVAILABILITY"]),
             help="Run time over planned production time. The biggest loss here, "
                  "and most of it is waiting rather than breakdown.")
    c.metric("Performance", pct(fleet["PERFORMANCE"]),
             help="Actual output over what the line's best demonstrated rate would "
                  "have produced in the same run time. Not a vendor spec — the "
                  "benchmark is the line's own best hour.")
    d.metric("Quality", pct(fleet["QUALITY"]),
             help="Packages out over packages in. A throughput yield, not a lab "
                  "inspection result. Nearly perfect here, so it is not the problem.")
    e.metric("Planned hours", num(fleet["PLANNED_HOURS"]),
             f"{int(fleet['DAYS_OBSERVED'])} days", delta_color="off",
             help="Total time the lines were scheduled to produce.")

    t1, t2, t3, t4 = st.tabs(["By line", "Daily trend", "Loss Pareto", "Cost ownership"])

    with t1:
        st.caption("The weakest of the three terms differs by line, so the fix differs too.")
        melted = machines.melt(
            id_vars="MACHINE_CODE",
            value_vars=["AVAILABILITY", "PERFORMANCE", "QUALITY", "OEE"],
            var_name="Term", value_name="Value")
        melted["Term"] = melted["Term"].str.title()
        melted["Value"] = melted["Value"].astype(float)
        fig = px.bar(melted, x="MACHINE_CODE", y="Value", color="Term", barmode="group")
        fig.update_yaxes(tickformat=".0%", range=[0, 1.02])
        fig.update_traces(hovertemplate="%{x} · %{fullData.name}<br>%{y:.1%}<extra></extra>")
        chart(style_fig(fig, height=330))

        show = machines.copy()
        for col in ["AVAILABILITY", "PERFORMANCE", "QUALITY", "OEE"]:
            show[col] = show[col].astype(float)
        st.dataframe(
            show, hide_index=True, use_container_width=True,
            column_config={
                "MACHINE_CODE": "Line",
                "DAYS_OBSERVED": st.column_config.NumberColumn("Days", format="%d"),
                "PLANNED_HOURS": st.column_config.NumberColumn("Planned h", format="%.0f"),
                "RUN_HOURS": st.column_config.NumberColumn("Run h", format="%.0f"),
                "BREAKDOWN_HOURS": st.column_config.NumberColumn("Breakdown h", format="%.0f"),
                "IDLE_HOURS": st.column_config.NumberColumn("Idle h", format="%.0f"),
                "SLOW_RUNNING_HOURS": st.column_config.NumberColumn("Slow h", format="%.0f"),
                "AVAILABILITY": st.column_config.ProgressColumn(
                    "Availability", min_value=0.0, max_value=1.0, format="%.3f"),
                "PERFORMANCE": st.column_config.ProgressColumn(
                    "Performance", min_value=0.0, max_value=1.0, format="%.3f"),
                "QUALITY": st.column_config.ProgressColumn(
                    "Quality", min_value=0.0, max_value=1.0, format="%.3f"),
                "OEE": st.column_config.ProgressColumn(
                    "OEE", min_value=0.0, max_value=1.0, format="%.3f"),
            })

    with t2:
        picked = st.multiselect("Lines", machines["MACHINE_CODE"].tolist(),
                                default=machines["MACHINE_CODE"].tolist())
        if picked:
            daily = query(
                f"""SELECT OEE_DATE, MACHINE_CODE, OEE FROM {DB}.GOLD.V_OEE_DAILY
                    WHERE MACHINE_CODE IN ({",".join(lit(p) for p in picked)})
                    ORDER BY OEE_DATE"""
            )
            daily["OEE"] = daily["OEE"].astype(float)
            fig = px.line(daily, x="OEE_DATE", y="OEE", color="MACHINE_CODE")
            fig.update_yaxes(tickformat=".0%", range=[0, 1])
            fig.update_traces(line=dict(width=1.6),
                              hovertemplate="%{x|%d %b %Y}<br>%{y:.1%}<extra></extra>")
            fig.add_hline(y=float(fleet["OEE"]), line_dash="dot", line_color=INK2,
                          line_width=1, annotation_text="Site weighted OEE",
                          annotation_font_size=11, annotation_font_color=INK2)
            chart(style_fig(fig, height=420))
            st.caption("The dotted line is the weighted site OEE. Daily points scatter "
                       "widely around it, which is why the single averaged figure is "
                       "not a safe summary on its own.")

    with t3:
        st.caption("Idle and breakdown are separated because they have different "
                   "owners. Every downtime interval in the source carries an alarm "
                   "code; every interval without one is idle.")
        pareto = query(
            f"""SELECT CAUSE_CODE, LOSS_NATURE, OWNING_FUNCTION, STOP_PATTERN,
                       STOP_COUNT, STOP_HOURS, MEDIAN_STOP_MIN,
                       PCT_OF_STOP_TIME, CUMULATIVE_PCT
                FROM {DB}.GOLD.V_DOWNTIME_PARETO
                WHERE PLANT_CODE='PLANT_B' ORDER BY STOP_HOURS DESC"""
        )
        top = pareto.head(14).copy()
        top["STOP_HOURS"] = top["STOP_HOURS"].astype(float)
        top["CUMULATIVE_PCT"] = top["CUMULATIVE_PCT"].astype(float)
        fig = go.Figure()
        fig.add_bar(x=top["CAUSE_CODE"], y=top["STOP_HOURS"], name="Stop hours",
                    marker_color=["#e59f23" if n == "WAITING" else "#0b7482"
                                  for n in top["LOSS_NATURE"]],
                    hovertemplate="%{x}<br>%{y:,.0f} h<extra></extra>")
        fig.add_scatter(x=top["CAUSE_CODE"], y=top["CUMULATIVE_PCT"], name="Cumulative %",
                        yaxis="y2", mode="lines+markers",
                        line=dict(color=INK2, width=1.6), marker=dict(size=5),
                        hovertemplate="%{y:.1f}% cumulative<extra></extra>")
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", range=[0, 105],
                                      showgrid=False, ticksuffix="%",
                                      tickfont=dict(size=11)))
        fig.update_yaxes(ticksuffix=" h")
        chart(style_fig(fig, height=380))
        plain("Amber is <b>waiting</b> — available, no fault raised, owned by "
              "planning. Teal is <b>faulted</b>, owned by maintenance.")
        st.dataframe(
            pareto.head(25), hide_index=True, use_container_width=True,
            column_config={
                "CAUSE_CODE": "Cause", "LOSS_NATURE": "Nature",
                "OWNING_FUNCTION": "Owner", "STOP_PATTERN": "Pattern",
                "STOP_COUNT": st.column_config.NumberColumn("Stops", format="%d"),
                "STOP_HOURS": st.column_config.NumberColumn("Hours", format="%.1f"),
                "MEDIAN_STOP_MIN": st.column_config.NumberColumn("Median min", format="%.1f"),
                "PCT_OF_STOP_TIME": st.column_config.NumberColumn("% of stop time", format="%.2f"),
                "CUMULATIVE_PCT": st.column_config.NumberColumn("Cumulative %", format="%.2f"),
            })

    with t4:
        badges("SYNTHETIC_IT")
        caveat("<b>These euros are invented.</b> Labour rate, parts draws and "
               "contribution margin are chosen assumptions; only the stop durations "
               "underneath them are observed. The ratio between the two bars is the "
               "finding — the absolute values are illustrative.")
        costs = query(
            f"""SELECT MACHINE_CODE, WORK_ORDERS, BREAKDOWN_HOURS, MAINTENANCE_COST,
                       IDLE_INCIDENTS, IDLE_HOURS, IDLE_FORGONE_MARGIN,
                       PCT_COST_FROM_IDLING
                FROM {DB}.GOLD.V_COST_BY_MACHINE
                WHERE PLANT_CODE='PLANT_B' ORDER BY MACHINE_CODE"""
        )
        melted = costs.melt(id_vars="MACHINE_CODE",
                            value_vars=["MAINTENANCE_COST", "IDLE_FORGONE_MARGIN"],
                            var_name="Kind", value_name="EUR")
        melted["Kind"] = melted["Kind"].map({
            "MAINTENANCE_COST": "Maintenance (faults)",
            "IDLE_FORGONE_MARGIN": "Forgone margin (waiting)"})
        melted["EUR"] = melted["EUR"].astype(float)
        fig = px.bar(melted, x="MACHINE_CODE", y="EUR", color="Kind", barmode="stack",
                     color_discrete_map={"Maintenance (faults)": "#0b7482",
                                         "Forgone margin (waiting)": "#e59f23"})
        fig.update_traces(hovertemplate="%{x} · %{fullData.name}<br>€%{y:,.0f}<extra></extra>")
        fig.update_yaxes(tickprefix="€")
        chart(style_fig(fig, height=330))
        st.dataframe(
            costs, hide_index=True, use_container_width=True,
            column_config={
                "MACHINE_CODE": "Line",
                "WORK_ORDERS": st.column_config.NumberColumn("Work orders", format="%d"),
                "BREAKDOWN_HOURS": st.column_config.NumberColumn("Breakdown h", format="%.1f"),
                "MAINTENANCE_COST": st.column_config.NumberColumn("Maintenance €", format="%.0f"),
                "IDLE_INCIDENTS": st.column_config.NumberColumn("Idle incidents", format="%d"),
                "IDLE_HOURS": st.column_config.NumberColumn("Idle h", format="%.1f"),
                "IDLE_FORGONE_MARGIN": st.column_config.NumberColumn("Forgone €", format="%.0f"),
                "PCT_COST_FROM_IDLING": st.column_config.ProgressColumn(
                    "% from waiting", min_value=0.0, max_value=100.0, format="%.1f"),
            })
        cortex_brief("PLANT_B_COST")


# ---------------------------------------------------------------------------
# Page — Plant B risk
# ---------------------------------------------------------------------------


def page_risk() -> None:
    hero("Plant B · Next-hour stop risk",
         "PIADE — the same 5 lines, looking one hour forward instead of backward.")
    badges("DERIVED_FROM_OBSERVED")

    with st.expander("How to read this page"):
        st.markdown(
            "The model scores each machine-hour for the chance that **the next hour** "
            "loses more than 10% of its time to unplanned downtime. It is trained on "
            "everything before 2021-08-01 and scored only on what came after, so it "
            "never sees its own test period.\n\n"
            "The operating point is the **riskiest 10% of hours**, because no team can "
            "react to half the hours in a week. **Precision** is how often those flags "
            "were right.\n\n"
            "The number that matters is not precision against the base rate — it is "
            "precision against the **do-nothing baseline**, the trivial rule *this hour "
            "already had downtime*. Anything a free rule already achieves is not worth "
            "attributing to a model."
        )

    metrics = query(
        f"""SELECT SCOPE, TEST_ROWS, AUC,
                   ROUND(BASE_RATE * 100, 1)                     AS BASE_RATE_PCT,
                   ROUND(TOP_DECILE_PRECISION * 100, 1)          AS PRECISION_PCT,
                   ROUND(BASELINE_TOP_DECILE_PRECISION * 100, 1) AS BASELINE_PCT,
                   ROUND(TOP_DECILE_RECALL * 100, 1)             AS RECALL_PCT
            FROM {DB}.ML.PLANT_B_MODEL_METRICS
            ORDER BY IFF(SCOPE='FLEET', 0, 1), SCOPE"""
    )
    fleet = metrics[metrics["SCOPE"] == "FLEET"].iloc[0]
    per_machine = metrics[metrics["SCOPE"] != "FLEET"].copy()
    per_machine["BEATS_BASELINE"] = per_machine["PRECISION_PCT"] > per_machine["BASELINE_PCT"]

    a, b, c, d, e = st.columns(5)
    a.metric("Model precision", f"{float(fleet['PRECISION_PCT']):.1f}%",
             help="Of the riskiest 10% of hours flagged, this share really did suffer "
                  "a heavy stop in the following hour.")
    b.metric("Do-nothing baseline", f"{float(fleet['BASELINE_PCT']):.1f}%",
             help="What you get for free from the rule 'this hour already had "
                  "downtime'. This is the number the model must beat to be worth "
                  "anything.")
    c.metric("Base rate", f"{float(fleet['BASE_RATE_PCT']):.1f}%",
             help="Share of all holdout hours that were heavy stops regardless. "
                  "Comparing to this flatters the model, which is why it is not the "
                  "headline.")
    d.metric("AUC", f"{float(fleet['AUC']):.3f}",
             help="Ranking quality over the whole holdout. 0.5 is a coin flip, 1.0 is "
                  "perfect. This is modest and deliberately not dressed up.")
    e.metric("Holdout hours", num(fleet["TEST_ROWS"]),
             help="Machine-hours scored but never trained on.")

    caveat(
        f"<b>Read the first two cards together.</b> The model is worth "
        f"{float(fleet['PRECISION_PCT']):.1f}% against the matched do-nothing rule's "
        f"{float(fleet['BASELINE_PCT']):.1f}% — not against the "
        f"{float(fleet['BASE_RATE_PCT']):.1f}% base rate. Feature importance is "
        f"dominated by 24-hour rolling downtime, so this is honestly described as a "
        f"smoothed persistence rule, not a discovery of new failure physics."
    )

    st.markdown("#### Does it beat doing nothing, line by line?")
    st.caption("The site-wide number hides the weak lines. This is the honest view.")
    comp = per_machine.melt(id_vars="SCOPE",
                            value_vars=["PRECISION_PCT", "BASELINE_PCT"],
                            var_name="Kind", value_name="Precision")
    comp["Kind"] = comp["Kind"].map({"PRECISION_PCT": "Model",
                                     "BASELINE_PCT": "Do-nothing baseline"})
    comp["Precision"] = comp["Precision"].astype(float)
    fig = px.bar(comp, x="SCOPE", y="Precision", color="Kind", barmode="group",
                 color_discrete_map={"Model": "#0b7482",
                                     "Do-nothing baseline": "#bcc9d3"})
    fig.update_yaxes(ticksuffix="%")
    fig.update_traces(hovertemplate="%{x} · %{fullData.name}<br>%{y:.1f}%<extra></extra>")
    chart(style_fig(fig, height=300))

    losers = per_machine[~per_machine["BEATS_BASELINE"]]["SCOPE"].tolist()
    if losers:
        caveat("<b>Do not present the model as an improvement on "
               + esc(", ".join(losers))
               + ".</b> On the holdout its matched baseline is at least as precise, "
                 "so the model adds cost without adding information for that line. "
                 "It is excluded from the Action queue for exactly this reason.")

    st.dataframe(
        per_machine[["SCOPE", "TEST_ROWS", "AUC", "BASE_RATE_PCT", "PRECISION_PCT",
                     "BASELINE_PCT", "RECALL_PCT", "BEATS_BASELINE"]],
        hide_index=True, use_container_width=True,
        column_config={
            "SCOPE": "Line",
            "TEST_ROWS": st.column_config.NumberColumn("Holdout hours", format="%d"),
            "AUC": st.column_config.NumberColumn("AUC", format="%.3f"),
            "BASE_RATE_PCT": st.column_config.NumberColumn("Base rate %", format="%.1f"),
            "PRECISION_PCT": st.column_config.NumberColumn("Model %", format="%.1f"),
            "BASELINE_PCT": st.column_config.NumberColumn("Baseline %", format="%.1f"),
            "RECALL_PCT": st.column_config.NumberColumn("Recall %", format="%.1f"),
            "BEATS_BASELINE": st.column_config.CheckboxColumn("Beats baseline"),
        })

    st.markdown("#### Scored hours, and what drives the score")
    left, right = st.columns([1.45, 1], gap="medium")
    with left:
        line = st.selectbox("Line", per_machine["SCOPE"].tolist())
        scores = query(
            f"""SELECT HOUR_TS, RISK_SCORE, IS_FLAGGED, ACTUAL_HEAVY_STOP
                FROM {DB}.GOLD.V_PLANT_B_RISK WHERE MACHINE_CODE={lit(line)}
                ORDER BY HOUR_TS DESC LIMIT 336"""
        ).sort_values("HOUR_TS")
        scores["RISK_SCORE"] = scores["RISK_SCORE"].astype(float)
        fig = go.Figure()
        fig.add_scatter(x=scores["HOUR_TS"], y=scores["RISK_SCORE"], name="Risk score",
                        mode="lines", line=dict(color=ACCENT, width=1.5),
                        hovertemplate="%{x|%d %b %H:%M}<br>%{y:.1%}<extra></extra>")
        hits = scores[(scores["IS_FLAGGED"] == 1) & (scores["ACTUAL_HEAVY_STOP"] == 1)]
        miss = scores[(scores["IS_FLAGGED"] == 1) & (scores["ACTUAL_HEAVY_STOP"] == 0)]
        fig.add_scatter(x=hits["HOUR_TS"], y=hits["RISK_SCORE"], mode="markers",
                        name="Flagged — stop followed",
                        marker=dict(color="#13864d", size=7))
        fig.add_scatter(x=miss["HOUR_TS"], y=miss["RISK_SCORE"], mode="markers",
                        name="Flagged — false alarm",
                        marker=dict(color="#ba3131", size=7, symbol="x"))
        fig.update_yaxes(tickformat=".0%", range=[0, 1])
        chart(style_fig(fig, height=360))
        st.caption("The flag threshold is site-wide, so the two worst lines absorb "
                   "most of the alerts. A quiet line showing very few markers is "
                   "expected, not a bug.")
    with right:
        imp = query(
            f"""SELECT FEATURE, IMPORTANCE FROM {DB}.ML.PLANT_B_FEATURE_IMPORTANCE
                ORDER BY RANK LIMIT 12"""
        ).sort_values("IMPORTANCE")
        imp["IMPORTANCE"] = imp["IMPORTANCE"].astype(float)
        fig = px.bar(imp, x="IMPORTANCE", y="FEATURE", orientation="h")
        fig.update_traces(marker_color=ACCENT,
                          hovertemplate="%{y}<br>%{x:.3f}<extra></extra>")
        chart(style_fig(fig, height=360, legend=False))
        st.caption("Rolling downtime dominates — hence 'smoothed persistence rule'.")

    cortex_brief("PLANT_B_MODEL", "Cortex readout — how much to trust this")


# ---------------------------------------------------------------------------
# Page — Plant A
# ---------------------------------------------------------------------------


def page_plant_a() -> None:
    hero("Plant A · Condition drift",
         "CoMoPI — 8 closure machines, 16 anonymised sensor channels. A different factory.")
    badges("DERIVED_FROM_OBSERVED")

    with st.expander("How to read this page"):
        st.markdown(
            "This is a **different dataset from Plant B** — different factory, "
            "different machines, no shared time or key. It has sensors but no "
            "production counts, so OEE cannot be computed here at any level.\n\n"
            "Each machine is scored against **its own first 200 windows**, using "
            "median and interquartile range rather than mean and standard deviation "
            "so that a few extreme windows cannot distort the baseline. A health "
            "index of 100 means indistinguishable from that baseline; 0 means a mean "
            "deviation of six robust standard deviations or worse.\n\n"
            "A supervised failure model was built here first and **abandoned after "
            "measurement** — AUC between 0.48 and 0.54 at every horizon tried, which "
            "is a coin flip. That negative result is why this page shows drift rather "
            "than a prediction."
        )

    status = query(
        f"""WITH scored AS (
              SELECT MACHINE_CODE, COUNT_IF(IS_SCORED_PERIOD) AS SCORED_WINDOWS
              FROM {DB}.ML.PLANT_A_HEALTH GROUP BY MACHINE_CODE
            ),
            latest AS (
              SELECT MACHINE_CODE, HEALTH_INDEX_AVG, HEALTH_INDEX_WORST, DOMINANT_CHANNEL
              FROM {DB}.GOLD.V_PLANT_A_HEALTH WHERE ANY_SCORED_PERIOD
              QUALIFY ROW_NUMBER() OVER (
                PARTITION BY MACHINE_CODE ORDER BY HEALTH_DATE DESC) = 1
            )
            SELECT f.MACHINE_CODE,
                   IFF(COALESCE(s.SCORED_WINDOWS,0) < 30, 'Not assessed', 'Scored') AS STATUS,
                   COALESCE(s.SCORED_WINDOWS,0) AS SCORED_WINDOWS,
                   l.HEALTH_INDEX_AVG, l.HEALTH_INDEX_WORST, l.DOMINANT_CHANNEL,
                   f.FIRST_SEEN, f.LAST_SEEN
            FROM {DB}.GOLD.V_FLEET f
            LEFT JOIN scored s USING (MACHINE_CODE)
            LEFT JOIN latest l USING (MACHINE_CODE)
            WHERE f.PLANT_CODE='PLANT_A' ORDER BY f.MACHINE_CODE"""
    )
    assessed = status[status["STATUS"] == "Scored"]
    unassessed = status[status["STATUS"] != "Scored"]["MACHINE_CODE"].tolist()

    a, b, c, d = st.columns(4)
    a.metric("Machines in source", len(status),
             help="Published by the CoMoPI authors.")
    b.metric("Assessed", len(assessed),
             help="Machines with at least 30 windows of history after their own "
                  "baseline period, which is the minimum to say anything.")
    c.metric("Not assessed", len(unassessed),
             ", ".join(unassessed) if unassessed else "none", delta_color="off",
             help="Deliberately left unscored rather than guessed. Absence of a "
                  "score is not a clean bill of health.")
    d.metric("Mean health", f"{assessed['HEALTH_INDEX_AVG'].astype(float).mean():.1f}/100",
             help="Latest day, averaged across assessed machines.")

    caveat(
        "<b>This index is not a failure probability.</b> It was checked against what "
        "actually happened next: windows in the worst health decile were followed by "
        "an alarm 21.2% of the time, against 17.7% for the best decile. That gap is "
        "far too small to act on. What the index does tell you is that a machine no "
        "longer behaves the way it did when recording began — a real signal, but a "
        "different one from \u201cit is about to break\u201d."
    )

    st.dataframe(
        status, hide_index=True, use_container_width=True,
        column_config={
            "MACHINE_CODE": "Machine", "STATUS": "Status",
            "SCORED_WINDOWS": st.column_config.NumberColumn("Scored windows", format="%d"),
            "HEALTH_INDEX_AVG": st.column_config.ProgressColumn(
                "Latest health", min_value=0.0, max_value=100.0, format="%.1f"),
            "HEALTH_INDEX_WORST": st.column_config.NumberColumn("Worst window", format="%.1f"),
            "DOMINANT_CHANNEL": "Leading channel",
            "FIRST_SEEN": st.column_config.DatetimeColumn("First seen", format="DD MMM YYYY"),
            "LAST_SEEN": st.column_config.DatetimeColumn("Last seen", format="DD MMM YYYY"),
        })

    st.markdown("#### Per-machine history")
    machine = st.selectbox("Machine", assessed["MACHINE_CODE"].tolist())
    left, right = st.columns([1.45, 1], gap="medium")

    with left:
        daily = query(
            f"""SELECT HEALTH_DATE, HEALTH_INDEX_AVG, HEALTH_INDEX_WORST
                FROM {DB}.GOLD.V_PLANT_A_HEALTH
                WHERE MACHINE_CODE={lit(machine)} AND ANY_SCORED_PERIOD
                ORDER BY HEALTH_DATE"""
        )
        daily["HEALTH_INDEX_AVG"] = daily["HEALTH_INDEX_AVG"].astype(float)
        daily["HEALTH_INDEX_WORST"] = daily["HEALTH_INDEX_WORST"].astype(float)
        fig = go.Figure()
        fig.add_scatter(x=daily["HEALTH_DATE"], y=daily["HEALTH_INDEX_WORST"],
                        name="Worst window that day", mode="lines",
                        line=dict(color="#dcc49c", width=1), fill="tozeroy",
                        fillcolor="rgba(229,159,35,.10)",
                        hovertemplate="%{x|%d %b %Y}<br>worst %{y:.1f}<extra></extra>")
        fig.add_scatter(x=daily["HEALTH_DATE"], y=daily["HEALTH_INDEX_AVG"],
                        name="Daily average", mode="lines",
                        line=dict(color=ACCENT, width=2),
                        hovertemplate="%{x|%d %b %Y}<br>average %{y:.1f}<extra></extra>")
        fig.update_yaxes(range=[0, 102])
        chart(style_fig(fig, height=360))

    with right:
        drift = query(
            f"""SELECT CHANNEL, MEAN_SIGNED_Z FROM {DB}.ML.PLANT_A_CHANNEL_DRIFT
                WHERE MACHINE_CODE={lit(machine)} AND IS_DRIFTED
                QUALIFY ROW_NUMBER() OVER (
                  PARTITION BY CHANNEL ORDER BY ABS(MEAN_SIGNED_Z) DESC) = 1
                ORDER BY MEAN_SIGNED_Z"""
        )
        if drift.empty:
            plain("No channel on this machine shows sustained monthly drift beyond "
                  "the threshold. Its readings still resemble its own baseline. Only "
                  "A005 and B002 have drifted channels.")
        else:
            drift["MEAN_SIGNED_Z"] = drift["MEAN_SIGNED_Z"].astype(float)
            fig = px.bar(drift, x="MEAN_SIGNED_Z", y="CHANNEL", orientation="h")
            fig.update_traces(
                marker_color=["#ba3131" if v < 0 else "#0b7482"
                              for v in drift["MEAN_SIGNED_Z"]],
                hovertemplate="%{y}<br>%{x:.2f} robust SD from baseline<extra></extra>")
            fig.add_vline(x=0, line_color=LINE, line_width=1)
            chart(style_fig(fig, height=360, legend=False))
            st.caption("Strongest drifted month per channel, in robust standard "
                       "deviations from that machine's own baseline.")

    cortex_brief("PLANT_A_HEALTH", "Cortex readout — what this index means")


# ---------------------------------------------------------------------------
# Page — Provenance
# ---------------------------------------------------------------------------


def page_trust() -> None:
    hero("Provenance", "Where every number on every page comes from.")
    badges("OBSERVED", "DERIVED_FROM_OBSERVED", "SYNTHETIC_IT")

    plain(
        "<b>Observed</b> means published by the dataset author. <b>Derived</b> means "
        "computed here from published values only. <b>Synthetic</b> means invented "
        "here and anchored one-to-one to a real observed event. Nothing in this "
        "application is unlabelled."
    )

    st.dataframe(
        query(f"""SELECT PLANT_CODE, SUBJECT, DATA_ORIGIN, SOURCE, NOTE
                  FROM {DB}.GOLD.V_PROVENANCE ORDER BY PLANT_CODE, SUBJECT"""),
        hide_index=True, use_container_width=True,
        column_config={"PLANT_CODE": "Plant", "SUBJECT": "Subject",
                       "DATA_ORIGIN": "Origin", "SOURCE": "Source", "NOTE": "Note"})

    st.markdown("#### Assumptions behind every synthetic euro")
    st.caption("Each row is a number we chose rather than measured, unless the "
               "Measured box is ticked.")
    st.dataframe(
        query(f"""SELECT PLANT_SCOPE, NAME, VALUE, UNIT, IS_MEASURED, BASIS
                  FROM {DB}.GOLD.IT_ASSUMPTION ORDER BY PLANT_SCOPE, NAME"""),
        hide_index=True, use_container_width=True,
        column_config={
            "PLANT_SCOPE": "Applies to", "NAME": "Assumption",
            "VALUE": st.column_config.NumberColumn("Value", format="%.2f"),
            "UNIT": "Unit",
            "IS_MEASURED": st.column_config.CheckboxColumn("Measured"),
            "BASIS": "Why this value"})

    st.markdown("#### What this application does not establish")
    caveat(
        "It does not establish a causal failure mechanism for any alarm code — both "
        "publishers anonymised them. It does not estimate remaining useful life. It "
        "does not compute OEE or lost output for Plant A, which has no production "
        "counts. It does not use a vendor-rated ideal speed; the Performance "
        "denominator is each line\u2019s own best demonstrated rate. It does not claim "
        "realised savings, because no intervention was ever carried out. And it does "
        "not relate Plant A to Plant B at the data level, because no such relationship "
        "exists in the sources."
    )


# ---------------------------------------------------------------------------
# Shell
# ---------------------------------------------------------------------------

PAGES = {
    "Overview": page_overview,
    "Action queue": page_actions,
    "Plant B · OEE & loss": page_plant_b,
    "Plant B · Stop risk": page_risk,
    "Plant A · Condition drift": page_plant_a,
    "Provenance": page_trust,
}

with st.sidebar:
    st.markdown('<div class="sb-brand">❄️ SnowCore</div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-tag">Predictive Maintenance<br>&amp; OEE Command Center</div>',
                unsafe_allow_html=True)
    choice = st.radio("Navigate", list(PAGES), label_visibility="collapsed")
    st.markdown('<div class="sb-rule"></div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-h">Which dataset is which</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sb-map"><b>Plant B = PIADE</b><br>'
        '<span>5 packaging lines. Production states, stop alarms, package counters. '
        'No sensors.</span></div>'
        '<div class="sb-map"><b>Plant A = CoMoPI</b><br>'
        '<span>8 closure machines. 16 anonymised sensor channels. '
        'No production counts.</span></div>',
        unsafe_allow_html=True)
    st.markdown('<div class="sb-rule"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sb-map"><span>Both CC BY 4.0. All times UTC. Neither ships any '
        'maintenance records — every euro here is synthetic.</span></div>',
        unsafe_allow_html=True)

try:
    PAGES[choice]()
except Exception as exc:
    st.error("This page could not be rendered.")
    st.exception(exc)
