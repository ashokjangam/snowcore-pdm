# ==================================================================================================
# VIEW SPECIFICATION: Executive Summary
# ==================================================================================================
#
# PURPOSE:
#   - Provide a high-level, at-a-glance overview of the entire manufacturing operation's health.
#   - This view is targeted at executives like the COO (Valerie Vance) who need quick,
#     aggregated insights without technical details.
#   - Enhanced to show time-series trends of OEE at enterprise and plant levels.
#
# DATA SOURCES:
#   - Primary: `SNOWCORE_INDUSTRIES.GOLD.AGG_ASSET_HOURLY_HEALTH`
#     - This pre-aggregated table is used for high-performance loading of the most critical KPIs:
#       - LATEST_HEALTH_SCORE
#       - AVG_FAILURE_PROBABILITY (used to calculate Production at Risk)
#   - Secondary: `SNOWCORE_INDUSTRIES.SILVER` Layer
#     - `FCT_PRODUCTION_LOG`: Used to calculate the overall OEE and time-series trends.
#     - `FCT_MAINTENANCE_LOG` & `DIM_WORK_ORDER_TYPE`: Used to calculate the Maintenance Cost Ratio.
#     - `DIM_ASSET`, `DIM_PLANT`, `DIM_LINE`, `DIM_PROCESS`: Used for hierarchy and impact calculations.
#
# ==================================================================================================

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from utils.data_loader import run_query, run_queries_sequential
from utils.calculations import calculate_oee

