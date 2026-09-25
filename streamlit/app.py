"""PIADE Packaging Site management operations console.

Streamlit in Snowflake. The application is read-only against historical facts;
the only user-created records live in Streamlit session state.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from snowflake.snowpark.context import get_active_session


DB = "SNOWCORE_REAL"
LINES = ["s_1", "s_2", "s_3", "s_4", "s_5"]
LOGGER = logging.getLogger(__name__)
AMBER = "#d99a2b"
RED = "#d14b52"
TEAL = "#2a9d9f"
BLUE = "#4f7cac"
SLATE = "#6b7a8a"
# Muted ramp for per-line series; risk colours stay reserved for exceptions.
LINE_RAMP = ["#4f7cac", "#6f93bc", "#8fa9c9", "#5f7a8c", "#7d8e9c"]

st.set_page_config(
    page_title="PIADE | Operations Console",
    page_icon="▦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Theme and shell
# ---------------------------------------------------------------------------

if "dark_theme" not in st.session_state:
    st.session_state.dark_theme = True


def inject_theme(dark: bool) -> None:
    bg = "#0a0e14" if dark else "#f4f6f8"
    panel = "#111821" if dark else "#ffffff"
    panel2 = "#151e29" if dark else "#edf1f4"
    text = "#edf2f6" if dark else "#17212b"
    muted = "#95a1ad" if dark else "#5e6b78"
    border = "#26313d" if dark else "#d6dde3"
    sidebar = "#0d131b" if dark else "#e8edf1"
    st.markdown(
        f"""
        <style>
        :root {{
          --ops-bg:{bg}; --ops-panel:{panel}; --ops-panel2:{panel2};
          --ops-text:{text}; --ops-muted:{muted}; --ops-border:{border};
        }}
        .stApp, [data-testid="stAppViewContainer"] {{ background:{bg}; color:{text}; }}
        .block-container {{ padding:1rem 1.25rem 1.6rem; max-width:1500px; }}
        [data-testid="stSidebar"] {{ background:{sidebar}; border-right:1px solid {border}; }}
        [data-testid="stSidebar"] .block-container {{ padding:1rem .8rem; }}
        [data-testid="stSidebar"] .stMarkdown p,
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
        [data-testid="stSidebar"] [role="radiogroup"] label p {{ color:{text}; }}
        [data-testid="stSidebar"] [role="radiogroup"] label {{
          border-radius:4px; padding:.27rem .45rem;
        }}
        [data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background:{panel2}; }}
        h1,h2,h3,h4,p,li,label,[data-testid="stCaptionContainer"] {{
          color:{text};
          font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
        }}
        h1 {{ font-size:1.42rem !important; letter-spacing:-.02em; margin:0 !important; }}
        h2 {{ font-size:1.12rem !important; }}
        h3 {{ font-size:.94rem !important; letter-spacing:.01em; }}
        [data-testid="stCaptionContainer"], .muted {{ color:{muted} !important; }}
        .ops-header {{
          display:flex; justify-content:space-between; align-items:flex-end;
          border-bottom:1px solid {border}; padding:.1rem 0 .65rem; margin-bottom:.7rem;
        }}
        .ops-title {{ font-size:1.38rem; font-weight:720; letter-spacing:-.025em; }}
        .ops-meta {{ color:{muted}; font-size:.72rem; text-align:right; line-height:1.45; }}
        .eyebrow {{ color:{muted}; font-size:.64rem; font-weight:700;
          letter-spacing:.12em; text-transform:uppercase; }}
        .tag {{ display:inline-block; border:1px solid {border}; border-radius:3px;
          padding:.08rem .34rem; margin-left:.25rem; color:{muted}; font-size:.64rem; }}
        .tag-risk {{ color:{AMBER}; border-color:{AMBER}; }}
        .tag-exception {{ color:{RED}; border-color:{RED}; }}
        div[data-testid="stMetric"] {{
          background:{panel}; border:1px solid {border}; border-radius:5px;
          padding:.52rem .68rem;
        }}
        div[data-testid="stMetricLabel"] p {{ color:{muted}; font-size:.72rem; font-weight:650; }}
        div[data-testid="stMetricValue"] {{ color:{text}; font-size:1.35rem; }}
        div[data-testid="stMetricDelta"] {{ font-size:.67rem; }}
        div[data-testid="stDataFrame"] {{ border:1px solid {border}; border-radius:4px; }}
        [data-testid="stExpander"] {{ border:1px solid {border}; border-radius:4px; background:{panel}; }}
        [data-testid="stAlert"] {{ border-radius:4px; }}
        .section-title {{ font-size:.78rem; font-weight:720; letter-spacing:.04em;
          text-transform:uppercase; border-bottom:1px solid {border};
          padding-bottom:.3rem; margin:.75rem 0 .45rem; }}
        .notice {{ border-left:3px solid {AMBER}; background:{panel};
          padding:.45rem .65rem; font-size:.75rem; color:{muted}; margin:.4rem 0; }}
        .source-line {{ font-size:.68rem; color:{muted}; border-top:1px solid {border};
          margin-top:.6rem; padding-top:.4rem; }}
        .stButton button, .stDownloadButton button {{
          border-radius:4px; border:1px solid {border}; box-shadow:none;
        }}
        .stTabs [data-baseweb="tab"] {{ font-size:.78rem; padding:.35rem .65rem; }}
        hr {{ border-color:{border}; }}
        #MainMenu, footer {{ visibility:hidden; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def header(title: str, subtitle: str = "", as_of: object = None, status: str = "Operational") -> None:
    stamp = "Latest warehouse refresh" if as_of is None or pd.isna(as_of) else str(as_of)
    st.markdown(
        f'<div class="ops-header"><div><div class="eyebrow">PIADE Packaging Site</div>'
        f'<div class="ops-title">{esc(title)}</div><div class="muted">{esc(subtitle)}</div></div>'
        f'<div class="ops-meta">DATA AS OF · {esc(stamp)}<br>MODEL · {esc(status)}</div></div>',
        unsafe_allow_html=True,
    )


def section(title: str) -> None:
    st.markdown(f'<div class="section-title">{esc(title)}</div>', unsafe_allow_html=True)


