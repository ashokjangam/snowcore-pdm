import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session
from typing import Dict, Optional
import logging
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@st.cache_resource
def init_connection():
    """Initializes a connection to Snowflake using active session (SiS)."""
    session = get_active_session()
    return session

conn = init_connection()

@st.cache_data(ttl=600)
def run_query(query: str, params: list = None) -> pd.DataFrame:
    """Executes a query and returns a Pandas DataFrame, with results cached."""
    session = conn
    # Snowpark session.sql() returns a DataFrame that can be converted to pandas
    if params:
        # For parameterized queries, format the query with parameters
        # Note: Snowpark doesn't support parameterized queries the same way as connector
        # This is a simplified approach - may need adjustment based on actual usage
        formatted_query = query
        for param in params:
            if isinstance(param, str):
                formatted_query = formatted_query.replace('?', f"'{param}'", 1)
            else:
                formatted_query = formatted_query.replace('?', str(param), 1)
        return session.sql(formatted_query).to_pandas()
    else:
        return session.sql(query).to_pandas()


def run_queries_sequential(
    queries: Dict[str, str],
    return_empty_on_error: bool = True
) -> Dict[str, pd.DataFrame]:
    """
    Execute multiple queries sequentially (one after another).
    
    Args:
        queries: Dictionary mapping result names to SQL query strings
        return_empty_on_error: If True, returns empty DataFrame on error; if False, raises exception
        
    Returns:
        Dictionary mapping result names to DataFrames
    """
    import time
    start_time = time.time()
    
    results = {}
    errors = {}
    
    for name, query in queries.items():
        try:
            result = run_query(query)
            results[name] = result
        except Exception as e:
            error_msg = f"Query '{name}' failed: {str(e)}"
            logger.error(error_msg)
            errors[name] = str(e)
            
            if return_empty_on_error:
                results[name] = pd.DataFrame()
            else:
                raise Exception(error_msg) from e
    
    elapsed_time = time.time() - start_time
    logger.debug(f"Sequential query execution completed in {elapsed_time:.2f}s")
    
    # Show errors in UI if any occurred
    if errors:
        for name, error in errors.items():
            st.warning(f"⚠️ Query '{name}' failed: {error}")
    
    return results


# ==================================================================================================
# REST API Authentication Helpers (for Cortex Analyst and Intelligence Agent)
# ==================================================================================================

def get_oauth_token() -> str:
    """
    Read the OAuth token from the Snowflake session token file.
    This is available when running in Snowflake (SiS - Streamlit in Snowflake).
    
    Returns:
        OAuth token string
        
    Raises:
        FileNotFoundError: If the token file doesn't exist (not running in Snowflake)
    """
    token_path = "/snowflake/session/token"
    try:
        with open(token_path, "r") as f:
            token = f.read().strip()
            return token
    except FileNotFoundError:
        logger.error(f"Token file not found at {token_path}. Are you running in Snowflake?")
        raise


def get_pat_token(connection_name: Optional[str] = None) -> str:
    """
    Get authentication token. Uses OAuth token from Snowflake session.
    
    Args:
        connection_name: Deprecated - kept for backward compatibility, not used
        
    Returns:
        OAuth token string
    """
    return get_oauth_token()


def get_base_url(account: str) -> str:
    """
    Build the base URL for Snowflake REST API calls.
    Uses the SNOWFLAKE_HOST environment variable if available,
    otherwise constructs from account identifier.
    
    Args:
        account: Snowflake account identifier (e.g., 'xy12345.us-west-2.aws')
        
    Returns:
        Base URL string (e.g., 'https://xy12345.us-west-2.aws.snowflakecomputing.com')
    """
    snowflake_host = os.getenv("SNOWFLAKE_HOST")
    
    if snowflake_host:
        # Remove any protocol prefix if present
        snowflake_host = snowflake_host.replace("https://", "").replace("http://", "")
        base_url = f"https://{snowflake_host}"
    else:
        # Construct from account identifier
        # Handle different account formats (some include region, some don't)
        if "." in account:
            base_url = f"https://{account}.snowflakecomputing.com"
        else:
            # If no region specified, this might fail - log a warning
            logger.warning(f"Account '{account}' doesn't include region, URL may be incorrect")
            base_url = f"https://{account}.snowflakecomputing.com"
    
    return base_url


