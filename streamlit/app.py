"""SnowCore PdM — two-plant command centre.

Built for Streamlit in Snowflake. Plant A and Plant B are intentionally never
aggregated together: they are unrelated public datasets with different
capabilities, not two sites in one measured enterprise.
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

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.4rem; padding-bottom: 2rem; max-width: 1500px}
      [data-testid="stSidebar"] {background: #071525}
      [data-testid="stSidebar"] * {color: #eef6ff}
      .hero {background: linear-gradient(120deg,#071525,#0b3150 65%,#007a87);
             color:white; padding:1.25rem 1.5rem; border-radius:16px; margin-bottom:1rem}
      .hero h1 {font-size:2rem; margin:0}
      .hero p {color:#cce6ed; margin:.35rem 0 0}
      .badge {display:inline-block; padding:.18rem .52rem; border-radius:999px;
              font-size:.72rem; font-weight:700; letter-spacing:.02em; margin-right:.25rem}
      .observed {background:#dff5e8;color:#155d37}
      .derived {background:#e0efff;color:#114b7a}
      .synthetic {background:#fff0cf;color:#78520b}
      .caveat {border-left:4px solid #e59f23; background:#fff9eb;
               padding:.7rem .9rem; border-radius:0 8px 8px 0; color:#49350b}
      .good {color:#13864d}.bad {color:#ba3131}
      div[data-testid="stMetric"] {background:white;border:1px solid #dce5ec;
              padding:.65rem .85rem;border-radius:12px}
      div[data-testid="stMetricLabel"] {font-weight:700}
      .small {font-size:.83rem;color:#546575}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def session():
    return get_active_session()


@st.cache_data(ttl=600, show_spinner=False)
def query(sql: str) -> pd.DataFrame:
    return session().sql(sql).to_pandas()


def sql_text(value: str) -> str:
    """Quote a value selected from the database before placing it in SQL."""
    return "'" + str(value).replace("'", "''") + "'"


def badge(origin: str) -> None:
    styles = {
        "OBSERVED": ("observed", "Observed"),
        "DERIVED_FROM_OBSERVED": ("derived", "Derived from observed"),
        "SYNTHETIC_IT": ("synthetic", "Synthetic scenario"),
    }
    css, label = styles.get(origin, ("derived", origin))
    st.markdown(f'<span class="badge {css}">{html.escape(label)}</span>', unsafe_allow_html=True)


def empty_message(label: str = "No rows are available for this selection.") -> None:
    st.info(label)


def percent(value) -> str:
    return "—" if pd.isna(value) else f"{float(value):.1%}"


def money(value) -> str:
    return "—" if pd.isna(value) else f"€{float(value):,.0f}"


@st.cache_data(ttl=600, show_spinner=False)
def load_briefings() -> pd.DataFrame:
    return query(
        f"""SELECT BRIEFING_KEY, NARRATIVE, INPUT_ORIGIN, MODEL_USED, GENERATED_AT
            FROM {DB}.GOLD.CORTEX_BRIEFING ORDER BY BRIEFING_KEY"""
    )


def cortex_brief(key: str) -> None:
    rows = load_briefings()
    row = rows[rows["BRIEFING_KEY"] == key]
    if row.empty:
        return
    item = row.iloc[0]
    st.markdown("#### Cortex briefing")
    badge(str(item["INPUT_ORIGIN"]))
    st.write(item["NARRATIVE"])
    st.caption(f"Generated in Snowflake Cortex with {item['MODEL_USED']}.")


def executive_page() -> None:
    st.subheader("Decision brief")
    oee = query(
        f"""SELECT * FROM {DB}.GOLD.V_OEE_ROLLUP
            WHERE PLANT_CODE='PLANT_B' AND MACHINE_CODE IS NULL"""
    )
    costs = query(
        f"""SELECT SUM(MAINTENANCE_COST) MAINTENANCE_COST,
                   SUM(IDLE_FORGONE_MARGIN) IDLE_COST,
                   SUM(BREAKDOWN_HOURS) BREAKDOWN_HOURS,
                   SUM(IDLE_HOURS) IDLE_HOURS
            FROM {DB}.GOLD.V_COST_BY_MACHINE WHERE PLANT_CODE='PLANT_B'"""
    )
    health = query(
        f"""SELECT COUNT(DISTINCT MACHINE_CODE) MACHINES,
                   ROUND(AVG(HEALTH_INDEX_AVG),1) AVG_HEALTH,
                   ROUND(MIN(HEALTH_INDEX_WORST),1) WORST_HEALTH
            FROM {DB}.GOLD.V_PLANT_A_HEALTH WHERE ANY_SCORED_PERIOD"""
    )
    model = query(
        f"""SELECT AUC, TOP_DECILE_PRECISION, BASELINE_TOP_DECILE_PRECISION
            FROM {DB}.ML.PLANT_B_MODEL_METRICS WHERE SCOPE='FLEET'"""
    )

    a, b, c, d = st.columns(4)
    if not oee.empty:
        row = oee.iloc[0]
        a.metric("Plant B weighted OEE", percent(row["OEE"]))
        b.metric("Idle vs breakdown hours", f"{row['IDLE_HOURS']:,.0f} / {row['BREAKDOWN_HOURS']:,.0f}")
    if not costs.empty:
        row = costs.iloc[0]
        ratio = float(row["IDLE_COST"]) / float(row["MAINTENANCE_COST"])
        c.metric("Synthetic idle exposure", money(row["IDLE_COST"]), f"{ratio:.1f}× maintenance")
    if not model.empty:
        row = model.iloc[0]
        d.metric(
            "Plant B top-decile precision",
            percent(row["TOP_DECILE_PRECISION"]),
            f"baseline {percent(row['BASELINE_TOP_DECILE_PRECISION'])}",
        )

    st.markdown(
        '<div class="caveat"><b>Do not combine the plants.</b> Plant A has '
        "condition sensors but no production counts; Plant B has production "
        "states and OEE but no analogue sensors. There is no enterprise OEE.</div>",
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.25, 1])
    with left:
        st.markdown("### Plant B — production loss")
        badge("DERIVED_FROM_OBSERVED")
        rollup = query(
            f"""SELECT MACHINE_CODE, OEE, AVAILABILITY, PERFORMANCE, QUALITY
                FROM {DB}.GOLD.V_OEE_ROLLUP
                WHERE PLANT_CODE='PLANT_B' AND MACHINE_CODE IS NOT NULL
                ORDER BY MACHINE_CODE"""
        )
        if not rollup.empty:
            chart = rollup.melt(
                id_vars="MACHINE_CODE",
                value_vars=["OEE", "AVAILABILITY", "PERFORMANCE", "QUALITY"],
                var_name="METRIC",
                value_name="VALUE",
            )
            fig = px.bar(
                chart, x="MACHINE_CODE", y="VALUE", color="METRIC", barmode="group",
                color_discrete_map={
                    "OEE": "#0b7482", "AVAILABILITY": "#4b8bbe",
                    "PERFORMANCE": "#e59f23", "QUALITY": "#6fbc8b",
                },
            )
            fig.update_yaxes(tickformat=".0%", range=[0, 1.05], title=None)
            fig.update_xaxes(title=None)
            fig.update_layout(height=340, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
        cortex_brief("PLANT_B_OEE")

    with right:
        st.markdown("### Plant A — condition drift")
        badge("DERIVED_FROM_OBSERVED")
        if not health.empty:
            h = health.iloc[0]
            x, y, z = st.columns(3)
            x.metric("Machines scored", int(h["MACHINES"]))
            y.metric("Mean health", f"{float(h['AVG_HEALTH']):.1f}/100")
            z.metric("Worst window", f"{float(h['WORST_HEALTH']):.1f}/100")
        st.markdown(
            '<div class="caveat">Health means distance from each machine’s own '
            "first-200-window baseline. It is <b>not a failure probability</b> "
            "and did not predict subsequent alarms in validation.</div>",
            unsafe_allow_html=True,
        )
        cortex_brief("PLANT_A_HEALTH")


def plant_a_page() -> None:
    st.subheader("Plant A · Condition monitoring")
    badge("DERIVED_FROM_OBSERVED")
    st.caption("CoMoPI — anonymised sensor channels. No OEE or lost-output claim is possible.")

    status = query(
        f"""WITH scored AS (
              SELECT MACHINE_CODE, COUNT_IF(IS_SCORED_PERIOD) SCORED_WINDOWS
              FROM {DB}.ML.PLANT_A_HEALTH GROUP BY MACHINE_CODE
            ),
            latest AS (
              SELECT MACHINE_CODE, HEALTH_DATE, HEALTH_INDEX_AVG,
                     HEALTH_INDEX_WORST, DOMINANT_CHANNEL
              FROM {DB}.GOLD.V_PLANT_A_HEALTH
              WHERE ANY_SCORED_PERIOD
              QUALIFY ROW_NUMBER() OVER (
                PARTITION BY MACHINE_CODE ORDER BY HEALTH_DATE DESC)=1
            )
            SELECT f.MACHINE_CODE, f.FIRST_SEEN, f.LAST_SEEN,
                   l.HEALTH_DATE, l.HEALTH_INDEX_AVG, l.HEALTH_INDEX_WORST,
                   l.DOMINANT_CHANNEL, COALESCE(s.SCORED_WINDOWS,0) SCORED_WINDOWS,
                   IFF(COALESCE(s.SCORED_WINDOWS,0) < 30,
                       'NOT ASSESSED', 'SCORED') STATUS
            FROM {DB}.GOLD.V_FLEET f
            LEFT JOIN latest l USING (MACHINE_CODE)
            LEFT JOIN scored s USING (MACHINE_CODE)
            WHERE f.PLANT_CODE='PLANT_A' ORDER BY f.MACHINE_CODE"""
    )
    if status.empty:
        empty_message()
        return

    assessed = status[status["STATUS"] == "SCORED"]
    not_assessed = status[status["STATUS"] != "SCORED"]["MACHINE_CODE"].tolist()
    x, y, z = st.columns(3)
    x.metric("Machines in source", len(status))
    y.metric("Machines with scored periods", len(assessed))
    z.metric("Not assessed", len(not_assessed))
    if not_assessed:
        st.warning(
            "Not assessed: " + ", ".join(not_assessed)
            + ". These machines have fewer than 30 post-baseline windows; "
            "absence is not health."
        )

    display = status.copy()
    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        column_config={
            "HEALTH_INDEX_AVG": st.column_config.ProgressColumn(
                "Latest average health", min_value=0, max_value=100, format="%.1f"
            ),
            "HEALTH_INDEX_WORST": st.column_config.NumberColumn("Worst window", format="%.1f"),
        },
    )

    machine = st.selectbox("Machine", assessed["MACHINE_CODE"].tolist())
    daily = query(
        f"""SELECT HEALTH_DATE, HEALTH_INDEX_AVG, HEALTH_INDEX_WORST,
                   CHANNEL_EXCURSIONS, DOMINANT_CHANNEL
            FROM {DB}.GOLD.V_PLANT_A_HEALTH
            WHERE MACHINE_CODE={sql_text(machine)} AND ANY_SCORED_PERIOD
            ORDER BY HEALTH_DATE"""
    )
    drift = query(
        f"""SELECT DRIFT_MONTH, CHANNEL, MEAN_SIGNED_Z, MEDIAN_SHIFT, IS_DRIFTED
            FROM {DB}.ML.PLANT_A_CHANNEL_DRIFT
            WHERE MACHINE_CODE={sql_text(machine)} ORDER BY DRIFT_MONTH, CHANNEL"""
    )
    left, right = st.columns([1.4, 1])
    with left:
        st.markdown("#### Health history")
        if not daily.empty:
            fig = go.Figure()
            fig.add_scatter(
                x=daily["HEALTH_DATE"], y=daily["HEALTH_INDEX_AVG"],
                name="Daily average", line=dict(color="#087f8c", width=2),
            )
            fig.add_scatter(
                x=daily["HEALTH_DATE"], y=daily["HEALTH_INDEX_WORST"],
                name="Worst window", line=dict(color="#d97821", width=1),
            )
            fig.update_yaxes(range=[0, 100], title="Health index")
            fig.update_layout(height=390, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
    with right:
        st.markdown("#### Channel drift")
        if not drift.empty:
            drifted = drift[drift["IS_DRIFTED"] == True]  # noqa: E712
            if drifted.empty:
                st.success("No sustained channel drift at the monthly threshold.")
            else:
                strongest = (
                    drifted.assign(ABS_Z=drifted["MEAN_SIGNED_Z"].abs())
                    .sort_values("ABS_Z")
                    .drop_duplicates("CHANNEL", keep="last")
                    .sort_values("MEAN_SIGNED_Z")
                )
                fig = px.bar(
                    strongest,
                    x="MEAN_SIGNED_Z", y="CHANNEL", orientation="h",
                    color="MEAN_SIGNED_Z", color_continuous_scale="RdBu_r",
                )
                fig.update_layout(height=390, margin=dict(l=10, r=10, t=20, b=10))
                st.plotly_chart(fig, use_container_width=True)
    st.markdown(
        '<div class="caveat"><b>Validation limit:</b> worst-health windows had '
        "a 21.2% subsequent alarm rate versus 17.7% at best health. This index "
        "describes drift; it does not justify intervention by itself.</div>",
        unsafe_allow_html=True,
    )


def plant_b_page() -> None:
    st.subheader("Plant B · OEE and production loss")
    badge("DERIVED_FROM_OBSERVED")
    st.caption("PIADE — OEE is recomputed from summed seconds and package counts, never averaged from ratios.")

    machines = query(
        f"""SELECT * FROM {DB}.GOLD.V_OEE_ROLLUP
            WHERE PLANT_CODE='PLANT_B' AND MACHINE_CODE IS NOT NULL
            ORDER BY MACHINE_CODE"""
    )
    fleet = query(
        f"""SELECT * FROM {DB}.GOLD.V_OEE_ROLLUP
            WHERE PLANT_CODE='PLANT_B' AND MACHINE_CODE IS NULL"""
    )
    if fleet.empty:
        empty_message()
        return
    row = fleet.iloc[0]
    cols = st.columns(6)
    values = [
        ("Weighted OEE", percent(row["OEE"])),
        ("Availability", percent(row["AVAILABILITY"])),
        ("Performance", percent(row["PERFORMANCE"])),
        ("Quality", percent(row["QUALITY"])),
        ("Breakdown hours", f"{row['BREAKDOWN_HOURS']:,.0f}"),
        ("Idle hours", f"{row['IDLE_HOURS']:,.0f}"),
    ]
    for col, (label, value) in zip(cols, values):
        col.metric(label, value)

    tab1, tab2, tab3 = st.tabs(["OEE trend", "Loss Pareto", "Cost attribution"])
    with tab1:
        selected = st.multiselect(
            "Machines", machines["MACHINE_CODE"].tolist(),
            default=machines["MACHINE_CODE"].tolist(),
        )
        if selected:
            values_sql = ",".join(sql_text(x) for x in selected)
            daily = query(
                f"""SELECT OEE_DATE, MACHINE_CODE, OEE, AVAILABILITY,
                           PERFORMANCE, QUALITY, BIGGEST_LOSS
                    FROM {DB}.GOLD.V_OEE_DAILY
                    WHERE MACHINE_CODE IN ({values_sql}) ORDER BY OEE_DATE"""
            )
            fig = px.line(
                daily, x="OEE_DATE", y="OEE", color="MACHINE_CODE",
                labels={"OEE_DATE": "", "OEE": "Daily OEE"},
            )
            fig.update_yaxes(tickformat=".0%", range=[0, 1])
            fig.update_layout(height=440, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            machines[["MACHINE_CODE", "OEE", "AVAILABILITY", "PERFORMANCE", "QUALITY"]],
            hide_index=True, use_container_width=True,
            column_config={
                c: st.column_config.NumberColumn(c.title(), format="%.3f")
                for c in ["OEE", "AVAILABILITY", "PERFORMANCE", "QUALITY"]
            },
        )
    with tab2:
        pareto = query(
            f"""SELECT CAUSE_CODE, LOSS_NATURE, OWNING_FUNCTION, STOP_PATTERN,
                       STOP_COUNT, STOP_HOURS, MEDIAN_STOP_MIN,
                       PCT_OF_STOP_TIME, CUMULATIVE_PCT
                FROM {DB}.GOLD.V_DOWNTIME_PARETO
                WHERE PLANT_CODE='PLANT_B' ORDER BY STOP_HOURS DESC"""
        )
        top = pareto.head(15)
        fig = go.Figure()
        fig.add_bar(x=top["CAUSE_CODE"], y=top["STOP_HOURS"], name="Stop hours", marker_color="#167c80")
        fig.add_scatter(
            x=top["CAUSE_CODE"], y=top["CUMULATIVE_PCT"], name="Cumulative %",
            yaxis="y2", line=dict(color="#e59f23", width=3),
        )
        fig.update_layout(
            height=430, yaxis_title="Hours",
            yaxis2=dict(title="Cumulative %", overlaying="y", side="right", range=[0, 105]),
            margin=dict(l=10, r=10, t=20, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.info(
            "IDLE_NO_ALARM is waiting time, not an unexplained failure. "
            "Every downtime interval has an alarm; every no-alarm interval is idle."
        )
        st.dataframe(top, hide_index=True, use_container_width=True)
    with tab3:
        costs = query(
            f"""SELECT * FROM {DB}.GOLD.V_COST_BY_MACHINE
                WHERE PLANT_CODE='PLANT_B' ORDER BY MACHINE_CODE"""
        )
        badge("SYNTHETIC_IT")
        st.warning(
            "All euros are scenario values. Labour rates, parts draws and "
            "contribution margin are assumptions; only event durations are observed."
        )
        chart = costs.melt(
            id_vars="MACHINE_CODE",
            value_vars=["MAINTENANCE_COST", "IDLE_FORGONE_MARGIN"],
            var_name="COST_TYPE", value_name="EUR",
        )
        fig = px.bar(
            chart, x="MACHINE_CODE", y="EUR", color="COST_TYPE", barmode="stack",
            color_discrete_map={
                "MAINTENANCE_COST": "#2a788e",
                "IDLE_FORGONE_MARGIN": "#e59f23",
            },
        )
        fig.update_layout(height=390, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            costs[[
                "MACHINE_CODE", "WORK_ORDERS", "BREAKDOWN_HOURS",
                "MAINTENANCE_COST", "IDLE_INCIDENTS", "IDLE_HOURS",
                "IDLE_FORGONE_MARGIN", "PCT_COST_FROM_IDLING",
            ]],
            hide_index=True, use_container_width=True,
        )
        cortex_brief("PLANT_B_COST")


def risk_page() -> None:
    st.subheader("Plant B · Next-hour heavy-stop risk")
    badge("DERIVED_FROM_OBSERVED")
    st.caption("Target: next hour loses more than 10% to unplanned downtime. Chronological holdout begins 2021-08-01.")

    metrics = query(
        f"""SELECT SCOPE, TEST_ROWS, AUC, AVG_PRECISION,
                   BASE_RATE, TOP_DECILE_PRECISION, TOP_DECILE_RECALL,
                   BASELINE_TOP_DECILE_PRECISION,
                   ROUND(BASE_RATE * 100, 1)                     AS BASE_RATE_PCT,
                   ROUND(TOP_DECILE_PRECISION * 100, 1)          AS PRECISION_PCT,
                   ROUND(TOP_DECILE_RECALL * 100, 1)             AS RECALL_PCT,
                   ROUND(BASELINE_TOP_DECILE_PRECISION * 100, 1) AS BASELINE_PCT
            FROM {DB}.ML.PLANT_B_MODEL_METRICS
            ORDER BY IFF(SCOPE='FLEET',0,1), SCOPE"""
    )
    fleet = metrics[metrics["SCOPE"] == "FLEET"].iloc[0]
    a, b, c, d = st.columns(4)
    a.metric("AUC", f"{float(fleet['AUC']):.3f}")
    b.metric("Top-decile precision", percent(fleet["TOP_DECILE_PRECISION"]))
    c.metric("Matched baseline", percent(fleet["BASELINE_TOP_DECILE_PRECISION"]))
    d.metric("Base rate", percent(fleet["BASE_RATE"]))
    st.markdown(
        '<div class="caveat">This is a modest, persistence-heavy ranking model. '
        "The honest comparison is 67.6% precision against the matched 55.7% "
        "do-nothing rule—not against the 40.3% base rate.</div>",
        unsafe_allow_html=True,
    )

    per_machine = metrics[metrics["SCOPE"] != "FLEET"].copy()
    per_machine["MODEL_BEATS_BASELINE"] = (
        per_machine["TOP_DECILE_PRECISION"] > per_machine["BASELINE_TOP_DECILE_PRECISION"]
    )
    st.markdown("#### Holdout performance by machine")
    st.dataframe(
        per_machine[[
            "SCOPE", "TEST_ROWS", "AUC", "BASE_RATE_PCT", "PRECISION_PCT",
            "BASELINE_PCT", "RECALL_PCT", "MODEL_BEATS_BASELINE",
        ]],
        hide_index=True,
        use_container_width=True,
        column_config={
            "SCOPE": "Machine",
            "TEST_ROWS": "Holdout hours",
            "AUC": st.column_config.NumberColumn("AUC", format="%.3f"),
            "BASE_RATE_PCT": st.column_config.NumberColumn("Base rate %", format="%.1f"),
            "PRECISION_PCT": st.column_config.NumberColumn("Model precision %", format="%.1f"),
            "BASELINE_PCT": st.column_config.NumberColumn("Baseline precision %", format="%.1f"),
            "RECALL_PCT": st.column_config.NumberColumn("Recall %", format="%.1f"),
            "MODEL_BEATS_BASELINE": "Beats baseline",
        },
    )
    losers = per_machine[~per_machine["MODEL_BEATS_BASELINE"]]["SCOPE"].tolist()
    if losers:
        st.warning(
            "Do not use the model as an upgrade on "
            + ", ".join(losers)
            + ": its matched baseline performs better on the holdout."
        )

    left, right = st.columns([1.3, 1])
    with left:
        machine = st.selectbox("Inspect machine", per_machine["SCOPE"].tolist())
        scores = query(
            f"""SELECT HOUR_TS, RISK_SCORE, RISK_BAND, IS_FLAGGED,
                       ACTUAL_HEAVY_STOP, ACTUAL_NEXT_HOUR_DOWNTIME_PCT
                FROM {DB}.GOLD.V_PLANT_B_RISK
                WHERE MACHINE_CODE={sql_text(machine)}
                ORDER BY HOUR_TS DESC LIMIT 240"""
        ).sort_values("HOUR_TS")
        fig = px.line(scores, x="HOUR_TS", y="RISK_SCORE", color_discrete_sequence=["#087f8c"])
        flagged = scores[scores["IS_FLAGGED"] == 1]
        fig.add_scatter(
            x=flagged["HOUR_TS"], y=flagged["RISK_SCORE"], mode="markers",
            name="Flagged top decile", marker=dict(color="#df8d19", size=8),
        )
        fig.update_yaxes(tickformat=".0%", range=[0, 1], title="Risk score")
        fig.update_layout(height=390, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        importance = query(
            f"""SELECT RANK, FEATURE, IMPORTANCE
                FROM {DB}.ML.PLANT_B_FEATURE_IMPORTANCE ORDER BY RANK LIMIT 12"""
        ).sort_values("IMPORTANCE")
        fig = px.bar(
            importance, x="IMPORTANCE", y="FEATURE", orientation="h",
            color_discrete_sequence=["#2a788e"],
        )
        fig.update_layout(height=390, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
    cortex_brief("PLANT_B_MODEL")


def trust_page() -> None:
    st.subheader("Data trust & assumptions")
    st.markdown(
        "Every displayed number carries one of three origins. Synthetic does "
        "not mean observed, and derived does not mean vendor-certified."
    )
    provenance = query(
        f"""SELECT PLANT_CODE, SUBJECT, DATA_ORIGIN, SOURCE, NOTE
            FROM {DB}.GOLD.V_PROVENANCE ORDER BY PLANT_CODE, SUBJECT"""
    )
    st.dataframe(provenance, hide_index=True, use_container_width=True)

    st.markdown("#### Synthetic IT assumptions")
    assumptions = query(
        f"""SELECT PLANT_SCOPE, NAME, VALUE, UNIT, IS_MEASURED, BASIS
            FROM {DB}.GOLD.IT_ASSUMPTION ORDER BY PLANT_SCOPE, NAME"""
    )
    st.dataframe(
        assumptions,
        hide_index=True,
        use_container_width=True,
        column_config={
            "PLANT_SCOPE": "Applies to",
            "IS_MEASURED": st.column_config.CheckboxColumn("Measured, not chosen"),
            "BASIS": "Why this value",
        },
    )
    st.markdown(
        '<div class="caveat"><b>What this app does not establish:</b> causal '
        "failure mechanisms, remaining useful life, Plant A production loss, "
        "vendor-rated ideal speed, or realised financial savings.</div>",
        unsafe_allow_html=True,
    )


st.sidebar.markdown("## ❄️ SnowCore")
st.sidebar.caption("Predictive Maintenance & OEE Command Center")
page = st.sidebar.radio(
    "Navigate",
    [
        "Executive brief",
        "Plant A · Health drift",
        "Plant B · OEE & loss",
        "Plant B · Stop risk",
        "Data trust",
    ],
    label_visibility="collapsed",
)
st.sidebar.divider()
st.sidebar.markdown("**Plant A · CoMoPI**  \nCondition sensors, no OEE")
st.sidebar.markdown("**Plant B · PIADE**  \nOEE, stops and modest risk")
st.sidebar.caption("UTC · SNOWCORE_REAL · No cross-plant aggregation")

st.markdown(
    """
    <div class="hero">
      <h1>SnowCore Maintenance & OEE Command Center</h1>
      <p>Real manufacturing data, explicit limitations, and Snowflake-native intelligence.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    if page == "Executive brief":
        executive_page()
    elif page == "Plant A · Health drift":
        plant_a_page()
    elif page == "Plant B · OEE & loss":
        plant_b_page()
    elif page == "Plant B · Stop risk":
        risk_page()
    else:
        trust_page()
except Exception as exc:
    st.error("The dashboard could not load this page.")
    st.exception(exc)