def origin_note(observed: bool = True, synthetic: bool = False, text: str = "") -> None:
    chips = []
    if observed:
        chips.append('<span class="tag">OBSERVED / DERIVED</span>')
    if synthetic:
        chips.append('<span class="tag tag-risk">SYNTHETIC SCENARIO</span>')
    st.markdown(
        f'<div class="source-line">{"".join(chips)} {esc(text)}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Data access and defensive schema helpers
# ---------------------------------------------------------------------------


def session():
    """Return the request's Snowflake session; never cache across app users."""
    return get_active_session()


@st.cache_data(ttl=600, show_spinner=False)
def query(sql: str) -> pd.DataFrame:
    return session().sql(sql).to_pandas()


def load(name: str, sql: str) -> pd.DataFrame:
    """Load a dataset while making query failures visible to the operator."""
    try:
        return query(sql)
    except Exception as exc:
        # Snowflake exceptions can echo the complete SQL statement. The
        # Analyst statement includes the bounded context and user question,
        # so neither the exception nor traceback belongs in the client.
        LOGGER.error("%s failed (%s)", name, type(exc).__name__)
        st.error(f"{name} is temporarily unavailable. Retry or contact the app owner.")
        return pd.DataFrame()


def table(schema: str, name: str, limit: int | None = None) -> pd.DataFrame:
    suffix = f" LIMIT {int(limit)}" if limit else ""
    return load(name, f"SELECT * FROM {DB}.{schema}.{name}{suffix}")


def col(df: pd.DataFrame, *candidates: str) -> str | None:
    lookup = {str(c).upper(): c for c in df.columns}
    for candidate in candidates:
        if candidate.upper() in lookup:
            return lookup[candidate.upper()]
    return None


def series(df: pd.DataFrame, *candidates: str, default: object = None) -> pd.Series:
    found = col(df, *candidates)
    return df[found] if found else pd.Series([default] * len(df), index=df.index)


def scalar(df: pd.DataFrame, candidates: tuple[str, ...], default: object = None) -> object:
    if df.empty:
        return default
    found = col(df, *candidates)
    return df.iloc[0][found] if found else default


def number(value: object, digits: int = 0, prefix: str = "", suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{prefix}{float(value):,.{digits}f}{suffix}"


def percent(value: object, digits: int = 1, already_percent: bool = False) -> str:
    if value is None or pd.isna(value):
        return "—"
    v = float(value)
    if not already_percent and abs(v) <= 1:
        v *= 100
    return f"{v:.{digits}f}%"


def safe_lines(df: pd.DataFrame) -> pd.DataFrame:
    machine = col(df, "MACHINE_CODE", "LINE_ID", "LINE_CODE")
    if not machine:
        return df
    return df[df[machine].astype(str).isin(LINES)].copy()


def sql_literal(value: object, max_len: int = 6000) -> str:
    clean = str(value)[:max_len].replace("\x00", "").replace("'", "''")
    return f"'{clean}'"


def style_fig(fig: go.Figure, height: int = 280, legend: bool = True) -> go.Figure:
    dark = st.session_state.dark_theme
    text = "#aeb8c2" if dark else "#4f5d69"
    grid = "#202a35" if dark else "#e3e8ec"
    fig.update_layout(
        height=height,
        margin=dict(l=5, r=8, t=24 if legend else 8, b=5),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, sans-serif", size=11, color=text),
        showlegend=legend,
        legend=dict(orientation="h", y=1.01, x=0, title=None, font=dict(size=10)),
        hoverlabel=dict(font_size=11),
        colorway=[TEAL, BLUE, AMBER, RED, "#7e8b98"],
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=grid, title=None)
    fig.update_yaxes(showgrid=True, gridcolor=grid, zeroline=False, title=None)
    return fig


def chart(fig: go.Figure) -> None:
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ---------------------------------------------------------------------------
# Display contract
#
# Warehouse columns are SCREAMING_SNAKE and unscaled. Leadership tables need
# short labels, the unit in the header, and a human magnitude in the cell.
# Values stay numeric so column sorting remains correct.
# ---------------------------------------------------------------------------

# kind -> (multiplier applied for display, printf format)
KIND_SPEC: dict[str, tuple[float, str]] = {
    "pct": (100.0, "%.1f%%"),
    "pct100": (1.0, "%.1f%%"),
    "pts": (1.0, "%+.1f"),
    "score": (1.0, "%.3f"),
    "hours": (1.0, "%.0f"),
    "hours1": (1.0, "%.1f"),
    "minutes": (1.0, "%.0f"),
    "thousands": (1e-3, "%.0f"),
    "eur": (1.0, "%.0f"),
    "eur2": (1.0, "%.2f"),
    "eur_k": (1e-3, "%.1f"),
    "eur_m": (1e-6, "%.2f"),
    "int": (1.0, "%.0f"),
}

COLUMN_META: dict[str, tuple[str, str]] = {
    "MACHINE_CODE": ("Line", "text"),
    "SCOPE": ("Scope", "text"),
    "GRAIN": ("Grain", "text"),
    "OEE": ("OEE", "pct"),
    "AVAILABILITY": ("Availability", "pct"),
    "PERFORMANCE": ("Performance", "pct"),
    "QUALITY": ("Quality", "pct"),
    "LAST_RISK_SCORE": ("Risk score", "score"),
    "RISK_PERCENTILE": ("Risk pctile", "pct"),
    "RISK_BAND": ("Risk band", "text"),
    "RISK_STATE": ("State", "text"),
    "MODEL_VS_BASELINE_TRUST": ("Model trust", "text"),
    "LAST_SCORED_HOUR": ("Last scored", "text"),
    "AUC": ("AUC", "score"),
    "AVG_PRECISION": ("Avg precision", "score"),
    "BASE_RATE": ("Base rate", "pct"),
    "TEST_ROWS": ("Test hours", "int"),
    "TOP_DECILE_PRECISION": ("Model precision", "pct"),
    "BASELINE_TOP_DECILE_PRECISION": ("Persistence precision", "pct"),
    "MODEL_ADVANTAGE_PTS": ("Advantage (pts)", "pts"),
    "BREAKDOWN_HOURS": ("Fault (h)", "hours"),
    "IDLE_HOURS": ("Waiting (h)", "hours"),
    "SLOW_RUNNING_HOURS": ("Slow (h)", "hours"),
    "RUN_HOURS": ("Run (h)", "hours"),
    "PLANNED_HOURS": ("Planned (h)", "hours"),
    "STOP_HOURS": ("Stop (h)", "hours"),
    "OBSERVED_LOSS_MINUTES": ("Loss (min)", "minutes"),
    "ACTUAL_OUTPUT_UNITS": ("Output (k)", "thousands"),
    "PACKAGES_OUT": ("Packages out (k)", "thousands"),
    "MARGIN_EXPOSURE_EUR": ("Exposure (€M)", "eur_m"),
    "PRODUCTION_EXPOSURE_EUR": ("Exposure (€M)", "eur_m"),
    "WORK_ORDER_COUNT": ("Work orders", "int"),
    "WORK_ORDERS": ("Work orders", "int"),
    "STOCK_RISK_COUNT": ("Stock-risk kits", "int"),
    "ACTION_RANK": ("#", "int"),
    "OWNER_FUNCTION": ("Owner", "text"),
    "PRIORITY": ("Priority", "text"),
    "RECOMMENDED_ACTION": ("Recommended action", "wide"),
    "EVIDENCE": ("Evidence", "wide"),
    "LABOUR_COST": ("Labour (€k)", "eur_k"),
    "PARTS_COST": ("Parts (€k)", "eur_k"),
    "MAINTENANCE_COST": ("Maintenance (€k)", "eur_k"),
    "BREAKDOWN_FORGONE_MARGIN": ("Fault margin (€k)", "eur_k"),
    "IDLE_FORGONE_MARGIN": ("Waiting margin (€k)", "eur_k"),
    "TOTAL_SCENARIO_EXPOSURE": ("Total (€k)", "eur_k"),
    "AVG_COST_PER_ORDER": ("Avg / order (€)", "eur"),
    "PCT_COST_FROM_IDLING": ("From waiting", "pct100"),
    "IDLE_INCIDENTS": ("Waiting events", "int"),
    "CUMULATIVE_PCT": ("Cumulative", "pct100"),
    "CAUSE_CODE": ("Cause", "text"),
    "ALARM_CODE": ("Alarm", "text"),
    "STOP_STATE": ("Stop state", "text"),
    "STOCK_STATE": ("Stock state", "text"),
    "ON_HAND_QTY": ("On hand", "int"),
    "REORDER_POINT": ("Reorder point", "int"),
    "STOCK_RISK": ("At risk", "text"),
    "WORK_ORDER_ID": ("Work order", "text"),
    "PRODUCTION_ORDER_ID": ("Production order", "text"),
    "MATERIAL_ID": ("Material", "text"),
    "SOURCE_EVENT_ID": ("Event", "text"),
    "TECH_NAME": ("Technician", "text"),
    "SPECIALITY": ("Speciality", "text"),
    "STATUS": ("Status", "text"),
    "ORDER_STATUS": ("Order status", "text"),
    "WORK_ORDER_STATUS": ("WO status", "text"),
    "REPORTED_AT": ("Reported", "text"),
    "COMPLETED_AT": ("Completed", "text"),
    "STOP_START": ("Stop start", "text"),
    "DESCRIPTION": ("Description", "wide"),
    "DATA_ORIGIN": ("Origin", "text"),
    "EVENT_DATA_ORIGIN": ("Event origin", "text"),
    "PRODUCTION_ORDER_ORIGIN": ("PO origin", "text"),
    "WORK_ORDER_ORIGIN": ("WO origin", "text"),
    "PART_ORIGIN": ("Part origin", "text"),
    "INVENTORY_ORIGIN": ("Inventory origin", "text"),
}

# Warehouse enums rendered as prose. Only these columns are relabelled, so
# identifiers and free text are never rewritten.
VALUE_LABELS = {
    "MODEL_OUTPERFORMS_PERSISTENCE": "Beats persistence",
    "MODEL_DOES_NOT_OUTPERFORM_PERSISTENCE": "No edge vs persistence",
    "IDLE_DOMINANT": "Waiting dominant",
    "BREAKDOWN_DOMINANT": "Fault dominant",
    "SUPPLY_CHAIN": "Supply chain",
    "DERIVED_FROM_OBSERVED": "Derived",
    "DERIVED_FROM_OBSERVED + SYNTHETIC_ERP": "Derived + synthetic",
    "SYNTHETIC_IT": "Synthetic IT",
    "SESSION_SCENARIO": "Session scenario",
}
RELABEL_COLUMNS = {
    "MODEL_VS_BASELINE_TRUST",
    "RISK_STATE",
    "RISK_BAND",
    "OWNER_FUNCTION",
    "STOCK_STATE",
    "STATUS",
    "ORDER_STATUS",
    "WORK_ORDER_STATUS",
    "LOSS_NATURE",
    "GRAIN",
    "STOP_STATE",
    "DATA_ORIGIN",
    "EVENT_DATA_ORIGIN",
    "PRODUCTION_ORDER_ORIGIN",
    "WORK_ORDER_ORIGIN",
    "PART_ORIGIN",
    "INVENTORY_ORIGIN",
}


def label_value(value: object) -> object:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return value
    text = str(value)
    if text in VALUE_LABELS:
        return VALUE_LABELS[text]
    if text.isupper():
        return text.replace("_", " ").capitalize()
    return text


def dataframe(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    overrides: dict[str, tuple[str, str]] | None = None,
    **kwargs,
) -> None:
    if df is None or df.empty:
        st.info("No rows are available for this view.")
        return
    wanted = [c for c in (columns or list(df.columns)) if c in df.columns]
    shown = df[wanted].copy()
    meta = dict(COLUMN_META)
    meta.update({k.upper(): v for k, v in (overrides or {}).items()})

    config: dict[str, object] = {}
    for column in wanted:
        key = str(column).upper()
        label, kind = meta.get(key, (key.replace("_", " ").capitalize(), "text"))
        if kind in KIND_SPEC:
            # Snowflake NUMBER can arrive as Decimal objects, so coerce first.
            numeric = pd.to_numeric(shown[column], errors="coerce")
            if numeric.notna().any():
                scale, fmt = KIND_SPEC[kind]
                shown[column] = numeric * scale if scale != 1.0 else numeric
                config[column] = st.column_config.NumberColumn(label, format=fmt)
                continue
        if key in RELABEL_COLUMNS:
            shown[column] = shown[column].map(label_value)
        config[column] = (
            st.column_config.TextColumn(label, width="large")
            if kind == "wide"
            else st.column_config.Column(label)
        )

    try:
        st.dataframe(
            shown,
            hide_index=True,
            use_container_width=True,
            column_config=config,
            **kwargs,
        )
    except Exception:
        # Older Streamlit runtimes reject column_config; the data still matters.
        LOGGER.warning("column_config unsupported; rendering plain table")
        st.dataframe(shown, hide_index=True, use_container_width=True, **kwargs)


# ---------------------------------------------------------------------------
# Command Center
# ---------------------------------------------------------------------------


def command_center() -> None:
    kpi = table("GOLD", "V_EXECUTIVE_KPI")
    fleet = safe_lines(table("GOLD", "V_EXECUTIVE_FLEET"))
    actions = safe_lines(table("GOLD", "V_EXECUTIVE_ACTION_QUEUE"))
    as_of = scalar(kpi, ("DATA_AS_OF", "AS_OF_TS", "LAST_REFRESHED_AT"))
    model_status = scalar(kpi, ("MODEL_STATUS", "RISK_MODEL_STATUS"), "Holdout validated")
    header("Command Center", "Leadership view · exceptions, loss, and accountable action", as_of, str(model_status))

    oee = scalar(kpi, ("SITE_WEIGHTED_OEE", "OEE", "WEIGHTED_OEE"))
    risk_lines = scalar(kpi, ("LINES_AT_RISK", "HIGH_RISK_LINES", "ACTIONABLE_LINES"))
    if risk_lines is None and not fleet.empty:
        at_risk = series(fleet, "RISK_BAND").astype(str).str.upper().isin(["ELEVATED", "HIGH"])
        trusted = series(fleet, "MODEL_VS_BASELINE_TRUST").astype(str).eq(
            "MODEL_OUTPERFORMS_PERSISTENCE"
        )
        risk_lines = int((at_risk & trusted).sum())
    financial_exposure = scalar(
        kpi,
        ("ESTIMATED_MARGIN_EXPOSURE_EUR", "FINANCIAL_EXPOSURE_EUR"),
    )
    open_actions = scalar(kpi, ("OPEN_ACTIONS", "ACTION_COUNT", "QUEUE_COUNT"))
    if open_actions is None:
        open_actions = len(actions)
    if kpi.empty:
        rollup = load(
            "OEE rollup",
            f"SELECT * FROM {DB}.GOLD.V_OEE_ROLLUP WHERE MACHINE_CODE IS NULL LIMIT 1",
        )
        oee = scalar(rollup, ("OEE",))

    a, b, c, d = st.columns(4)
    a.metric("Weighted OEE", percent(oee), help="Site A × P × Q from summed time and package totals.")
    b.metric(
        "Validated lines on watch",
        number(risk_lines),
        help="Lines whose latest blind-period hour is Elevated/High and whose line-level model beat persistence. This is an archived validation result, not live telemetry.",
    )
    c.metric(
        "Scenario margin exposure",
        number(financial_exposure, prefix="€"),
        help="Synthetic ERP estimate from observed production shortfall and an assumed contribution margin.",
    )
    d.metric("Open leadership actions", number(open_actions), help="Unresolved actions requiring an accountable owner.")

    section("Where the planned hours go")
    rollup = load(
        "OEE loss bridge",
        f"SELECT * FROM {DB}.GOLD.V_OEE_ROLLUP WHERE MACHINE_CODE IS NULL LIMIT 1",
    )
    if not rollup.empty:
        row = rollup.iloc[0]
        run = float(row.get("RUN_HOURS") or 0)
        slow = float(row.get("SLOW_RUNNING_HOURS") or 0)
        parts = [
            ("Productive", max(run - slow, 0.0), TEAL),
            ("Slow running", slow, SLATE),
            ("Waiting", float(row.get("IDLE_HOURS") or 0), AMBER),
            ("Fault", float(row.get("BREAKDOWN_HOURS") or 0), RED),
        ]
        total = sum(hours for _, hours, _ in parts) or 1.0
        fig = go.Figure()
        for name, hours, colour in parts:
            fig.add_bar(
                x=[hours],
                y=["Planned hours"],
                orientation="h",
                name=f"{name} · {hours / total:.0%}",
                marker_color=colour,
                text=f"{hours:,.0f} h",
                textposition="inside",
                insidetextanchor="middle",
                textfont=dict(size=11, color="#0a0e14"),
                hovertemplate=f"{esc(name)}<br>%{{x:,.0f}} h<extra></extra>",
            )
        fig.update_layout(barmode="stack")
        fig.update_yaxes(showticklabels=False)
        fig.update_xaxes(showticklabels=False)
        chart(style_fig(fig, height=132, legend=True))

    section("Fleet ranked by actionable risk")
    risk_col = col(
        fleet,
        "LAST_RISK_SCORE",
        "ACTIONABLE_RISK",
        "RISK_SCORE",
        "RISK_RANK",
        "PRIORITY_SCORE",
    )
    if risk_col:
        fleet = fleet.sort_values(risk_col, ascending=False).head(5)
    dataframe(
        fleet,
        [
            "MACHINE_CODE",
            "RISK_BAND",
            "LAST_RISK_SCORE",
            "MODEL_VS_BASELINE_TRUST",
            "OEE",
            "IDLE_HOURS",
            "BREAKDOWN_HOURS",
            "MARGIN_EXPOSURE_EUR",
        ],
    )

    section("Leadership action queue")
    priority = col(actions, "PRIORITY_RANK", "ACTION_RANK", "RISK_SCORE", "PRIORITY")
    if priority:
        descending = str(priority).upper() in {"RISK_SCORE", "ACTIONABLE_RISK", "PRIORITY_SCORE"}
        actions = actions.sort_values(priority, ascending=not descending).head(8)
    dataframe(
        actions,
        [
            "ACTION_RANK",
            "PRIORITY",
            "OWNER_FUNCTION",
            "MACHINE_CODE",
            "RISK_STATE",
            "PRODUCTION_EXPOSURE_EUR",
            "RECOMMENDED_ACTION",
        ],
    )
    origin_note(True, True, "Operations and OEE are observed/derived. Costs and workflow records are synthetic scenarios.")


# ---------------------------------------------------------------------------
# Fleet Risk
# ---------------------------------------------------------------------------


def fleet_risk() -> None:
    metrics = table("ML", "PLANT_B_MODEL_METRICS")
    fleet = metrics[series(metrics, "SCOPE").astype(str).str.upper() == "FLEET"] if not metrics.empty else metrics
    row = fleet.iloc[0] if not fleet.empty else pd.Series(dtype=object)
    header("Fleet Risk", "Next-hour stop exposure · chronological holdout")

    precision = row.get("TOP_DECILE_PRECISION")
    baseline = row.get("BASELINE_TOP_DECILE_PRECISION")
    lift = None
    if precision is not None and baseline not in (None, 0) and not pd.isna(baseline):
        lift = float(precision) / float(baseline)
    a, b, c, d = st.columns(4)
    a.metric("Model precision", percent(precision), help="Share of top-decile alerts followed by a heavy stop.")
    b.metric("Persistence precision", percent(baseline), help="Matched do-nothing rule: current downtime persists.")
    c.metric("Lift vs persistence", number(lift, 2, suffix="×"), help="Model precision divided by persistence precision; above 1 adds value.")
    d.metric("Holdout AUC", number(row.get("AUC"), 3), help="Ranking quality on unseen time; 0.5 is random and 1.0 is perfect.")

    per_line = metrics[series(metrics, "SCOPE").astype(str).isin(LINES)].copy() if not metrics.empty else metrics
    if not per_line.empty:
        per_line["MODEL_ADVANTAGE_PTS"] = (
            pd.to_numeric(per_line["TOP_DECILE_PRECISION"], errors="coerce")
            - pd.to_numeric(per_line["BASELINE_TOP_DECILE_PRECISION"], errors="coerce")
        ) * 100
        per_line = per_line.sort_values("MODEL_ADVANTAGE_PTS", ascending=False)
    section("Trust by line")
    dataframe(
        per_line,
        [
            "SCOPE",
            "TEST_ROWS",
            "BASE_RATE",
            "AUC",
            "AVG_PRECISION",
            "TOP_DECILE_PRECISION",
            "BASELINE_TOP_DECILE_PRECISION",
            "MODEL_ADVANTAGE_PTS",
        ],
    )

    risk = safe_lines(table("GOLD", "V_PLANT_B_RISK"))
    selected = st.selectbox("Selected line", LINES, key="risk_line")
    selected_risk = risk[series(risk, "MACHINE_CODE", "LINE_ID").astype(str) == selected].copy()
    ts = col(selected_risk, "HOUR_TS", "SCORE_TS", "EVENT_TS")
    if ts:
        selected_risk[ts] = pd.to_datetime(selected_risk[ts], errors="coerce")
        selected_risk = selected_risk.sort_values(ts).tail(72)

    left, right = st.columns([1.55, 1], gap="medium")
    with left:
        section("Selected-line 72-hour result")
        if not selected_risk.empty and ts:
            fig = go.Figure()
            risk_score = col(selected_risk, "RISK_SCORE", "ACTIONABLE_RISK")
            actual = col(
                selected_risk,
                "NEXT_HOUR_DOWNTIME",
                "ACTUAL_NEXT_HOUR_DOWNTIME_PCT",
                "CURRENT_DOWNTIME_PCT",
                "DOWNTIME_PCT",
            )
            output = col(selected_risk, "OUTPUT_PACKAGES", "PACKAGES_OUT", "CURRENT_OUTPUT")
            if risk_score:
                fig.add_scatter(x=selected_risk[ts], y=selected_risk[risk_score], name="Risk", line=dict(color=AMBER, width=2))
            if actual:
                values = pd.to_numeric(selected_risk[actual], errors="coerce")
                if values.max() > 1:
                    values = values / 100
                fig.add_scatter(x=selected_risk[ts], y=values, name="Downtime", line=dict(color=RED, width=1.4))
            if output:
                fig.add_bar(x=selected_risk[ts], y=selected_risk[output], name="Output", marker_color=BLUE, opacity=.35, yaxis="y2")
                fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False))
            fig.update_yaxes(tickformat=".0%")
            chart(style_fig(fig, height=300))
        else:
            st.info("No scored hours are available for this line.")
    with right:
        section("Actual vs predicted")
        st.caption(
            "This 72-hour slice uses the fleet-wide alert flag. It is diagnostic "
            "history, not the separately re-ranked per-line top-decile metric."
        )
        if not selected_risk.empty:
            predicted = pd.to_numeric(series(selected_risk, "IS_FLAGGED", default=0), errors="coerce").fillna(0)
            actual_stop = pd.to_numeric(series(selected_risk, "ACTUAL_HEAVY_STOP", default=0), errors="coerce").fillna(0)
            result = pd.DataFrame(
                {
                    "Result": ["True alert", "False alert", "Missed stop", "Correct quiet"],
                    "Hours": [
                        int(((predicted == 1) & (actual_stop == 1)).sum()),
                        int(((predicted == 1) & (actual_stop == 0)).sum()),
                        int(((predicted == 0) & (actual_stop == 1)).sum()),
                        int(((predicted == 0) & (actual_stop == 0)).sum()),
                    ],
                }
            )
            fig = px.bar(result, x="Hours", y="Result", orientation="h")
            # Good outcomes stay neutral; only misses and false alarms carry risk colour.
            fig.update_traces(
                marker_color=[TEAL, AMBER, RED, SLATE],
                hovertemplate="%{y}: %{x:,.0f} h<extra></extra>",
            )
            chart(style_fig(fig, height=180, legend=False))

        section("Feature drivers")
        importance = table("ML", "PLANT_B_FEATURE_IMPORTANCE")
        if not importance.empty:
            importance = importance.sort_values(col(importance, "IMPORTANCE") or importance.columns[-1]).tail(8)
            fig = px.bar(importance, x=col(importance, "IMPORTANCE"), y=col(importance, "FEATURE"), orientation="h")
            fig.update_traces(marker_color=BLUE)
            chart(style_fig(fig, height=220, legend=False))
    origin_note(True, False, "No condition sensors or remaining-useful-life claims are used.")