def show_page():
    """Executive Summary view - Top-level KPIs and strategic insights"""
    
    st.header("🏢 Executive Summary")
    
    # --- Time Period Configuration ---
    # Default to last 30 days for executive view
    days_back = 30
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days_back)
    
    # --- SQL QUERIES ---
    
    # 1. Enterprise-level daily OEE time-series (last 30 days)
    enterprise_timeseries_query = f"""
        WITH daily_production AS (
            SELECT
                PL.PRODUCTION_DATE,
                SUM(PL.PLANNED_RUNTIME_HOURS) AS PLANNED_RUNTIME_HOURS,
                SUM(PL.ACTUAL_RUNTIME_HOURS) AS ACTUAL_RUNTIME_HOURS,
                SUM(PL.UNITS_PRODUCED) AS UNITS_PRODUCED,
                SUM(PL.UNITS_SCRAPPED) AS UNITS_SCRAPPED
            FROM SNOWCORE_INDUSTRIES.SILVER.FCT_PRODUCTION_LOG PL
            WHERE PL.PRODUCTION_DATE >= DATEADD(DAY, -{days_back}, CURRENT_DATE())
            GROUP BY PL.PRODUCTION_DATE
            ORDER BY PL.PRODUCTION_DATE
        )
        SELECT
            PRODUCTION_DATE,
            PLANNED_RUNTIME_HOURS,
            ACTUAL_RUNTIME_HOURS,
            UNITS_PRODUCED,
            UNITS_SCRAPPED,
            CASE WHEN PLANNED_RUNTIME_HOURS > 0 
                THEN ACTUAL_RUNTIME_HOURS / PLANNED_RUNTIME_HOURS 
                ELSE 0 END AS AVAILABILITY,
            0.95 AS PERFORMANCE,
            CASE WHEN UNITS_PRODUCED > 0 
                THEN (UNITS_PRODUCED - UNITS_SCRAPPED) / UNITS_PRODUCED 
                ELSE 0 END AS QUALITY,
            CASE WHEN PLANNED_RUNTIME_HOURS > 0 AND UNITS_PRODUCED > 0
                THEN (ACTUAL_RUNTIME_HOURS / PLANNED_RUNTIME_HOURS) * 0.95 * 
                     ((UNITS_PRODUCED - UNITS_SCRAPPED) / UNITS_PRODUCED)
                ELSE 0 END AS OEE
        FROM daily_production;
    """
    
    # 2. Plant-level daily OEE time-series (last 30 days)
    plant_timeseries_query = f"""
        WITH plant_daily_production AS (
            SELECT
                P.PLANT_NAME,
                PL.PRODUCTION_DATE,
                SUM(PL.PLANNED_RUNTIME_HOURS) AS PLANNED_RUNTIME_HOURS,
                SUM(PL.ACTUAL_RUNTIME_HOURS) AS ACTUAL_RUNTIME_HOURS,
                SUM(PL.UNITS_PRODUCED) AS UNITS_PRODUCED,
                SUM(PL.UNITS_SCRAPPED) AS UNITS_SCRAPPED
            FROM SNOWCORE_INDUSTRIES.SILVER.FCT_PRODUCTION_LOG PL
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET A ON PL.ASSET_ID = A.ASSET_ID AND A.IS_CURRENT = TRUE
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_PROCESS PR ON PR.PROCESS_ID = A.PROCESS_ID
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_LINE L ON PR.LINE_ID = L.LINE_ID
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_PLANT P ON L.PLANT_ID = P.PLANT_ID
            WHERE PL.PRODUCTION_DATE >= DATEADD(DAY, -{days_back}, CURRENT_DATE())
            GROUP BY P.PLANT_NAME, PL.PRODUCTION_DATE
        )
        SELECT
            PLANT_NAME,
            PRODUCTION_DATE,
            PLANNED_RUNTIME_HOURS,
            ACTUAL_RUNTIME_HOURS,
            UNITS_PRODUCED,
            UNITS_SCRAPPED,
            CASE WHEN PLANNED_RUNTIME_HOURS > 0 
                THEN ACTUAL_RUNTIME_HOURS / PLANNED_RUNTIME_HOURS 
                ELSE 0 END AS AVAILABILITY,
            0.95 AS PERFORMANCE,
            CASE WHEN UNITS_PRODUCED > 0 
                THEN (UNITS_PRODUCED - UNITS_SCRAPPED) / UNITS_PRODUCED 
                ELSE 0 END AS QUALITY,
            CASE WHEN PLANNED_RUNTIME_HOURS > 0 AND UNITS_PRODUCED > 0
                THEN (ACTUAL_RUNTIME_HOURS / PLANNED_RUNTIME_HOURS) * 0.95 * 
                     ((UNITS_PRODUCED - UNITS_SCRAPPED) / UNITS_PRODUCED)
                ELSE 0 END AS OEE
        FROM plant_daily_production
        ORDER BY PLANT_NAME, PRODUCTION_DATE;
    """
    
    # 3. Current plant performance summary
    plant_current_query = """
        WITH latest_production AS (
            SELECT
                P.PLANT_NAME,
                SUM(PL.PLANNED_RUNTIME_HOURS) AS PLANNED_RUNTIME_HOURS,
                SUM(PL.ACTUAL_RUNTIME_HOURS) AS ACTUAL_RUNTIME_HOURS,
                SUM(PL.UNITS_PRODUCED) AS UNITS_PRODUCED,
                SUM(PL.UNITS_SCRAPPED) AS UNITS_SCRAPPED
            FROM SNOWCORE_INDUSTRIES.SILVER.FCT_PRODUCTION_LOG PL
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET A ON PL.ASSET_ID = A.ASSET_ID AND A.IS_CURRENT = TRUE
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_PROCESS PR ON PR.PROCESS_ID = A.PROCESS_ID
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_LINE L ON PR.LINE_ID = L.LINE_ID
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_PLANT P ON L.PLANT_ID = P.PLANT_ID
            WHERE PL.PRODUCTION_DATE >= DATEADD(DAY, -7, CURRENT_DATE())
            GROUP BY P.PLANT_NAME
        )
        SELECT
            PLANT_NAME,
            PLANNED_RUNTIME_HOURS,
            ACTUAL_RUNTIME_HOURS,
            UNITS_PRODUCED,
            UNITS_SCRAPPED
        FROM latest_production
        ORDER BY PLANT_NAME;
    """
    
    # 4. Asset health and risk data
    gold_data_query = """
        SELECT ASSET_ID, LATEST_HEALTH_SCORE, AVG_FAILURE_PROBABILITY
        FROM SNOWCORE_INDUSTRIES.GOLD.AGG_ASSET_HOURLY_HEALTH
        QUALIFY ROW_NUMBER() OVER (PARTITION BY ASSET_ID ORDER BY HOUR_TIMESTAMP DESC) = 1;
    """
    
    # 5. Asset health time-series (for sparkline in metric card)
    health_timeseries_query = f"""
        WITH daily_health AS (
            SELECT
                DATE_TRUNC('DAY', HOUR_TIMESTAMP) AS HEALTH_DATE,
                AVG(LATEST_HEALTH_SCORE) AS AVG_HEALTH_SCORE
            FROM SNOWCORE_INDUSTRIES.GOLD.AGG_ASSET_HOURLY_HEALTH
            WHERE HOUR_TIMESTAMP >= DATEADD(DAY, -{days_back}, CURRENT_TIMESTAMP())
            GROUP BY DATE_TRUNC('DAY', HOUR_TIMESTAMP)
            ORDER BY HEALTH_DATE
        )
        SELECT 
            HEALTH_DATE::DATE AS HEALTH_DATE,
            AVG_HEALTH_SCORE
        FROM daily_health;
    """
    
    # 6. Maintenance cost data
    maintenance_cost_query = """
        SELECT WT.WO_TYPE_NAME, SUM(ML.PARTS_COST + ML.LABOR_COST) AS TOTAL_COST
        FROM SNOWCORE_INDUSTRIES.SILVER.FCT_MAINTENANCE_LOG ML
        JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_WORK_ORDER_TYPE WT ON ML.WO_TYPE_ID = WT.WO_TYPE_ID
        GROUP BY WT.WO_TYPE_NAME;
    """
    
    # 7. Asset dimension for risk calculations
    asset_dim_query = "SELECT ASSET_ID, DOWNTIME_IMPACT_PER_HOUR FROM SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET WHERE IS_CURRENT = TRUE;"
    
    # --- DATA LOADING ---
    with st.spinner("Loading executive dashboard data..."):
        # Run all 7 queries
        queries = {
            'enterprise_ts': enterprise_timeseries_query,
            'plant_ts': plant_timeseries_query,
            'plant_current': plant_current_query,
            'gold_data': gold_data_query,
            'health_ts': health_timeseries_query,
            'cost_by_type': maintenance_cost_query,
            'asset_dim': asset_dim_query
        }
        
        # Execute all queries sequentially
        results = run_queries_sequential(queries)
        
        # Extract results
        enterprise_ts = results['enterprise_ts']
        plant_ts = results['plant_ts']
        plant_current = results['plant_current']
        gold_data = results['gold_data']
        health_ts = results['health_ts']
        cost_by_type = results['cost_by_type']
        asset_dim = results['asset_dim']
    
    # --- SECTION 1: TOP-LEVEL KPI CARDS WITH SPARKLINES ---
    st.subheader("Key Performance Indicators")
    
    # Calculate current metrics (convert to float to avoid Decimal type issues)
    if len(enterprise_ts) > 0:
        current_oee = float(enterprise_ts.iloc[-1]['OEE'])
        prior_week_oee = float(enterprise_ts.iloc[-8:-1]['OEE'].mean()) if len(enterprise_ts) >= 8 else current_oee
        oee_delta = ((current_oee - prior_week_oee) / prior_week_oee * 100) if prior_week_oee > 0 else 0
    else:
        current_oee = 0.0
        oee_delta = 0.0
    
    current_health = float(gold_data['LATEST_HEALTH_SCORE'].mean())
    prior_week_health = float(health_ts.iloc[-8:-1]['AVG_HEALTH_SCORE'].mean()) if len(health_ts) >= 8 else current_health
    health_delta = current_health - prior_week_health
    
    asset_details_for_risk = pd.merge(gold_data, asset_dim, on='ASSET_ID')
    production_at_risk = float((asset_details_for_risk['AVG_FAILURE_PROBABILITY'] * 
                         asset_details_for_risk['DOWNTIME_IMPACT_PER_HOUR'] * 24).sum())
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Overall Equipment Effectiveness (OEE)",
            f"{current_oee:.1%}",
            f"{oee_delta:+.1f}% vs prior week"
        )
        # Mini sparkline for OEE
        if len(enterprise_ts) > 0:
            fig_spark_oee = px.line(enterprise_ts, x='PRODUCTION_DATE', y='OEE')
            fig_spark_oee.update_layout(
                height=80, margin=dict(l=0, r=0, t=0, b=0),
                showlegend=False, xaxis_visible=False, yaxis_visible=False
            )
            fig_spark_oee.update_traces(line_color='#1f77b4')
            st.plotly_chart(fig_spark_oee, use_container_width=True)
    
    with col2:
        st.metric(
            "Average Asset Health Score",
            f"{current_health:.1f}",
            f"{health_delta:+.1f} vs prior week"
        )
        # Mini sparkline for Health
        if len(health_ts) > 0:
            fig_spark_health = px.line(health_ts, x='HEALTH_DATE', y='AVG_HEALTH_SCORE')
            fig_spark_health.update_layout(
                height=80, margin=dict(l=0, r=0, t=0, b=0),
                showlegend=False, xaxis_visible=False, yaxis_visible=False
            )
            fig_spark_health.update_traces(line_color='#2ca02c')
            st.plotly_chart(fig_spark_health, use_container_width=True)
    
    with col3:
        st.metric(
            "Production at Risk",
            f"${production_at_risk:,.0f}",
            "Daily exposure"
        )
    
    st.divider()
    
    # --- SECTION 2: ENTERPRISE OEE TREND WITH COMPONENTS ---
    st.subheader("Enterprise OEE Performance Trend (Last 30 Days)")
    
    if len(enterprise_ts) > 0:
        fig_enterprise = go.Figure()
        
        # Add OEE line
        fig_enterprise.add_trace(go.Scatter(
            x=enterprise_ts['PRODUCTION_DATE'],
            y=enterprise_ts['OEE'],
            name='OEE',
            mode='lines+markers',
            line=dict(color='#1f77b4', width=3),
            marker=dict(size=6)
        ))
        
        # Add Availability line
        fig_enterprise.add_trace(go.Scatter(
            x=enterprise_ts['PRODUCTION_DATE'],
            y=enterprise_ts['AVAILABILITY'],
            name='Availability',
            mode='lines',
            line=dict(color='#ff7f0e', width=2, dash='dot')
        ))
        
        # Add Performance line
        fig_enterprise.add_trace(go.Scatter(
            x=enterprise_ts['PRODUCTION_DATE'],
            y=enterprise_ts['PERFORMANCE'],
            name='Performance',
            mode='lines',
            line=dict(color='#2ca02c', width=2, dash='dot')
        ))
        
        # Add Quality line
        fig_enterprise.add_trace(go.Scatter(
            x=enterprise_ts['PRODUCTION_DATE'],
            y=enterprise_ts['QUALITY'],
            name='Quality',
            mode='lines',
            line=dict(color='#d62728', width=2, dash='dot')
        ))
        
        # Add target line at 85%
        fig_enterprise.add_hline(
            y=0.85, 
            line_dash="dash", 
            line_color="gray",
            annotation_text="Target (85%)",
            annotation_position="right"
        )
        
        fig_enterprise.update_layout(
            xaxis_title="Date",
            yaxis_title="Percentage",
            yaxis_tickformat='.0%',
            hovermode='x unified',
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        st.plotly_chart(fig_enterprise, use_container_width=True)
    else:
        st.warning("No enterprise OEE time-series data available.")
    
    st.divider()
    
    # --- SECTION 3: PLANT PERFORMANCE TABLE WITH TRENDS ---
    st.subheader("Plant Performance Summary")
    
    if len(plant_current) > 0:
        # Calculate OEE components for each plant
        plant_summary = []
        for _, row in plant_current.iterrows():
            oee, avail, perf, qual = calculate_oee(pd.DataFrame([row]))
            
            # Get trend data for this plant (convert to float for comparison)
            plant_trend = plant_ts[plant_ts['PLANT_NAME'] == row['PLANT_NAME']].tail(14)
            trend_direction = "📈" if len(plant_trend) >= 2 and float(plant_trend.iloc[-1]['OEE']) > float(plant_trend.iloc[0]['OEE']) else "📉"
            
            plant_summary.append({
                'Plant': row['PLANT_NAME'],
                'OEE': float(oee),
                'Availability': float(avail),
                'Performance': float(perf),
                'Quality': float(qual),
                'Trend': trend_direction
            })
        
        plant_df = pd.DataFrame(plant_summary)
        
        # Display as formatted table
        st.dataframe(
            plant_df.style.format({
                'OEE': '{:.1%}',
                'Availability': '{:.1%}',
                'Performance': '{:.1%}',
                'Quality': '{:.1%}'
            }).background_gradient(cmap='RdYlGn', subset=['OEE'], vmin=0.6, vmax=0.95),
            use_container_width=True,
            hide_index=True
        )
        
        # Show plant OEE trends as multi-line chart
        st.subheader("Plant OEE Trends Comparison")
        if len(plant_ts) > 0:
            fig_plants = px.line(
                plant_ts,
                x='PRODUCTION_DATE',
                y='OEE',
                color='PLANT_NAME',
                title='OEE by Plant Over Time',
                markers=True
            )
            fig_plants.update_layout(
                xaxis_title="Date",
                yaxis_title="OEE",
                yaxis_tickformat='.0%',
                hovermode='x unified',
                height=400,
                legend_title="Plant"
            )
            st.plotly_chart(fig_plants, use_container_width=True)
    else:
        st.warning("No plant performance data available.")
    
    st.divider()
    
    # --- SECTION 4: FINANCIAL PERFORMANCE & MAINTENANCE COST RATIO ---
    st.subheader("Financial Performance & Maintenance Analysis")
    
    col4, col5 = st.columns([1, 1.5])
    
    with col4:
        st.markdown("### Predictive Maintenance ROI")
        pdm_program_cost = 50000.0
        cost_avoidance = 150000.0
        pdm_roi = (cost_avoidance - pdm_program_cost) / pdm_program_cost if pdm_program_cost > 0 else 0.0
        
        st.metric("Cost Avoidance (YTD)", f"${cost_avoidance:,.0f}")
        st.metric("PdM Program Cost", f"${pdm_program_cost:,.0f}")
        st.metric("PdM Program ROI", f"{pdm_roi:.1%}", f"+{pdm_roi:.0%} return")
        
    with col5:
        st.markdown("### Maintenance Cost Distribution")
        if len(cost_by_type) > 0:
            fig_pie = px.pie(
                cost_by_type,
                names='WO_TYPE_NAME',
                values='TOTAL_COST',
                title="Cost by Maintenance Type",
                hole=0.4
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.warning("No maintenance cost data available.")

