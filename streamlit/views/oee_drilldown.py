# ==================================================================================================
# VIEW SPECIFICATION: OEE Drill-Down
# ==================================================================================================
#
# PURPOSE:
#   - Enable users to investigate operational efficiency issues.
#   - Provides a clear drill-path from a high-level plant comparison down to individual production lines.
#
# DATA SOURCES:
#   - `SNOWCORE_INDUSTRIES.SILVER` Layer: This view queries the transactional and dimensional data to build
#     the OEE hierarchy.
#     - `FCT_PRODUCTION_LOG`: The core fact table containing runtime and production counts.
#     - `DIM_ASSET`: To link production data to the asset hierarchy.
#     - `DIM_LINE`: To link assets to their production lines.
#     - `DIM_PLANT`: To link lines to their parent plants.
#
# ==================================================================================================

import streamlit as st
import pandas as pd
import plotly.express as px
from utils.data_loader import run_query
from utils.calculations import calculate_oee

def show_page():
    """OEE Drill-Down view - Plant and line-level efficiency analysis"""
    
    st.header("📉 OEE Drill-Down")
    
    # --- On-Demand Data Loading ---
    # This single, comprehensive query fetches all data needed for the OEE hierarchy.
    query = """
      SELECT
                P.PLANT_NAME,
                L.LINE_NAME,
                PR.PROCESS_NAME,
                A.ASSET_NAME,
                A.ASSET_UNS_NK,
                PL.PLANNED_RUNTIME_HOURS,
                PL.ACTUAL_RUNTIME_HOURS,
                PL.UNITS_PRODUCED,
                PL.UNITS_SCRAPPED
            FROM SNOWCORE_INDUSTRIES.SILVER.FCT_PRODUCTION_LOG PL
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET A ON PL.ASSET_ID = A.ASSET_ID AND A.IS_CURRENT = TRUE
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_PROCESS PR ON PR.PROCESS_ID = A.PROCESS_ID
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_LINE L ON PR.LINE_ID = L.LINE_ID
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_PLANT P ON L.PLANT_ID = P.PLANT_ID;
    """
    df = run_query(query)
    
    # --- OEE Calculations & UI ---
    plant_oee = df.groupby('PLANT_NAME').apply(calculate_oee).apply(pd.Series)
    plant_oee.columns = ['OEE', 'Availability', 'Performance', 'Quality']
    plant_oee = plant_oee.sort_values('OEE', ascending=False).reset_index()
    
    st.subheader("1. Plant Performance Comparison")
    fig_plant = px.bar(plant_oee, x='PLANT_NAME', y='OEE', text=plant_oee['OEE'].apply(lambda x: f'{x:.1%}'), title="OEE by Plant")
    st.plotly_chart(fig_plant, use_container_width=True)
    
    st.subheader("2. Line Performance Drill-Down")
    selected_plant = st.selectbox("Select a Plant to Investigate:", options=plant_oee['PLANT_NAME'])
    
    # Store the selection in the session state for cross-page drill-path functionality.
    st.session_state['selected_plant_name'] = selected_plant
    st.info(f"Drill path state saved: Plant '{selected_plant}' is now active.")
    
    if selected_plant:
        line_df = df[df['PLANT_NAME'] == selected_plant]
        line_oee = line_df.groupby('LINE_NAME').apply(calculate_oee).apply(pd.Series)
        line_oee.columns = ['OEE', 'Availability', 'Performance', 'Quality']
        line_oee = line_oee.sort_values('OEE').reset_index()
        
        st.dataframe(line_oee.style.format({
            'OEE': '{:.2%}', 'Availability': '{:.2%}', 'Performance': '{:.2%}', 'Quality': '{:.2%}'
        }).background_gradient(cmap='Reds_r', subset=['OEE', 'Availability']), use_container_width=True)