# ---------------------------------------------------------------------------
# OEE Drill-Down
# ---------------------------------------------------------------------------


def oee_drilldown() -> None:
    header("OEE Drill-Down", "Weighted operating effectiveness and attributable loss")
    rollup = table("GOLD", "V_OEE_ROLLUP")
    site = rollup[series(rollup, "MACHINE_CODE").isna()] if not rollup.empty else rollup
    line_rows = safe_lines(rollup)
    line_rows = line_rows[series(line_rows, "MACHINE_CODE").notna()] if not line_rows.empty else line_rows
    row = site.iloc[0] if not site.empty else pd.Series(dtype=object)
    a, b, c, d = st.columns(4)
    a.metric("Availability", percent(row.get("AVAILABILITY")), help="Run time divided by planned production time.")
    b.metric("Performance", percent(row.get("PERFORMANCE")), help="Output versus demonstrated line rate during run time.")
    c.metric("Quality", percent(row.get("QUALITY")), help="Packages out divided by packages in.")
    d.metric("Weighted OEE", percent(row.get("OEE")), help="A × P × Q recomputed from summed site totals, not averaged percentages.")

    left, right = st.columns([1.1, 1], gap="medium")
    with left:
        section("Loss stack")
        if not line_rows.empty:
            loss_names = {
                "BREAKDOWN_HOURS": "Fault",
                "IDLE_HOURS": "Waiting",
                "SLOW_RUNNING_HOURS": "Slow running",
            }
            loss_cols = [c for c in loss_names if c in line_rows.columns]
            melted = line_rows.melt(
                id_vars=["MACHINE_CODE"], value_vars=loss_cols, var_name="Loss", value_name="Hours"
            )
            melted["Loss"] = melted["Loss"].map(loss_names)
            fig = px.bar(
                melted,
                x="MACHINE_CODE",
                y="Hours",
                color="Loss",
                barmode="stack",
                category_orders={"Loss": ["Fault", "Waiting", "Slow running"]},
                color_discrete_map={"Fault": RED, "Waiting": AMBER, "Slow running": SLATE},
            )
            fig.update_traces(hovertemplate="%{x}<br>%{fullData.name}: %{y:,.0f} h<extra></extra>")
            chart(style_fig(fig, height=260))
    with right:
        section("Machine comparison")
        if not line_rows.empty:
            order = line_rows.sort_values("OEE", ascending=False)["MACHINE_CODE"].astype(str).tolist()
            comp = line_rows.melt(
                id_vars=["MACHINE_CODE"],
                value_vars=[c for c in ["AVAILABILITY", "PERFORMANCE", "QUALITY", "OEE"] if c in line_rows],
                var_name="Metric",
                value_name="Value",
            )
            comp["Metric"] = comp["Metric"].str.capitalize()
            fig = px.bar(
                comp,
                x="MACHINE_CODE",
                y="Value",
                color="Metric",
                barmode="group",
                category_orders={
                    "MACHINE_CODE": order,
                    "Metric": ["Availability", "Performance", "Quality", "Oee"],
                },
                # OEE is the outcome, so it is the only series that carries accent.
                color_discrete_map={
                    "Availability": "#4f7cac",
                    "Performance": "#6f93bc",
                    "Quality": "#8fa9c9",
                    "Oee": AMBER,
                },
            )
            fig.for_each_trace(lambda t: t.update(name="OEE") if t.name == "Oee" else None)
            fig.update_yaxes(tickformat=".0%", range=[0, 1])
            fig.update_traces(hovertemplate="%{x}<br>%{fullData.name}: %{y:.1%}<extra></extra>")
            chart(style_fig(fig, height=260))

    section("Weighted OEE trend · weekly")
    daily = safe_lines(table("GOLD", "V_OEE_DAILY"))
    date = col(daily, "OEE_DATE", "DATE") if not daily.empty else None
    if date:
        trend = daily.copy()
        # Snowflake DATE arrives as datetime.date objects. Passing those
        # straight to Plotly produces a categorical axis with one category per
        # day, which fails to draw; convert to real datetimes first.
        stamps = pd.to_datetime(trend[date], errors="coerce")
        trend = trend.assign(
            _WEEK=stamps - pd.to_timedelta(stamps.dt.dayofweek, unit="D")
        ).dropna(subset=["_WEEK"])
        components = ["PLANNED_HOURS", "RUN_HOURS", "PACKAGES_IN", "PACKAGES_OUT", "THEORETICAL_PACKAGES"]
        weighted = all(c in trend.columns for c in components)
        for component in components:
            if component in trend:
                trend[component] = pd.to_numeric(trend[component], errors="coerce")

        def weekly(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
            if weighted:
                agg = frame.groupby(keys, as_index=False)[components].sum(min_count=1)
                floors = agg[["PLANNED_HOURS", "THEORETICAL_PACKAGES", "PACKAGES_IN"]].replace(0, float("nan"))
                # Cumulative counters are sampled at interval boundaries, so an
                # output can land in a later bucket than its input. GOLD caps
                # each term at 1.0 for exactly this reason; match that rule.
                agg["VALUE"] = (
                    (agg["RUN_HOURS"] / floors["PLANNED_HOURS"]).clip(upper=1.0)
                    * (agg["PACKAGES_OUT"] / floors["THEORETICAL_PACKAGES"]).clip(upper=1.0)
                    * (agg["PACKAGES_OUT"] / floors["PACKAGES_IN"]).clip(upper=1.0)
                )
                return agg.dropna(subset=["VALUE"])
            # Fall back to an unweighted mean if the component columns move.
            agg = frame.groupby(keys, as_index=False)["OEE"].mean().rename(columns={"OEE": "VALUE"})
            return agg.dropna(subset=["VALUE"])

        fig = go.Figure()
        for index, machine in enumerate(sorted(trend["MACHINE_CODE"].dropna().astype(str).unique())):
            per_line = weekly(trend[trend["MACHINE_CODE"].astype(str) == machine], ["_WEEK"])
            if per_line.empty:
                continue
            fig.add_scatter(
                x=per_line["_WEEK"],
                y=per_line["VALUE"],
                name=machine,
                mode="lines",
                line=dict(color=LINE_RAMP[index % len(LINE_RAMP)], width=1),
                opacity=.7,
                hovertemplate=f"{esc(machine)}<br>%{{x|%d %b %Y}}: %{{y:.1%}}<extra></extra>",
            )
        site = weekly(trend, ["_WEEK"])
        if not site.empty:
            fig.add_scatter(
                x=site["_WEEK"],
                y=site["VALUE"],
                name="Site weighted",
                mode="lines",
                line=dict(color=AMBER, width=2.4),
                hovertemplate="Site<br>%{x|%d %b %Y}: %{y:.1%}<extra></extra>",
            )
        fig.update_yaxes(tickformat=".0%", range=[0, 1])
        chart(style_fig(fig, height=260))
        st.caption(
            "Weekly points recompute A × P × Q from summed hours and package "
            "counts, so short weeks cannot distort the site line. Each term is "
            "capped at 100%, matching the daily GOLD definition, because "
            "cumulative counters can record an output in a later bucket than "
            "its input."
        )

    section("Fault Pareto")
    pareto = table("GOLD", "V_DOWNTIME_PARETO")
    pareto = pareto[series(pareto, "LOSS_NATURE").astype(str).str.upper() == "FAULTED"] if not pareto.empty else pareto
    if not pareto.empty:
        pareto = pareto.sort_values("STOP_HOURS", ascending=False).head(12)
        fig = go.Figure()
        fig.add_bar(x=pareto["CAUSE_CODE"], y=pareto["STOP_HOURS"], name="Fault hours", marker_color=RED)
        if "CUMULATIVE_PCT" in pareto:
            fig.add_scatter(x=pareto["CAUSE_CODE"], y=pareto["CUMULATIVE_PCT"], name="Cumulative %", yaxis="y2", line=dict(color=AMBER))
            fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, ticksuffix="%"))
        chart(style_fig(fig, height=250))
    origin_note(True, False, "Ideal rate is each line’s demonstrated rate; fault codes are anonymised.")


