import streamlit as st
import streamlit.components.v1 as components
import os
import json
import pandas as pd
import hashlib
from utils.data_loader import run_query

@st.fragment
def render_visualization(selected_plant, selected_line, factory_data):
    """Fragment function to render the 3D visualization - can be rerun independently."""
    
    # Get the path to the HTML file (in streamlit root)
    html_file_path = os.path.join(os.path.dirname(__file__), "..", "line_visualization.html")
    
    # Read and display the HTML content
    try:
        with open(html_file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Replace the mock data with live data
        import re
        import time
        pattern = r'__REPLACE_WITH_LIVE_DATA__'
        replacement = json.dumps(factory_data, indent=2, ensure_ascii=False)
        html_content = re.sub(pattern, replacement, html_content, flags=re.DOTALL)
        
        # Create a unique hash based on the data to force complete refresh
        data_hash = hashlib.md5(json.dumps(factory_data).encode()).hexdigest()
        viz_id = f"{selected_plant}_{selected_line}_{data_hash}_{time.time()}"
        
        # Add multiple unique identifiers to force refresh
        unique_comments = f"""
        <!-- Visualization ID: {viz_id} -->
        <!-- Plant: {selected_plant} -->
        <!-- Line: {selected_line} -->
        <!-- Data Hash: {data_hash} -->
        <!-- Timestamp: {time.time()} -->
        <script>
        // Force unique instance
        window.VIZ_ID = '{viz_id}';
        console.log('Loading visualization:', window.VIZ_ID);
        </script>
        """
        html_content = html_content.replace('</body>', f'{unique_comments}</body>')
        
        # Debug output
        st.caption(f"🔄 Viz ID: {data_hash[:8]} | Plant: {selected_plant} | Line: {selected_line}")
        st.session_state['key'] = f"line_viz_{selected_plant}_{selected_line}_{data_hash}"
        
        # Render the HTML component
        components.html(
            html_content,
            height=600,
            scrolling=True
        )
        
    except FileNotFoundError:
        st.error("Line visualization HTML file not found. Please check the file path.")
    except Exception as e:
        st.error(f"Error loading visualization: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

def get_factory_data(plant_name, line_name):
    """Get complete factory data structure for visualization."""
    import time
    start_time = time.time()
    
    try:
        # Debug output
        st.info(f"🔍 Loading data for: {plant_name} → {line_name}")
        
        # Get plant info
        plant_query = f"""
            SELECT PLANT_ID, PLANT_NAME
            FROM SNOWCORE_INDUSTRIES.SILVER.DIM_PLANT
            WHERE PLANT_NAME = '{plant_name}'
        """
        plant_data = run_query(plant_query)
        
        if plant_data.empty:
            return {"id": "no_data", "name": "No Data", "type": "plant", "children": []}
        
        # Convert to native Python int to avoid numpy type issues
        plant_id = int(plant_data.iloc[0]['PLANT_ID'])
        
        # Get line info
        line_query = f"""
            SELECT L.LINE_ID, L.LINE_NAME
            FROM SNOWCORE_INDUSTRIES.SILVER.DIM_LINE L
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_PLANT P ON L.PLANT_ID = P.PLANT_ID
            WHERE P.PLANT_NAME = '{plant_name}' AND L.LINE_NAME = '{line_name}'
        """
        line_data = run_query(line_query)
        
        if line_data.empty:
            return {"id": "no_data", "name": "No Data", "type": "plant", "children": []}
        
        # Convert to native Python int to avoid numpy type issues
        line_id = int(line_data.iloc[0]['LINE_ID'])
        
        # Get processes and assets from the database
        assets_query = f"""
            SELECT DISTINCT
                P.PROCESS_ID,
                P.PROCESS_NAME,
                A.ASSET_ID,
                A.ASSET_NAME
            FROM SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET A
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_PROCESS P ON A.PROCESS_ID = P.PROCESS_ID
            WHERE P.LINE_ID = {line_id}
            ORDER BY P.PROCESS_ID, A.ASSET_ID
        """
        assets_data = run_query(assets_query)
        
        # Debug: Check if we have assets data
        if assets_data.empty:
            st.warning(f"No assets found for line_id: {line_id}")
            return {"id": "no_assets", "name": f"{plant_name} - {line_name}", "type": "plant", "children": [
                {"id": f"line_{line_id}", "name": line_name, "type": "line", "children": []}
            ]}
        
        # Get latest sensor readings for these assets from telemetry
        # Convert to native Python types to avoid numpy type issues
        asset_ids = [int(x) for x in assets_data['ASSET_ID'].tolist()]
        if asset_ids:
            # Format asset IDs for SQL IN clause
            asset_ids_str = ','.join([str(aid) for aid in asset_ids])
            
            sensors_query = f"""
                WITH latest_telemetry AS (
                    SELECT 
                        ASSET_ID,
                        TEMPERATURE_C,
                        VIBRATION_MM_S,
                        PRESSURE_PSI,
                        RECORDED_AT,
                        ROW_NUMBER() OVER (PARTITION BY ASSET_ID ORDER BY RECORDED_AT DESC) as rn
                    FROM SNOWCORE_INDUSTRIES.SILVER.FCT_ASSET_TELEMETRY
                    WHERE ASSET_ID IN ({asset_ids_str})
                )
                SELECT 
                    ASSET_ID,
                    TEMPERATURE_C,
                    VIBRATION_MM_S,
                    PRESSURE_PSI
                FROM latest_telemetry
                WHERE rn = 1
            """
            
            telemetry_data = run_query(sensors_query)
        else:
            telemetry_data = pd.DataFrame()
        
        # Build the factory data structure with the correct hierarchy: plant -> line -> processes
        factory_data = {
            "id": f"plant_{plant_id}",
            "name": plant_name,
            "type": "plant",
            "children": []
        }
        
        # Create the line level (required by HTML structure)
        line_data_obj = {
            "id": f"line_{line_id}",
            "name": line_name,
            "type": "line",
            "children": []
        }
        
        # Get health scores and predictions for assets from latest telemetry
        if asset_ids:
            asset_ids_str = ','.join([str(aid) for aid in asset_ids])
            
            health_query = f"""
                WITH latest_health AS (
                    SELECT 
                        ASSET_ID,
                        HEALTH_SCORE,
                        FAILURE_PROBABILITY,
                        RUL_DAYS,
                        IS_ANOMALOUS,
                        ROW_NUMBER() OVER (PARTITION BY ASSET_ID ORDER BY RECORDED_AT DESC) as rn
                    FROM SNOWCORE_INDUSTRIES.SILVER.FCT_ASSET_TELEMETRY
                    WHERE ASSET_ID IN ({asset_ids_str})
                )
                SELECT 
                    ASSET_ID,
                    HEALTH_SCORE,
                    FAILURE_PROBABILITY,
                    RUL_DAYS,
                    IS_ANOMALOUS
                FROM latest_health
                WHERE rn = 1
            """
            health_data = run_query(health_query)
            
            # Get downtime impact from DIM_ASSET
            asset_info_query = f"""
                SELECT 
                    ASSET_ID,
                    DOWNTIME_IMPACT_PER_HOUR
                FROM SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET
                WHERE ASSET_ID IN ({asset_ids_str})
            """
            asset_info_data = run_query(asset_info_query)
        else:
            health_data = pd.DataFrame()
            asset_info_data = pd.DataFrame()
        
        # Group assets by process
        processes = {}
        for _, asset in assets_data.iterrows():
            # Convert to native Python types
            process_id = int(asset['PROCESS_ID'])
            asset_id = int(asset['ASSET_ID'])
            
            if process_id not in processes:
                processes[process_id] = {
                    "id": f"proc_{process_id}",
                    "name": asset['PROCESS_NAME'],
                    "type": "process",
                    "children": []
                }
            
            # Get telemetry for this asset and transform to sensor format
            asset_telemetry = telemetry_data[telemetry_data['ASSET_ID'].astype(int) == asset_id] if not telemetry_data.empty else pd.DataFrame()
            sensor_children = []
            
            if not asset_telemetry.empty:
                telemetry_row = asset_telemetry.iloc[0]
                
                # Temperature sensor
                if telemetry_row['TEMPERATURE_C'] is not None:
                    temp_value = float(telemetry_row['TEMPERATURE_C'])
                    temp_status = 'normal'
                    if temp_value > 150:
                        temp_status = 'critical'
                    elif temp_value > 100:
                        temp_status = 'warning'
                    
                    sensor_children.append({
                        "id": f"sensor_{asset_id}_temp",
                        "type": "Temperature",
                        "value": round(temp_value, 2),
                        "unit": "°C",
                        "status": temp_status
                    })
                
                # Vibration sensor
                if telemetry_row['VIBRATION_MM_S'] is not None:
                    vib_value = float(telemetry_row['VIBRATION_MM_S'])
                    vib_status = 'normal'
                    if vib_value > 2.0:
                        vib_status = 'critical'
                    elif vib_value > 1.5:
                        vib_status = 'warning'
                    
                    sensor_children.append({
                        "id": f"sensor_{asset_id}_vib",
                        "type": "Vibration",
                        "value": round(vib_value, 2),
                        "unit": "mm/s",
                        "status": vib_status
                    })
                
                # Pressure sensor (if available)
                if telemetry_row['PRESSURE_PSI'] is not None:
                    pres_value = float(telemetry_row['PRESSURE_PSI'])
                    pres_status = 'normal'
                    if pres_value > 160 or pres_value < 120:
                        pres_status = 'warning'
                    
                    sensor_children.append({
                        "id": f"sensor_{asset_id}_pres",
                        "type": "Pressure",
                        "value": round(pres_value, 2),
                        "unit": "PSI",
                        "status": pres_status
                    })
            
            # Get health data for this asset (convert both sides to ensure proper comparison)
            asset_health = health_data[health_data['ASSET_ID'].astype(int) == asset_id] if not health_data.empty else pd.DataFrame()
            asset_info = asset_info_data[asset_info_data['ASSET_ID'].astype(int) == asset_id] if not asset_info_data.empty else pd.DataFrame()
            
            if not asset_health.empty:
                health_score = float(asset_health.iloc[0]['HEALTH_SCORE']) / 100.0 if asset_health.iloc[0]['HEALTH_SCORE'] is not None else 0.8  # Convert 0-100 to 0-1
                failure_prob = float(asset_health.iloc[0]['FAILURE_PROBABILITY']) if asset_health.iloc[0]['FAILURE_PROBABILITY'] is not None else 0.05
                rul_days = int(asset_health.iloc[0]['RUL_DAYS']) if asset_health.iloc[0]['RUL_DAYS'] is not None else 180
                is_anomalous = asset_health.iloc[0]['IS_ANOMALOUS'] if asset_health.iloc[0]['IS_ANOMALOUS'] is not None else False
                
                # Determine status based on health score and anomalies
                if is_anomalous or health_score < 0.5:
                    status = "Critical"
                elif health_score < 0.7:
                    status = "Warning"
                else:
                    status = "Online"
            else:
                health_score = 0.8
                status = "Online"
                failure_prob = 0.05
                rul_days = 180
            
            # Get downtime cost from asset info
            if not asset_info.empty:
                downtime_cost = float(asset_info.iloc[0]['DOWNTIME_IMPACT_PER_HOUR']) if asset_info.iloc[0]['DOWNTIME_IMPACT_PER_HOUR'] is not None else 5000
            else:
                downtime_cost = 5000
            
            # Create asset object with real data
            asset_obj = {
                "id": f"asset_{asset_id}",
                "name": asset['ASSET_NAME'],
                "type": "asset",
                "healthScore": health_score,
                "status": status,
                "pof": f"{failure_prob * 100:.1f}%",
                "cost": f"${downtime_cost:,.0f}/hr",
                "children": sensor_children
            }
            
            processes[process_id]["children"].append(asset_obj)
        
        # Add processes to line data
        for process in processes.values():
            line_data_obj["children"].append(process)
        
        # Add line to factory data
        factory_data["children"].append(line_data_obj)
        
        # Debug completion
        elapsed = time.time() - start_time
        asset_count = len(assets_data)
        process_count = len(processes)
        st.success(f"✅ Loaded {process_count} processes, {asset_count} assets in {elapsed:.2f}s")
        
        return factory_data
        
    except Exception as e:
        st.error(f"❌ Error loading factory data: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
        return {"id": "error", "name": "Error", "type": "plant", "children": []}

def show_page():
    """Line Visualization view - Interactive 3D factory floor visualization"""
    
    st.header("🏭 Line Visualization")
    st.markdown("Interactive 3D factory floor visualization with real-time asset monitoring")
    
    # Initialize session state for tracking selection changes
    if 'prev_plant' not in st.session_state:
        st.session_state.prev_plant = None
    if 'prev_line' not in st.session_state:
        st.session_state.prev_line = None
    if 'viz_counter' not in st.session_state:
        st.session_state.viz_counter = 0
    
    # Create columns for controls and visualization
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.subheader("Configuration")
        
        # Get live data from Snowflake
        try:
            plants_query = """
                SELECT DISTINCT PLANT_NAME
                FROM SNOWCORE_INDUSTRIES.SILVER.DIM_PLANT
                ORDER BY PLANT_NAME
            """
            plants_data = run_query(plants_query)
        except Exception as e:
            st.error(f"Error loading plants: {str(e)}")
            plants_data = pd.DataFrame()
        
        if plants_data.empty:
            st.warning("No plants found in the database.")
        else:
            selected_plant = st.selectbox(
                "Select Plant:",
                options=plants_data['PLANT_NAME'].tolist(),
                index=0
            )
            
            # Get lines for selected plant
            try:
                lines_query = f"""
                    SELECT DISTINCT L.LINE_NAME
                    FROM SNOWCORE_INDUSTRIES.SILVER.DIM_LINE L
                    JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_PLANT P ON L.PLANT_ID = P.PLANT_ID
                    WHERE P.PLANT_NAME = '{selected_plant}'
                    ORDER BY L.LINE_NAME
                """
                lines_data = run_query(lines_query)
            except Exception as e:
                st.error(f"Error loading lines: {str(e)}")
                lines_data = pd.DataFrame()
            
            if lines_data.empty:
                st.warning(f"No lines found for {selected_plant}.")
            else:
                selected_line = st.selectbox(
                    "Select Line:",
                    options=lines_data['LINE_NAME'].tolist(),
                    index=0
                )
                
                # Detect selection changes and increment counter to force refresh
                if (st.session_state.prev_plant != selected_plant or 
                    st.session_state.prev_line != selected_line):
                    st.session_state.prev_plant = selected_plant
                    st.session_state.prev_line = selected_line
                    st.session_state.viz_counter += 1
                
                # Display selection info
                st.info(f"**Selected:** {selected_plant} - {selected_line}")
                
                # Manual refresh button - forces complete rerun of the app
                if st.button("🔄 Refresh Visualization", use_container_width=True):
                    st.session_state.viz_counter += 1
                    st.rerun()
                
                # Additional controls
                st.subheader("Display Options")
                show_sensors = st.checkbox("Show Sensor Data", value=True)
                show_health_scores = st.checkbox("Show Health Scores", value=True)
                auto_refresh = st.checkbox("Auto Refresh", value=False)
                
                if auto_refresh:
                    refresh_interval = st.slider("Refresh Interval (seconds)", 5, 60, 30)
                    st.info(f"Auto-refreshing every {refresh_interval} seconds")
                    
                    # Initialize session state for auto-refresh
                    import time
                    if 'last_refresh' not in st.session_state:
                        st.session_state.last_refresh = time.time()
                    
                    # Check if it's time to refresh
                    elapsed = time.time() - st.session_state.last_refresh
                    if elapsed >= refresh_interval:
                        st.session_state.last_refresh = time.time()
                        st.rerun()
                    else:
                        # Show countdown
                        remaining = int(refresh_interval - elapsed)
                        st.text(f"Next refresh in {remaining} seconds...")
                        time.sleep(1)
                        st.rerun()
                
                # Get factory data for the selected plant and line
                with col2:
                    st.subheader("3D Factory Floor Visualization")
                    
                    factory_data = get_factory_data(selected_plant, selected_line)
                    
                    # Render the visualization using the fragment
                    render_visualization(selected_plant, selected_line, factory_data)
                    
                    # Additional information section
                    st.markdown("---")
                    st.markdown("### About This Visualization")
                    st.markdown("""
                    This interactive 3D visualization provides:
                    - **Real-time asset monitoring** with health scores and status indicators
                    - **Clickable assets** for detailed sensor data and maintenance information
                    - **Color-coded health indicators** (Green: Healthy, Yellow: Warning, Red: Critical)
                    - **Interactive 3D navigation** with zoom, pan, and rotate controls
                    - **Live sensor data** display for each asset
                    """)
                    
                    # Show data summary
                    with st.expander("Data Summary"):
                        if not factory_data.get('children', []):
                            st.warning("No data available for the selected plant and line.")
                        else:
                            line_data = factory_data['children'][0] if factory_data.get('children') else {}
                            processes = line_data.get('children', [])
                            st.write(f"**Processes:** {len(processes)}")
                            for process in processes:
                                assets = process.get('children', [])
                                st.write(f"- {process.get('name', 'Unknown')}: {len(assets)} assets")