def build_snowflake_headers(token: str, accept: str = 'application/json') -> Dict[str, str]:
    """
    Build HTTP headers for Snowflake REST API authentication using OAuth token.
    
    Args:
        token: OAuth token from Snowflake session
        accept: Accept header value (e.g., 'application/json' or 'text/event-stream')
        
    Returns:
        Dictionary of HTTP headers
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": accept,
        "Authorization": f"Bearer {token}",
        "X-Snowflake-Authorization-Token-Type": "OAUTH"
    }
    
    return headers


def get_verify_ssl(config_value: any = True) -> bool:
    """
    Determine whether to verify SSL certificates for API calls.
    
    Args:
        config_value: Configuration value (can be bool, string, or None)
        
    Returns:
        Boolean indicating whether to verify SSL
    """
    if isinstance(config_value, bool):
        return config_value
    elif isinstance(config_value, str):
        return config_value.lower() not in ['false', 'no', '0']
    else:
        return True  # Default to secure (verify SSL)


# ==================================================================================================
# Data Loading Functions for Pages
# ==================================================================================================

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_operations_data() -> Dict[str, pd.DataFrame]:
    """
    Load data for Fleet Operations Center page.
    
    Returns:
        Dictionary containing:
        - 'assets': Asset information with health scores
        - 'health': Health scores and predictions (merged into assets for convenience)
        - 'technicians': Technician workload information
        - 'sensors': Recent sensor readings
        - 'maintenance': Maintenance history
    """
    try:
        # Query 1: Assets with current health scores
        assets_query = """
        SELECT 
            a.ASSET_ID as asset_id_num,
            a.ASSET_NAME as asset_id,
            COALESCE(ac.CLASS_NAME, 'Unknown') as asset_type,
            CONCAT(COALESCE(p.PLANT_NAME, 'Unknown'), ' - ', COALESCE(l.LINE_NAME, 'Unknown')) as location,
            a.MODEL,
            COALESCE(h.LATEST_HEALTH_SCORE, 50.0) as health_score,
            COALESCE(h.AVG_FAILURE_PROBABILITY, 0.0) as failure_probability,
            COALESCE(h.MIN_RUL_DAYS, 999) as rul_days,
            CASE 
                WHEN COALESCE(h.AVG_FAILURE_PROBABILITY, 0) > 0.7 THEN 'Bearing Failure'
                WHEN COALESCE(h.AVG_FAILURE_PROBABILITY, 0) > 0.5 THEN 'Sensor Degradation'
                WHEN COALESCE(h.AVG_FAILURE_PROBABILITY, 0) > 0.3 THEN 'Performance Degradation'
                ELSE 'Normal Wear'
            END as predicted_failure_mode
        FROM SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET a
        LEFT JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET_CLASS ac 
            ON a.ASSET_CLASS_ID = ac.ASSET_CLASS_ID
        LEFT JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_PROCESS proc 
            ON a.PROCESS_ID = proc.PROCESS_ID
        LEFT JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_LINE l 
            ON proc.LINE_ID = l.LINE_ID
        LEFT JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_PLANT p 
            ON l.PLANT_ID = p.PLANT_ID
        LEFT JOIN (
            SELECT 
                ASSET_ID,
                LATEST_HEALTH_SCORE,
                AVG_FAILURE_PROBABILITY,
                MIN_RUL_DAYS,
                ROW_NUMBER() OVER (PARTITION BY ASSET_ID ORDER BY HOUR_TIMESTAMP DESC) as rn
            FROM SNOWCORE_INDUSTRIES.GOLD.AGG_ASSET_HOURLY_HEALTH
        ) h ON a.ASSET_ID = h.ASSET_ID AND h.rn = 1
        WHERE a.IS_CURRENT = TRUE
        ORDER BY COALESCE(h.AVG_FAILURE_PROBABILITY, 0) DESC
        """
        
        # Query 2: Technician workload
        technicians_query = """
        SELECT 
            t.TECHNICIAN_NAME as technician,
            COUNT(ml.LOG_ID) as workload
        FROM SNOWCORE_INDUSTRIES.SILVER.DIM_TECHNICIAN t
        LEFT JOIN SNOWCORE_INDUSTRIES.SILVER.FCT_MAINTENANCE_LOG ml 
            ON t.TECHNICIAN_ID = ml.TECHNICIAN_ID
            AND ml.COMPLETED_DATE >= DATEADD(day, -30, CURRENT_DATE())
        WHERE t.IS_ACTIVE = TRUE
        GROUP BY t.TECHNICIAN_NAME
        ORDER BY workload DESC
        """
        
        # Query 3: Recent sensor readings (last 24 hours for all assets)
        sensors_query = """
        SELECT 
            a.ASSET_NAME as asset_id,
            t.RECORDED_AT as timestamp,
            t.TEMPERATURE_C as temperature,
            t.VIBRATION_MM_S as vibration,
            t.PRESSURE_PSI as pressure
        FROM SNOWCORE_INDUSTRIES.SILVER.FCT_ASSET_TELEMETRY t
        JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET a 
            ON t.ASSET_ID = a.ASSET_ID
        WHERE t.RECORDED_AT >= DATEADD(hour, -24, CURRENT_TIMESTAMP())
            AND a.IS_CURRENT = TRUE
        ORDER BY t.RECORDED_AT DESC
        """
        
        # Query 4: Recent maintenance history
        maintenance_query = """
        SELECT 
            a.ASSET_NAME as asset_id,
            ml.COMPLETED_DATE as timestamp,
            CONCAT(
                wt.WO_TYPE_NAME, 
                CASE WHEN ml.FAILURE_FLAG THEN ' (FAILURE)' ELSE '' END,
                ' - ', 
                COALESCE(ml.TECHNICIAN_NOTES, 'No notes')
            ) as notes,
            ml.DOWNTIME_HOURS,
            ml.PARTS_COST + ml.LABOR_COST as total_cost
        FROM SNOWCORE_INDUSTRIES.SILVER.FCT_MAINTENANCE_LOG ml
        JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET a 
            ON ml.ASSET_ID = a.ASSET_ID
        JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_WORK_ORDER_TYPE wt 
            ON ml.WO_TYPE_ID = wt.WO_TYPE_ID
        WHERE ml.COMPLETED_DATE >= DATEADD(day, -90, CURRENT_DATE())
            AND a.IS_CURRENT = TRUE
        ORDER BY ml.COMPLETED_DATE DESC
        """
        
        # Execute queries sequentially
        queries = {
            'assets_raw': assets_query,
            'technicians': technicians_query,
            'sensors': sensors_query,
            'maintenance': maintenance_query
        }
        
        results = run_queries_sequential(queries)
        
        # Process assets data
        assets_df = results['assets_raw']
        
        # Convert column names to lowercase for consistency
        if not assets_df.empty:
            assets_df.columns = [col.lower() for col in assets_df.columns]
        
        # Create separate health dataframe (for backward compatibility)
        # Column names are now lowercase after conversion above
        if not assets_df.empty:
            # Build health dataframe with available columns
            health_cols = []
            rename_map = {}
            
            # Check which columns exist and add them
            if 'asset_id' in assets_df.columns:
                health_cols.append('asset_id')
            if 'health_score' in assets_df.columns:
                health_cols.append('health_score')
            if 'failure_probability' in assets_df.columns:
                health_cols.append('failure_probability')
            if 'rul_days' in assets_df.columns:
                health_cols.append('rul_days')
            if 'predicted_failure_mode' in assets_df.columns:
                health_cols.append('predicted_failure_mode')
            
            if health_cols:
                health_df = assets_df[health_cols].copy()
            else:
                health_df = pd.DataFrame()
        else:
            health_df = pd.DataFrame()
        
        # Convert column names to lowercase for all dataframes for consistency
        technicians_df = results['technicians']
        if not technicians_df.empty:
            technicians_df.columns = [col.lower() for col in technicians_df.columns]
        
        sensors_df = results['sensors']
        if not sensors_df.empty:
            sensors_df.columns = [col.lower() for col in sensors_df.columns]
        
        maintenance_df = results['maintenance']
        if not maintenance_df.empty:
            maintenance_df.columns = [col.lower() for col in maintenance_df.columns]
        
        return {
            'assets': assets_df,
            'health': health_df,
            'technicians': technicians_df,
            'sensors': sensors_df,
            'maintenance': maintenance_df
        }
        
    except Exception as e:
        logger.error(f"Error loading operations data: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Try to provide more helpful error info
        if hasattr(st, 'error'):
            st.error(f"Database query error: {str(e)}")
            with st.expander("🔍 Show error details"):
                st.code(traceback.format_exc())
        
        # Return empty dataframes as fallback
        return {
            'assets': pd.DataFrame(),
            'health': pd.DataFrame(),
            'technicians': pd.DataFrame(),
            'sensors': pd.DataFrame(),
            'maintenance': pd.DataFrame()
        }


# Alias for backward compatibility
get_mock_data = get_operations_data