# ---------------------------------------------------------------------------
# Work and Materials
# ---------------------------------------------------------------------------


def _scenario_work_orders() -> pd.DataFrame:
    return pd.DataFrame(st.session_state.get("scenario_work_orders", []))


def work_materials() -> None:
    header("Work & Materials", "Synthetic maintenance workflow and material exposure")
    st.markdown(
        '<div class="notice"><b>Simulation boundary.</b> Historical Snowflake facts are read-only. '
        'Planned work created here exists only in this browser session.</div>',
        unsafe_allow_html=True,
    )
    with st.expander("Create planned work order · simulation only"):
        with st.form("planned_wo"):
            c1, c2, c3 = st.columns(3)
            line = c1.selectbox("Line", LINES)
            priority = c2.selectbox(
                "Priority",
                ["P1", "P2", "P3", "P4"],
                index=1,
                help=(
                    "P1: immediate safety or production threat · "
                    "P2: urgent, plan next intervention · "
                    "P3: routine planned work · P4: monitor/backlog."
                ),
            )
            description = c3.text_input("Planned task", max_chars=120)
            submitted = st.form_submit_button("Create session scenario")
        if submitted:
            if not description.strip():
                st.warning("Enter a planned task.")
            else:
                rows = list(st.session_state.get("scenario_work_orders", []))
                sequence = int(st.session_state.get("scenario_work_order_seq", 0)) + 1
                st.session_state.scenario_work_order_seq = sequence
                new_row = {
                    "WORK_ORDER_ID": f"SIM-{sequence:03d}",
                    "MACHINE_CODE": line,
                    "PRIORITY": priority,
                    "STATUS": "PLANNED",
                    "DESCRIPTION": description.strip(),
                    "REPORTED_AT": datetime.now(timezone.utc),
                    "DATA_ORIGIN": "SESSION_SCENARIO",
                }
                # Session scenarios are a UI aid, not a durable work ledger.
                # Bound them so one browser session cannot grow indefinitely.
                st.session_state.scenario_work_orders = (rows + [new_row])[-25:]
                st.success("Scenario row created in session state; Snowflake was not changed.")

    work = load(
        "PIADE work orders",
        f"""SELECT WORK_ORDER_ID,MACHINE_CODE,CAUSE_CODE,REPORTED_AT,
                   COMPLETED_AT,PRIORITY,STATUS,TECH_NAME,SPECIALITY,
                   LABOUR_COST,PARTS_COST,LOST_PRODUCTION_COST,TOTAL_COST,
                   DATA_ORIGIN
            FROM {DB}.GOLD.WORK_ORDER
            WHERE PLANT_CODE='PLANT_B'
            ORDER BY REPORTED_AT DESC
            LIMIT 250""",
    )
    simulated = _scenario_work_orders()
    section("Work-order list")
    combined_work = pd.concat([simulated, work.head(250)], ignore_index=True, sort=False)
    status_order = ["PLANNED", "IN_PROGRESS", "ON_HOLD", "COMPLETED", "CANCELLED"]
    status_values = (
        combined_work["STATUS"].dropna().astype(str).str.upper().unique().tolist()
        if "STATUS" in combined_work
        else []
    )
    status_options = [s for s in status_order if s in status_values]
    status_options.extend(sorted(s for s in status_values if s not in status_order))
    status = st.multiselect(
        "Status filter",
        status_options,
        default=[],
        format_func=label_value,
        placeholder="All statuses",
        help="Session-created work is Planned. Published scenario history is Completed.",
    )
    if status:
        selected_statuses = {
            str(value).strip().upper().replace(" ", "_") for value in status
        }
        combined_work = combined_work[
            combined_work["STATUS"].astype(str).str.upper().isin(selected_statuses)
        ]
    planned_count = int(
        (combined_work.get("STATUS", pd.Series(dtype=str)).astype(str).str.upper() == "PLANNED").sum()
    )
    st.caption(
        f"{planned_count} session-planned · "
        f"{int((combined_work.get('STATUS', pd.Series(dtype=str)).astype(str).str.upper() == 'COMPLETED').sum())} "
        "completed historical scenario rows shown. Blank costs on planned rows mean not yet estimated."
    )
    dataframe(
        combined_work,
        [
            "WORK_ORDER_ID",
            "MACHINE_CODE",
            "PRIORITY",
            "STATUS",
            "CAUSE_CODE",
            "REPORTED_AT",
            "COMPLETED_AT",
            "TECH_NAME",
            "SPECIALITY",
            "LABOUR_COST",
            "PARTS_COST",
            "LOST_PRODUCTION_COST",
            "TOTAL_COST",
            "DESCRIPTION",
        ],
        # Order-grain money is small, so euros read better than thousands.
        overrides={
            "LABOUR_COST": ("Labour (€)", "eur2"),
            "PARTS_COST": ("Parts (€)", "eur2"),
            "LOST_PRODUCTION_COST": ("Lost output (€)", "eur2"),
            "TOTAL_COST": ("Total (€)", "eur2"),
        },
    )
    with st.expander("How to read the work-order table"):
        st.caption(
            "Planned rows are temporary browser-session scenarios and disappear when the "
            "session ends. Completed rows are deterministic synthetic maintenance records "
            "anchored to observed PIADE fault events. Blank technician, completion, and cost "
            "fields on a planned row mean those decisions have not been simulated—not that "
            "the values are zero. Cortex is reserved for questions that require synthesis; "
            "fixed status and column definitions are shown here without an AI call."
        )

    left, right = st.columns([1.1, 1], gap="medium")
    with left:
        section("Parts inventory and stock risk")
        inventory = table("GOLD", "INVENTORY_SNAPSHOT")
        materials = table("GOLD", "DIM_MATERIAL")
        material_id = col(inventory, "MATERIAL_ID", "MATERIAL_CODE")
        dim_id = col(materials, "MATERIAL_ID", "MATERIAL_CODE")
        if material_id and dim_id and material_id != dim_id:
            inventory = inventory.merge(materials, left_on=material_id, right_on=dim_id, how="left")
        elif material_id and dim_id:
            inventory = inventory.merge(materials, on=material_id, how="left")
        on_hand = col(inventory, "ON_HAND_QTY", "QUANTITY_ON_HAND", "STOCK_QTY")
        reorder = col(inventory, "REORDER_POINT", "MIN_STOCK_QTY", "SAFETY_STOCK_QTY")
        if on_hand and reorder:
            inventory["STOCK_RISK"] = pd.to_numeric(inventory[on_hand], errors="coerce") <= pd.to_numeric(inventory[reorder], errors="coerce")
            inventory = inventory.sort_values(["STOCK_RISK", on_hand], ascending=[False, True])
        dataframe(
            inventory,
            [
                "MATERIAL_ID",
                "STOCK_STATE",
                "ON_HAND_QTY",
                "REORDER_POINT",
                "LEAD_TIME_DAYS",
                "ANCHORED_WORK_ORDERS",
                "SNAPSHOT_DATE",
            ],
            overrides={
                "LEAD_TIME_DAYS": ("Lead time (d)", "int"),
                "ANCHORED_WORK_ORDERS": ("Anchored WOs", "int"),
                "SNAPSHOT_DATE": ("Snapshot", "text"),
            },
        )
        st.caption("Inventory is a site-level material position and is not attributed to a single line.")
    with right:
        section("Selected digital thread")
        thread_line = st.selectbox("Line", LINES, key="thread_line")
        thread = load(
            "Recent PIADE digital threads",
            f"""SELECT *
                FROM {DB}.GOLD.V_DIGITAL_THREAD
                WHERE MACHINE_CODE={sql_literal(thread_line)}
                ORDER BY STOP_START DESC
                LIMIT 500""",
        )
        thread_id = col(thread, "SOURCE_EVENT_ID")
        if thread_id and not thread.empty:
            selected_thread = st.selectbox("Thread", thread[thread_id].dropna().astype(str).unique())
            item = thread[thread[thread_id].astype(str) == selected_thread]
            dataframe(
                item,
                [
                    "STOP_START",
                    "STOP_STATE",
                    "ALARM_CODE",
                    "OBSERVED_LOSS_MINUTES",
                    "PRODUCTION_ORDER_ID",
                    "ORDER_STATUS",
                    "WORK_ORDER_ID",
                    "WORK_ORDER_STATUS",
                    "MATERIAL_ID",
                    "STOCK_STATE",
                    "EVENT_DATA_ORIGIN",
                    "PRODUCTION_ORDER_ORIGIN",
                    "WORK_ORDER_ORIGIN",
                    "PART_ORIGIN",
                    "INVENTORY_ORIGIN",
                ],
            )
        else:
            st.info("No linked OT → incident → work order → material → production-order thread is available.")
    origin_note(False, True, "Workflow, materials, and orders are synthetic IT records anchored to observed operations.")


