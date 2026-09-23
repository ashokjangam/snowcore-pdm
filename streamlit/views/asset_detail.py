# ==================================================================================================
# VIEW SPECIFICATION: Asset Detail View
# ==================================================================================================
#
# PURPOSE:
#   - Provide comprehensive information for a single asset and its associated sensors.
#   - Parameterized by asset selection and date range for flexible analysis.
#   - Real-time monitoring capabilities with historical context.
#
# DATA SOURCES:
#   - Primary: `SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET` for asset details
#   - Primary: `SNOWCORE_INDUSTRIES.SILVER.DIM_SENSOR` for sensor information
#   - Primary: `SNOWCORE_INDUSTRIES.SILVER.FCT_ASSET_TELEMETRY` for time-series sensor data
#   - Primary: `SNOWCORE_INDUSTRIES.GOLD.AGG_ASSET_HOURLY_HEALTH` for health metrics
#   - Secondary: `SNOWCORE_INDUSTRIES.SILVER.FCT_MAINTENANCE_LOG` for maintenance history
#
# ==================================================================================================

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from utils.data_loader import run_query, run_queries_sequential

def show_page():
    """Asset Detail view - Comprehensive asset monitoring and analysis"""
    
    st.header("🔍 Asset Detail View")
    st.markdown("Comprehensive monitoring and analysis for individual assets with real-time sensor data.")
    
    # Initialize session state for asset and date range
    if 'selected_asset_id' not in st.session_state:
        st.session_state.selected_asset_id = None
    if 'selected_date_range' not in st.session_state:
        st.session_state.selected_date_range = '7d'
    if 'real_time_mode' not in st.session_state:
        st.session_state.real_time_mode = False
    
    # --- Control Panel ---
    st.subheader("Asset Selection & Configuration")
    
    # Create two columns for controls
    control_col1, control_col2, control_col3 = st.columns([2, 1, 1])
    
    with control_col1:
        # Hierarchical asset selection
        st.markdown("**Asset Selection**")
        
        # Initialize session state for hierarchy
        if 'selected_plant' not in st.session_state:
            st.session_state.selected_plant = None
        if 'selected_line' not in st.session_state:
            st.session_state.selected_line = None
        if 'selected_process' not in st.session_state:
            st.session_state.selected_process = None
        if 'selected_asset' not in st.session_state:
            st.session_state.selected_asset = None
        
        # Get hierarchy data
        try:
            hierarchy_query = """
                SELECT 
                    A.ASSET_ID,
                    A.ASSET_NAME,
                    A.MODEL,
                    A.OEM_NAME,
                    AC.CLASS_NAME,
                    P.PROCESS_NAME,
                    L.LINE_NAME,
                    PL.PLANT_NAME
                FROM SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET A
                JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET_CLASS AC ON A.ASSET_CLASS_ID = AC.ASSET_CLASS_ID
                JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_PROCESS P ON A.PROCESS_ID = P.PROCESS_ID
                JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_LINE L ON P.LINE_ID = L.LINE_ID
                JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_PLANT PL ON L.PLANT_ID = PL.PLANT_ID
                WHERE A.IS_CURRENT = TRUE
                ORDER BY PL.PLANT_NAME, L.LINE_NAME, P.PROCESS_NAME, A.ASSET_NAME
            """
            hierarchy_data = run_query(hierarchy_query)
        except Exception as e:
            st.warning(f"Database connection issue: {str(e)}")
            hierarchy_data = pd.DataFrame()
        
        if not hierarchy_data.empty:
            # Add reset button
            if st.button("🔄 Reset Selection", help="Clear all selections and start over"):
                st.session_state.selected_plant = None
                st.session_state.selected_line = None
                st.session_state.selected_process = None
                st.session_state.selected_asset = None
                st.session_state.selected_asset_id = None
                st.rerun()
            
            # Create a visual hierarchy display
            with st.expander("🏭 Manufacturing Hierarchy", expanded=True):
                # Step 1: Plant Selection
                plants = hierarchy_data['PLANT_NAME'].unique()
                selected_plant = st.selectbox(
                    "🏭 Select Plant:",
                    options=plants,
                    index=0 if st.session_state.selected_plant is None else list(plants).index(st.session_state.selected_plant) if st.session_state.selected_plant in plants else 0,
                    key="plant_selector"
                )
                st.session_state.selected_plant = selected_plant
                
                # Step 2: Line Selection (filtered by plant)
                if selected_plant:
                    plant_data = hierarchy_data[hierarchy_data['PLANT_NAME'] == selected_plant]
                    lines = plant_data['LINE_NAME'].unique()
                    
                    selected_line = st.selectbox(
                        "📏 Select Production Line:",
                        options=lines,
                        index=0 if st.session_state.selected_line is None else list(lines).index(st.session_state.selected_line) if st.session_state.selected_line in lines else 0,
                        key="line_selector"
                    )
                    st.session_state.selected_line = selected_line
                    
                    # Step 3: Process Selection (filtered by line)
                    if selected_line:
                        line_data = plant_data[plant_data['LINE_NAME'] == selected_line]
                        processes = line_data['PROCESS_NAME'].unique()
                        
                        selected_process = st.selectbox(
                            "⚙️ Select Process:",
                            options=processes,
                            index=0 if st.session_state.selected_process is None else list(processes).index(st.session_state.selected_process) if st.session_state.selected_process in processes else 0,
                            key="process_selector"
                        )
                        st.session_state.selected_process = selected_process
                        
                        # Step 4: Asset Selection (filtered by process)
                        if selected_process:
                            process_data = line_data[line_data['PROCESS_NAME'] == selected_process]
                            assets = process_data[['ASSET_ID', 'ASSET_NAME', 'MODEL', 'OEM_NAME']].drop_duplicates()
                            
                            selected_asset = st.selectbox(
                                "🔧 Select Asset:",
                                options=assets['ASSET_ID'],
                                format_func=lambda x: f"{assets[assets['ASSET_ID'] == x]['ASSET_NAME'].iloc[0]} ({assets[assets['ASSET_ID'] == x]['MODEL'].iloc[0]})",
                                index=0 if st.session_state.selected_asset is None else list(assets['ASSET_ID']).index(st.session_state.selected_asset) if st.session_state.selected_asset in assets['ASSET_ID'].values else 0,
                                key="asset_selector"
                            )
                            st.session_state.selected_asset = selected_asset
                            st.session_state.selected_asset_id = selected_asset
                            
                            # Display selected asset details
                            if selected_asset:
                                asset_info = assets[assets['ASSET_ID'] == selected_asset].iloc[0]
                                st.success(f"✅ Selected: **{asset_info['ASSET_NAME']}** ({asset_info['MODEL']}) by {asset_info['OEM_NAME']}")
        else:
            st.error("No hierarchy data available")
            selected_asset = None
    
    with control_col2:
        # Date range selection
        date_presets = {
            '24h': 'Last 24 Hours',
            '7d': 'Last 7 Days', 
            '30d': 'Last 30 Days',
            'custom': 'Custom Range'
        }
        date_range = st.selectbox(
            "Time Range:",
            options=list(date_presets.keys()),
            format_func=lambda x: date_presets[x],
            index=list(date_presets.keys()).index(st.session_state.selected_date_range)
        )
        st.session_state.selected_date_range = date_range
    
    with control_col3:
        # Real-time toggle
        real_time = st.toggle("Real-time", value=st.session_state.real_time_mode)
        st.session_state.real_time_mode = real_time
    
    # Custom date range picker
    if date_range == 'custom':
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", value=datetime.now() - timedelta(days=7))
        with col2:
            end_date = st.date_input("End Date", value=datetime.now())
    else:
        # Calculate date range based on preset
        end_date = datetime.now()
        if date_range == '24h':
            start_date = end_date - timedelta(hours=24)
        elif date_range == '7d':
            start_date = end_date - timedelta(days=7)
        elif date_range == '30d':
            start_date = end_date - timedelta(days=30)
    
    # --- Main Content ---
    selected_asset = st.session_state.selected_asset if 'selected_asset' in st.session_state else None
    
    if selected_asset:
        # Load all data
        with st.spinner("Loading asset data..."):
            # Prepare queries
            asset_query = f"""
                SELECT 
                    A.ASSET_ID,
                    A.ASSET_NAME,
                    A.MODEL,
                    A.OEM_NAME,
                    A.INSTALLATION_DATE,
                    A.DOWNTIME_IMPACT_PER_HOUR,
                    AC.CLASS_NAME,
                    P.PROCESS_NAME,
                    L.LINE_NAME,
                    PL.PLANT_NAME,
                    G.LATEST_HEALTH_SCORE,
                    G.AVG_FAILURE_PROBABILITY,
                    G.MIN_RUL_DAYS
                FROM SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET A
                JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET_CLASS AC ON A.ASSET_CLASS_ID = AC.ASSET_CLASS_ID
                JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_PROCESS P ON A.PROCESS_ID = P.PROCESS_ID
                JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_LINE L ON P.LINE_ID = L.LINE_ID
                JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_PLANT PL ON L.PLANT_ID = PL.PLANT_ID
                LEFT JOIN (
                    SELECT ASSET_ID, LATEST_HEALTH_SCORE, AVG_FAILURE_PROBABILITY, MIN_RUL_DAYS
                    FROM SNOWCORE_INDUSTRIES.GOLD.AGG_ASSET_HOURLY_HEALTH
                    QUALIFY ROW_NUMBER() OVER (PARTITION BY ASSET_ID ORDER BY HOUR_TIMESTAMP DESC) = 1
                ) G ON A.ASSET_ID = G.ASSET_ID
                WHERE A.ASSET_ID = {selected_asset} AND A.IS_CURRENT = TRUE
            """
            
            sensor_query = f"""
                SELECT 
                    S.SENSOR_SK,
                    S.SENSOR_NK,
                    S.SENSOR_TYPE,
                    S.UNITS_OF_MEASURE,
                    T.RECORDED_AT,
                    T.TEMPERATURE_C,
                    T.VIBRATION_MM_S,
                    T.PRESSURE_PSI,
                    T.HEALTH_SCORE,
                    T.FAILURE_PROBABILITY,
                    T.RUL_DAYS,
                    T.IS_ANOMALOUS
                FROM SNOWCORE_INDUSTRIES.SILVER.DIM_SENSOR S
                JOIN SNOWCORE_INDUSTRIES.SILVER.FCT_ASSET_TELEMETRY T ON S.ASSET_ID = T.ASSET_ID
                WHERE S.ASSET_ID = {selected_asset} 
                AND T.RECORDED_AT BETWEEN '{start_date}' AND '{end_date}'
                ORDER BY T.RECORDED_AT DESC
            """
            
            maintenance_query = f"""
                SELECT 
                    ML.ACTION_DATE_SK,
                    ML.COMPLETED_DATE,
                    ML.DOWNTIME_HOURS,
                    ML.PARTS_COST,
                    ML.LABOR_COST,
                    ML.FAILURE_FLAG,
                    WT.WO_TYPE_NAME,
                    T.TECHNICIAN_NAME,
                    FC.FAILURE_DESCRIPTION,
                    ML.TECHNICIAN_NOTES
                FROM SNOWCORE_INDUSTRIES.SILVER.FCT_MAINTENANCE_LOG ML
                JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_WORK_ORDER_TYPE WT ON ML.WO_TYPE_ID = WT.WO_TYPE_ID
                LEFT JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_TECHNICIAN T ON ML.TECHNICIAN_ID = T.TECHNICIAN_ID
                LEFT JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_FAILURE_CODE FC ON ML.FAILURE_CODE_ID = FC.FAILURE_CODE_ID
                WHERE ML.ASSET_ID = {selected_asset}
                AND ML.COMPLETED_DATE BETWEEN '{start_date}' AND '{end_date}'
                ORDER BY ML.COMPLETED_DATE DESC
            """
            
            # Execute queries sequentially
            queries = {
                'asset_details': asset_query,
                'sensor_data': sensor_query,
                'maintenance_data': maintenance_query
            }
            results = run_queries_sequential(queries)
            
            # Extract results
            asset_details_df = results['asset_details']
            sensor_data = results['sensor_data']
            maintenance_data = results['maintenance_data']
        
        # Process asset details
        asset_details = asset_details_df.iloc[0] if not asset_details_df.empty else None
        
        if asset_details is not None:
            # Display asset overview
            st.subheader("Asset Overview")
            
            # Create columns for asset information
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Asset Name", asset_details.get('ASSET_NAME', 'N/A'))
                st.metric("Model", asset_details.get('MODEL', 'N/A'))
                st.metric("OEM", asset_details.get('OEM_NAME', 'N/A'))
            
            with col2:
                st.metric("Plant", asset_details.get('PLANT_NAME', 'N/A'))
                st.metric("Line", asset_details.get('LINE_NAME', 'N/A'))
                st.metric("Process", asset_details.get('PROCESS_NAME', 'N/A'))
            
            with col3:
                # Health metrics
                health_score = asset_details.get('LATEST_HEALTH_SCORE', 0)
                failure_prob = asset_details.get('AVG_FAILURE_PROBABILITY', 0)
                rul_days = asset_details.get('MIN_RUL_DAYS', 0)
                
                st.metric("Health Score", f"{health_score:.1f}%", delta=None)
                st.metric("Failure Probability", f"{failure_prob:.1%}")
                st.metric("RUL (Days)", f"{rul_days}")
            
            # Health status indicator
            if health_score >= 90:
                st.success("✅ Asset is in excellent condition")
            elif health_score >= 75:
                st.warning("⚠️ Asset requires attention")
            else:
                st.error("🚨 Asset requires immediate attention")
            
            if not sensor_data.empty:
                # Display sensor monitoring dashboard
                st.subheader("Sensor Monitoring Dashboard")
                
                # Get unique sensor types for this asset
                sensor_types = sensor_data['SENSOR_TYPE'].unique()
                
                # Create tabs for different sensor types
                if len(sensor_types) > 0:
                    tabs = st.tabs([f"📊 {sensor_type}" for sensor_type in sensor_types])
                    
                    for i, sensor_type in enumerate(sensor_types):
                        with tabs[i]:
                            # Filter data for this sensor type
                            type_data = sensor_data[sensor_data['SENSOR_TYPE'] == sensor_type]
                            
                            if not type_data.empty:
                                # Create time series chart
                                fig = go.Figure()
                                
                                # Add traces for different metrics
                                if 'TEMPERATURE_C' in type_data.columns and not type_data['TEMPERATURE_C'].isna().all():
                                    fig.add_trace(go.Scatter(
                                        x=type_data['RECORDED_AT'],
                                        y=type_data['TEMPERATURE_C'],
                                        mode='lines+markers',
                                        name='Temperature (°C)',
                                        line=dict(color='red')
                                    ))
                                
                                if 'VIBRATION_MM_S' in type_data.columns and not type_data['VIBRATION_MM_S'].isna().all():
                                    fig.add_trace(go.Scatter(
                                        x=type_data['RECORDED_AT'],
                                        y=type_data['VIBRATION_MM_S'],
                                        mode='lines+markers',
                                        name='Vibration (mm/s)',
                                        line=dict(color='blue'),
                                        yaxis='y2'
                                    ))
                                
                                if 'PRESSURE_PSI' in type_data.columns and not type_data['PRESSURE_PSI'].isna().all():
                                    fig.add_trace(go.Scatter(
                                        x=type_data['RECORDED_AT'],
                                        y=type_data['PRESSURE_PSI'],
                                        mode='lines+markers',
                                        name='Pressure (PSI)',
                                        line=dict(color='green'),
                                        yaxis='y3'
                                    ))
                                
                                # Update layout
                                fig.update_layout(
                                    title=f"{sensor_type} Sensor Readings Over Time",
                                    xaxis_title="Time",
                                    yaxis_title="Temperature (°C)",
                                    yaxis2=dict(title="Vibration (mm/s)", overlaying="y", side="right"),
                                    yaxis3=dict(title="Pressure (PSI)", overlaying="y", side="right"),
                                    hovermode='x unified',
                                    height=400
                                )
                                
                                st.plotly_chart(fig, use_container_width=True)
                                
                                # Display current values
                                latest_data = type_data.iloc[0]
                                col1, col2, col3 = st.columns(3)
                                
                                with col1:
                                    if not pd.isna(latest_data.get('TEMPERATURE_C')):
                                        st.metric("Current Temperature", f"{latest_data['TEMPERATURE_C']:.1f}°C")
                                
                                with col2:
                                    if not pd.isna(latest_data.get('VIBRATION_MM_S')):
                                        st.metric("Current Vibration", f"{latest_data['VIBRATION_MM_S']:.2f} mm/s")
                                
                                with col3:
                                    if not pd.isna(latest_data.get('PRESSURE_PSI')):
                                        st.metric("Current Pressure", f"{latest_data['PRESSURE_PSI']:.1f} PSI")
                            else:
                                st.info(f"No data available for {sensor_type} sensors")
                
                # Display maintenance history
                st.subheader("Maintenance History")
                
                if not maintenance_data.empty:
                    # Display maintenance summary
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        total_downtime = maintenance_data['DOWNTIME_HOURS'].sum()
                        st.metric("Total Downtime", f"{total_downtime:.1f} hours")
                    
                    with col2:
                        total_cost = (maintenance_data['PARTS_COST'] + maintenance_data['LABOR_COST']).sum()
                        st.metric("Total Cost", f"${total_cost:,.2f}")
                    
                    with col3:
                        failure_count = maintenance_data['FAILURE_FLAG'].sum()
                        st.metric("Failure Events", f"{failure_count}")
                    
                    # Display maintenance table
                    st.dataframe(
                        maintenance_data[['COMPLETED_DATE', 'WO_TYPE_NAME', 'DOWNTIME_HOURS', 'PARTS_COST', 'LABOR_COST', 'TECHNICIAN_NAME', 'TECHNICIAN_NOTES']],
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("No maintenance records found for the selected time period.")
            else:
                st.warning(f"No sensor data available for asset {selected_asset} in the selected time range.")
        else:
            st.warning(f"Could not load details for asset {selected_asset}")
    else:
        st.info("Please select an asset to view detailed information.")

