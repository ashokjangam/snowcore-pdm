# pages/2_🔧_Fleet_Operations_Center.py
import streamlit as st
import pandas as pd
import plotly.express as px
from utils.data_loader import get_operations_data

def show_page():
    """Fleet Operations Center view - Real-time monitoring and alert triage"""
    
    st.header("🔧 Fleet Operations Center")
    st.markdown("Real-time monitoring, alert triage, and maintenance resource dispatch.")
    
    # --- Data Loading ---
    data = get_operations_data()
    df = data['assets']  # Health data is already merged into assets
    tech_df = data['technicians']
    
    # Check if data loaded successfully
    if df.empty:
        st.error("⚠️ Unable to load asset data. Please ensure the database is properly configured.")
        return
    
    # Check for required columns
    required_cols = ['asset_id', 'asset_type', 'location', 'health_score', 'predicted_failure_mode', 'rul_days']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.error(f"⚠️ Missing required columns: {missing_cols}")
        return
    
    # --- Asset Risk Triage List ---
    st.subheader("Asset Risk Triage List")
    
    # Filters for the triage list
    f1, f2 = st.columns(2)
    
    # Get unique asset types, filtering out None values
    asset_types = df['asset_type'].dropna().unique().tolist()
    if not asset_types:
        asset_types = ['Unknown']
    
    selected_type = f1.multiselect("Filter by Asset Type:", options=asset_types, default=asset_types)
    health_threshold = f2.slider("Show assets with health score below:", 0, 100, 80)
    
    # Filter by type and health score, handling null values
    triage_df = df[
        (df['asset_type'].isin(selected_type)) & 
        (df['health_score'].notna()) &
        (df['health_score'] <= health_threshold)
    ].copy()
    
    if not triage_df.empty:
        triage_df = triage_df.sort_values('health_score').reset_index(drop=True)
        
        st.dataframe(triage_df[['asset_id', 'location', 'health_score', 'predicted_failure_mode', 'rul_days']],
                 column_config={
                     "health_score": st.column_config.ProgressColumn(
                         "Health Score",
                         help="The AI-powered health score of the asset. Lower is worse.",
                         min_value=0,
                         max_value=100,
                         format="%d"
                     ),
                     "rul_days": st.column_config.NumberColumn(
                         "RUL (Days)",
                         help="Remaining Useful Life in days until predicted failure."
                     )
                 }, use_container_width=True)
    else:
        st.info("📊 No assets found matching the current filters.")

    # --- Click-to-Detail Simulation ---
    st.markdown("#### Asset Deep Dive")
    
    if not triage_df.empty:
        selected_asset_id = st.selectbox("Select an asset to see details:", options=triage_df['asset_id'])
    
        if selected_asset_id:
            with st.expander(f"Details for {selected_asset_id}", expanded=True):
                asset_details = df[df['asset_id'] == selected_asset_id].iloc[0]
                
                st.write(f"**Location:** {asset_details['location']} | **Type:** {asset_details['asset_type']} | **Model:** {asset_details['model']}")
                
                c1, c2 = st.columns([2,1])
                with c1:
                    st.write("**Recent Sensor Readings**")
                    
                    # Check if sensors data exists and has asset_id column
                    if data['sensors'].empty:
                        st.warning("No sensor data available in the last 24 hours.")
                        sensor_data = pd.DataFrame()
                    elif 'asset_id' not in data['sensors'].columns:
                        st.error(f"⚠️ Sensors data missing 'asset_id' column. Available columns: {data['sensors'].columns.tolist()}")
                        sensor_data = pd.DataFrame()
                    else:
                        sensor_data = data['sensors'][data['sensors']['asset_id'] == selected_asset_id]
                    
                    if not sensor_data.empty:
                        fig = px.line(sensor_data, x='timestamp', y=['temperature', 'vibration'], title="Vibration & Temperature Trend")
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("No detailed sensor data available for this asset.")

                with c2:
                    st.write("**Maintenance History**")
                    
                    # Check if maintenance data exists and has asset_id column
                    if data['maintenance'].empty:
                        st.info("No maintenance history available (last 90 days).")
                        history = pd.DataFrame()
                    elif 'asset_id' not in data['maintenance'].columns:
                        st.error(f"⚠️ Maintenance data missing 'asset_id' column. Available columns: {data['maintenance'].columns.tolist()}")
                        history = pd.DataFrame()
                    else:
                        history = data['maintenance'][data['maintenance']['asset_id'] == selected_asset_id].head(5)
                    
                    if not history.empty:
                        st.dataframe(history[['timestamp', 'notes']], use_container_width=True, hide_index=True)
                    else:
                        st.info("No recent maintenance history.")

                st.write("**Recommended Actions:**")
                b1, b2, b3 = st.columns(3)
                if b1.button("Create High-Priority Work Order", key=f"wo_{selected_asset_id}"):
                    st.toast(f"✅ Work Order created for {selected_asset_id} in CMMS!", icon="🛠️")
                if b2.button("Acknowledge Alert", key=f"ack_{selected_asset_id}"):
                    st.toast(f"👍 Alert for {selected_asset_id} acknowledged.", icon="🔔")
                if b3.button("Snooze Alert (24h)", key=f"snz_{selected_asset_id}"):
                    st.toast(f"😴 Alert for {selected_asset_id} snoozed.", icon="💤")
    else:
        st.info("👆 Adjust the filters above to see assets.")

    st.markdown("<hr>", unsafe_allow_html=True)
    
    # --- Other Visualizations ---
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Technician Status & Workload")
        if not tech_df.empty:
            fig_tech = px.bar(tech_df, x='workload', y='technician', orientation='h', title="Active Work Orders per Technician")
            fig_tech.update_layout(yaxis_title=None, xaxis_title="Work Orders")
            st.plotly_chart(fig_tech, use_container_width=True)
        else:
            st.info("No technician workload data available.")
    
    with c2:
        st.subheader("Alerts Feed")
        if not triage_df.empty:
            alerts = triage_df[triage_df['health_score'] < 50].head(5)
            if not alerts.empty:
                for _, row in alerts.iterrows():
                    st.error(f"**CRITICAL ALERT:** {row['predicted_failure_mode']} predicted on **{row['asset_id']}** in {row['location']}.")
            else:
                st.success("✅ No critical alerts at this time.")
        else:
            st.info("No alerts to display.")