# ---------------------------------------------------------------------------
# Financial Risk
# ---------------------------------------------------------------------------


def financial_risk() -> None:
    header("Financial Risk", "Scenario exposure · planning loss kept separate from maintenance cost")
    costs = safe_lines(table("GOLD", "V_PIADE_COST_BY_MACHINE"))
    if costs.empty:
        st.info("No cost scenario rows are available.")
        return
    maint = pd.to_numeric(series(costs, "MAINTENANCE_COST", default=0), errors="coerce").fillna(0)
    idle = pd.to_numeric(series(costs, "IDLE_FORGONE_MARGIN", default=0), errors="coerce").fillna(0)
    prod = pd.to_numeric(series(costs, "BREAKDOWN_FORGONE_MARGIN", default=0), errors="coerce").fillna(0)
    a, b, c, d = st.columns(4)
    a.metric("Planning / idle exposure", number(idle.sum(), 0, "€"), help="Synthetic forgone margin while available but waiting.")
    b.metric("Fault / maintenance cost", number(maint.sum(), 0, "€"), help="Synthetic labour, parts, and fault-linked production cost.")
    c.metric("Production at risk", number((idle + prod).sum(), 0, "€"), help="Synthetic margin exposure from waiting and fault events.")
    d.metric("Highest-exposure line", str(costs.iloc[(idle + maint).argmax()].get("MACHINE_CODE", "—")), help="Line with the largest combined scenario exposure.")

    machine = col(costs, "MACHINE_CODE", "LINE_ID")
    melted = pd.DataFrame(
        {
            "Line": list(costs[machine]) * 2,
            "Exposure": list(idle) + list(maint),
            "Owner": ["Planning / idle"] * len(costs) + ["Maintenance / fault"] * len(costs),
        }
    )
    fig = px.bar(melted, x="Line", y="Exposure", color="Owner", barmode="stack", color_discrete_map={"Planning / idle": AMBER, "Maintenance / fault": RED})
    fig.update_yaxes(tickprefix="€")
    chart(style_fig(fig, height=280))
    costs = costs.assign(TOTAL_SCENARIO_EXPOSURE=idle + maint).sort_values("TOTAL_SCENARIO_EXPOSURE", ascending=False)
    dataframe(
        costs,
        [
            "MACHINE_CODE",
            "TOTAL_SCENARIO_EXPOSURE",
            "IDLE_FORGONE_MARGIN",
            "MAINTENANCE_COST",
            "BREAKDOWN_FORGONE_MARGIN",
            "LABOUR_COST",
            "PARTS_COST",
            "PCT_COST_FROM_IDLING",
            "WORK_ORDERS",
            "IDLE_HOURS",
            "BREAKDOWN_HOURS",
            "AVG_COST_PER_ORDER",
        ],
    )
    with st.expander("Assumptions and limitations"):
        st.caption(
            "All currency values are synthetic scenarios. Labour rates, parts draws, and contribution "
            "margin are assumptions; observed stop duration and package activity are the operational basis. "
            "These figures do not represent booked spend or realised savings. The Command Center margin "
            "exposure is a production-order capacity scenario; this page instead separates event-level "
            "idle exposure from work-order maintenance cost, so the totals are intentionally different."
        )
    origin_note(False, True, "Use for prioritisation and sensitivity, not accounting.")


# ---------------------------------------------------------------------------
# Analyst
# ---------------------------------------------------------------------------


SUGGESTIONS = {
    "Which lines require action now?": ("ACTION", "RISK", "PRIORITY"),
    "What is driving site OEE loss?": ("OEE", "LOSS", "DOWNTIME"),
    "Where is inventory risk concentrated?": ("MATERIAL", "INVENTORY", "STOCK"),
}


def analyst_context() -> pd.DataFrame:
    return table("GOLD", "V_ANALYST_CONTEXT", limit=50)


def bounded_context(df: pd.DataFrame) -> str:
    if df.empty:
        return "No aggregate context rows are available."
    safe = df.copy().head(50)
    for c in safe.columns:
        safe[c] = safe[c].astype(str).str.slice(0, 300)
    return safe.to_json(orient="records", date_format="iso")[:12000]


def analyst() -> None:
    header("Analyst", "Bounded aggregate Q&A · no generated SQL")
    context = analyst_context()
    with st.expander("Verified suggested questions", expanded=True):
        choice = st.radio("Question", list(SUGGESTIONS), horizontal=True, label_visibility="collapsed")
        if st.button("Show verified evidence", use_container_width=False):
            terms = SUGGESTIONS[choice]
            mask = pd.Series(False, index=context.index)
            for candidate in ["TOPIC", "METRIC_NAME", "SUBJECT", "CATEGORY", "CONTEXT_KEY"]:
                if candidate in context:
                    mask |= context[candidate].astype(str).str.upper().str.contains("|".join(terms), regex=True)
            evidence = context[mask] if mask.any() else context.head(10)
            st.markdown(f"**{choice}**")
            dataframe(
                evidence,
                [
                    "GRAIN",
                    "MACHINE_CODE",
                    "RISK_BAND",
                    "LAST_RISK_SCORE",
                    "OEE",
                    "AVAILABILITY",
                    "PERFORMANCE",
                    "QUALITY",
                    "BREAKDOWN_HOURS",
                    "IDLE_HOURS",
                    "ACTUAL_OUTPUT_UNITS",
                    "MARGIN_EXPOSURE_EUR",
                    "WORK_ORDER_COUNT",
                    "STOCK_RISK_COUNT",
                ],
            )
            origin_note(True, True, "Rows shown directly from bounded GOLD.V_ANALYST_CONTEXT.")

    with st.expander("Ask a custom question"):
        prompt = st.text_area(
            "Question",
            max_chars=800,
            placeholder="Ask about aggregate OEE, risk, work, material, or financial exposure…",
        )
        run = st.button("Ask Cortex", disabled=not prompt.strip())
        if run:
            system_prompt = (
                "You are an operations analyst for PIADE Packaging Site. Answer only from the "
                "aggregate context below. Distinguish observed/derived inputs from synthetic "
                "scenario inputs. If evidence is absent, say so. Do not provide SQL, hidden "
                "reasoning, or unsupported causal claims. Keep the answer under 180 words.\n\n"
                f"AGGREGATE CONTEXT:\n{bounded_context(context)}\n\nQUESTION:\n{prompt}"
            )
            sql = (
                "SELECT SNOWFLAKE.CORTEX.COMPLETE("
                "'llama3.3-70b', "
                f"{sql_literal(system_prompt, 18000)}) AS RESPONSE"
            )
            answer = load("Cortex response", sql)
            if not answer.empty:
                # Cortex output is untrusted model text. Render it literally
                # so Markdown links/images/HTML cannot trigger callbacks.
                st.text(str(answer.iloc[0]["RESPONSE"]))
                st.caption("Cortex answer generated from bounded aggregate context; no SQL was generated or executed by the model.")
                with st.expander("Evidence and source trail"):
                    source_cols = [c for c in ["TOPIC", "METRIC_NAME", "METRIC_VALUE", "DATA_ORIGIN", "SOURCE_VIEW", "AS_OF_TS"] if c in context]
                    dataframe(context.head(50), source_cols or None)
    origin_note(True, True, "Custom answers may combine observed/derived aggregates and labelled synthetic scenarios.")


# ---------------------------------------------------------------------------
# Provenance and navigation
# ---------------------------------------------------------------------------


def provenance() -> None:
    with st.expander("Provenance / About"):
        st.caption(
            "PIADE Packaging Site uses five production lines (s_1…s_5). OEE and risk are derived "
            "from operational records. Workflow, material, production-order, and currency records "
            "are synthetic demonstrations unless explicitly marked observed."
        )
        st.markdown(
            "- Stop-risk output is a one-hour operational watch signal, not remaining useful life.\n"
            "- No vibration, temperature, RPM, or other condition-sensor claims are made.\n"
            "- Historical facts are read-only; session scenarios are never written to Snowflake."
        )


PAGES = {
    "Command Center": command_center,
    "Fleet Risk": fleet_risk,
    "OEE Drill-Down": oee_drilldown,
    "Work & Materials": work_materials,
    "Financial Risk": financial_risk,
    "Analyst": analyst,
}

with st.sidebar:
    st.markdown('<div class="eyebrow">OPERATIONS CONSOLE</div>', unsafe_allow_html=True)
    st.markdown("### PIADE Packaging Site")
    st.caption("Five-line packaging operation")
    st.toggle("Dark theme", key="dark_theme")
    st.markdown("---")
    choice = st.radio(
        "Navigation",
        list(PAGES),
        key="nav_page",
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption("s_1 · s_2 · s_3 · s_4 · s_5")
    st.caption("Observed operations + labelled synthetic workflow")
    sidebar_fleet = safe_lines(table("GOLD", "V_EXECUTIVE_FLEET"))
    if not sidebar_fleet.empty:
        bands = series(sidebar_fleet, "RISK_BAND").astype(str).str.upper()
        counts = [
            int(bands.isin(["LOW", "MODERATE"]).sum()),
            int((bands == "ELEVATED").sum()),
            int((bands == "HIGH").sum()),
        ]
        donut = go.Figure(
            go.Pie(
                labels=["Stable", "Watch", "Critical"],
                values=counts,
                hole=.72,
                marker_colors=[TEAL, AMBER, RED],
                textinfo="none",
                hovertemplate="%{label}: %{value}<extra></extra>",
            )
        )
        donut.update_layout(
            height=125,
            margin=dict(l=0, r=0, t=4, b=4),
            paper_bgcolor="rgba(0,0,0,0)",
            showlegend=True,
            legend=dict(orientation="h", y=-.12, x=0, font=dict(size=9)),
            annotations=[
                dict(
                    text=f"<b>{len(sidebar_fleet)}</b><br><span style='font-size:9px'>LINES</span>",
                    x=.5,
                    y=.5,
                    showarrow=False,
                )
            ],
        )
        st.plotly_chart(
            donut,
            use_container_width=True,
            config={"displayModeBar": False},
        )

inject_theme(st.session_state.dark_theme)

try:
    PAGES[choice]()
    provenance()
except Exception as exc:
    LOGGER.error("Page render failed (%s)", type(exc).__name__)
    st.error("This page could not be rendered. Retry or contact the app owner.")
