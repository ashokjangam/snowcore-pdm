import streamlit as st
import json
import requests
import os
import pandas as pd
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Optional, Tuple
from .data_loader import run_query, get_base_url, get_pat_token, build_snowflake_headers, get_verify_ssl

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AVAILABLE_SEMANTIC_MODELS_PATHS = ["SNOWCORE_INDUSTRIES.GOLD.SEMANTIC_VIEW_STAGE/SNOWCORE_INDUSTRIES_SV.yaml"]
API_TIMEOUT = 50

class SnowflakeCortexAnalyst:
    def __init__(self, account: str, user: str, role: Optional[str] = None, verify_ssl: bool = True):
        self.account = account
        self.user = user
        self.role = role
        self.verify_ssl = verify_ssl

        self.base_url = get_base_url(account)
        # Optional connection name to support SNOWFLAKE_CONNECTIONS_<NAME>_TOKEN
        try:
            self.connection_name = st.secrets.get("features", {}).get("connection_name")
        except:
            self.connection_name = None

    def _get_valid_token(self) -> str:
        return get_pat_token(self.connection_name)
    
    def _make_api_request(self, endpoint: str, data: dict) -> Tuple[dict, Optional[str]]:
        try:
            token = self._get_valid_token()
            headers = build_snowflake_headers(token, accept='application/json')
            url = f"{self.base_url}{endpoint}"
            
            print(f"🔍 API REQUEST DEBUG:")
            print(f"URL: {url}")
            print(f"Request Body: {json.dumps(data, indent=2)}")
            print("=" * 50)
            
            response = requests.post(
                url, headers=headers, json=data, 
                timeout=API_TIMEOUT, verify=self.verify_ssl
            )
            
            print(f"🔍 API RESPONSE DEBUG:")
            print(f"Status Code: {response.status_code}")
            print(f"Response Content: {response.text[:500]}...")
            print("=" * 50)
            
            if response.status_code < 400:
                return response.json(), None
            else:
                error_data = response.json() if response.content else {}
                error_msg = f"🚨 Cortex Analyst API Error - Status: {response.status_code}, Message: {error_data.get('message', 'Unknown')}"
                return error_data, error_msg
                
        except Exception as e:
            return {}, f"🚨 Request failed: {str(e)}"

    def get_analyst_response(self, messages: List[Dict], semantic_model_path: str) -> Tuple[dict, Optional[str]]:
        # Convert messages to the correct format expected by Cortex Analyst API
        # Cortex Analyst needs alternating user/assistant messages for context
        api_messages = []
        for msg in messages:
            if msg["role"] == "user":
                api_messages.append({
                    "role": "user",
                    "content": [{"type": "text", "text": msg["content"]}]
                })
            elif msg["role"] == "assistant" and msg.get("api_content"):
                # Use the original API response content structure if available
                api_messages.append({
                    "role": "analyst",  # Cortex uses "analyst" role for responses
                    "content": msg["api_content"]
                })
        
        # CRITICAL: Ensure roles alternate (Cortex Analyst requirement)
        # Filter out consecutive messages with the same role
        api_messages = self._ensure_alternating_roles(api_messages)
        
        # Debug: Show message role sequence
        role_sequence = [msg.get("role", "unknown") for msg in api_messages]
        print(f"🔧 Message role sequence: {' -> '.join(role_sequence)}")
        
        # Try with SQL execution enabled first
        request_body = {
            "messages": api_messages,
            "semantic_model_file": f"@{semantic_model_path}",
        }
        if self.role:
            request_body["role"] = self.role
        
        print(f"🔧 Calling Cortex Analyst API with {len(api_messages)} messages...")
        return self._make_api_request("/api/v2/cortex/analyst/message", request_body)
    
    def _ensure_alternating_roles(self, messages: List[Dict]) -> List[Dict]:
        """
        Ensure messages alternate between user and analyst roles.
        Cortex Analyst API requires strict alternation.
        
        Args:
            messages: List of messages with roles
            
        Returns:
            Filtered list with alternating roles
        """
        if not messages:
            return messages
        
        filtered = []
        last_role = None
        
        for msg in messages:
            current_role = msg.get("role")
            
            # Skip if same role as previous (keep only the last one of consecutive same-role messages)
            if current_role == last_role:
                # Replace the previous message with this one (keep most recent)
                if filtered:
                    filtered[-1] = msg
                continue
            
            filtered.append(msg)
            last_role = current_role
        
        # API must start with user message
        if filtered and filtered[0].get("role") != "user":
            filtered = filtered[1:]  # Remove leading analyst message
        
        # API must end with user message (we're asking for a response)
        if filtered and filtered[-1].get("role") != "user":
            logger.warning("Message list doesn't end with user message - this may cause issues")
        
        return filtered

    def get_complete_response(self, messages: List[Dict], semantic_model_path: str) -> Tuple[str, Optional[str], Optional[List]]:
        """
        Get complete Cortex Analyst response with SQL execution using data_loader.
        
        Returns:
            Tuple of (formatted_response, error_message, api_content_structure)
            The api_content_structure is the original API response content that should be
            stored for followup questions.
        """
        
        print("🤖 Getting response from Cortex Analyst...")
        response, error = self.get_analyst_response(messages, semantic_model_path)
        
        if error:
            return "", error, None
        
        if isinstance(response, dict) and "message" in response:
            content = response["message"]["content"]
            
            text_parts = []
            sql_statement = None
            
            for item in content:
                if item["type"] == "text":
                    text_parts.append(item["text"])
                elif item["type"] == "sql":
                    sql_statement = item["statement"]
            
            interpretation = "\n\n".join(text_parts)
            
            # If we have SQL, execute it with data_loader
            if sql_statement:
                print("🔍 Executing SQL with data_loader...")
                print(f"📝 SQL Query:\n{sql_statement}")
                try:
                    df = run_query(sql_statement)
                    print(f"📊 Query returned {len(df)} rows with {len(df.columns)} columns")
                    print(f"📋 Column names: {list(df.columns)}")
                    
                    if len(df) > 0:
                        # Debug: Show first row to understand data structure
                        if len(df) > 0:
                            print(f"🔍 First row sample: {df.iloc[0].to_dict()}")
                        
                        formatted_results = self._format_results(df, interpretation)
                        return formatted_results, None, content
                    else:
                        return f"{interpretation}\n\n📊 Query executed successfully but returned no results.", None, content
                
                except Exception as sql_error:
                    return f"{interpretation}\n\n🚨 Error executing query: {str(sql_error)}", None, content
            
            return interpretation, None, content
        
        return str(response), None, None
    
    def _format_results(self, df: pd.DataFrame, interpretation: str) -> str:
        """
        Format DataFrame results for display.
        Dynamically handles whatever columns are returned.
        """
        formatted = f"**{interpretation}**\n\n📊 **Query Results ({len(df)} rows):**\n\n"
        
        # Get column names (case-insensitive mapping)
        cols_lower = {col.upper(): col for col in df.columns}
        
        for idx, row in df.head(10).iterrows():
            # Try to find an identifier column (asset name, ID, etc.)
            identifier = None
            for name_col in ['ASSET_NAME', 'NAME', 'ASSET_ID', 'ID']:
                if name_col in cols_lower:
                    identifier = row[cols_lower[name_col]]
                    break
            
            if identifier:
                formatted += f"**{idx + 1}. {identifier}**\n"
            else:
                formatted += f"**{idx + 1}. Row {idx + 1}**\n"
            
            # Display all columns in the result
            for col in df.columns:
                col_upper = col.upper()
                value = row[col]
                
                # Skip the identifier column (already displayed)
                if identifier and value == identifier:
                    continue
                
                # Format based on column name and value type
                if pd.isna(value) or value is None:
                    continue  # Skip null values
                
                # Format numbers nicely
                if isinstance(value, (int, float)):
                    if 'PROB' in col_upper or 'RISK' in col_upper:
                        formatted += f"   • {col}: {value:.3f}\n"
                    elif 'SCORE' in col_upper or 'PERCENT' in col_upper:
                        formatted += f"   • {col}: {value:.1f}%\n"
                    elif 'COST' in col_upper or 'IMPACT' in col_upper or 'PRICE' in col_upper:
                        formatted += f"   • {col}: ${value:,.2f}\n"
                    elif 'HOURS' in col_upper or 'DAYS' in col_upper:
                        formatted += f"   • {col}: {value:.1f}\n"
                    else:
                        formatted += f"   • {col}: {value:,.2f}\n"
                else:
                    formatted += f"   • {col}: {value}\n"
            
            formatted += "\n"
        
        if len(df) > 10:
            formatted += f"... and {len(df) - 10} more rows\n"
        
        return formatted

# Global client instance
_cortex_client: Optional[SnowflakeCortexAnalyst] = None

def _get_cortex_client() -> SnowflakeCortexAnalyst:
    global _cortex_client
    
    if _cortex_client is None:
        # Get configuration from secrets if available, otherwise use environment/session
        import os
        
        # Try to get from secrets first
        try:
            config = st.secrets["snowflake"]
            account = config["account"]
            user = config["user"]
            role = config.get("role")
            verify_ssl = get_verify_ssl(config.get("verify_ssl", True))
            logger.info("Using configuration from secrets.toml")
        except:
            # When running in SiS with OAuth, get from environment/session
            try:
                from snowflake.snowpark.context import get_active_session
                
                session = get_active_session()
                account = os.getenv("SNOWFLAKE_ACCOUNT", "")
                user = session.sql("SELECT CURRENT_USER()").collect()[0][0]
                role = session.sql("SELECT CURRENT_ROLE()").collect()[0][0]
                verify_ssl = True
                logger.info("Using configuration from Snowflake session")
            except Exception as e:
                logger.warning(f"Failed to get session info: {e}. Using environment variables.")
                # Fallback to environment variables
                account = os.getenv("SNOWFLAKE_ACCOUNT", "")
                user = os.getenv("USER", "UNKNOWN")
                role = None
                verify_ssl = True

        _cortex_client = SnowflakeCortexAnalyst(
            account=account,
            user=user,
            role=role,
            verify_ssl=verify_ssl
        )
    
    return _cortex_client

def build_analyst_widget(
    title: str = "Cortex Analyst 🤖",
    semantic_model_path: str = "SNOWCORE_INDUSTRIES.GOLD.SEMANTIC_VIEW_STAGE/SNOWCORE_INDUSTRIES_SV.yaml",
    initial_message: str = "Hi! Ask me anything about your Snowcore_Industries manufacturing data.",
    placeholder: str = "e.g., 'What assets have the highest risk?'"
):
    st.subheader(title)
    
    try:
        client = _get_cortex_client()
    except Exception as e:
        st.error(f"Failed to initialize Cortex client: {e}")
        return

    messages_key = f"cortex_messages_{semantic_model_path.replace('/', '_').replace('.', '_')}"
    
    if messages_key not in st.session_state:
        st.session_state[messages_key] = [{"role": "assistant", "content": initial_message}]
    
    for message in st.session_state[messages_key]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"], unsafe_allow_html=True)

    if prompt := st.chat_input(placeholder):
        st.session_state[messages_key].append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("🤖 Analyzing..."):
                try:
                    api_messages = []
                    for msg in st.session_state[messages_key]:
                        if msg["role"] in ["user", "assistant"]:
                            api_messages.append(msg)
                    
                    assistant_response, error_msg, api_content = client.get_complete_response(api_messages, semantic_model_path)
                    
                    if error_msg:
                        assistant_response = error_msg
                        st.error(error_msg)
                    
                    st.markdown(assistant_response, unsafe_allow_html=True)
                    
                    # Store both the formatted response and the original API content
                    assistant_msg = {"role": "assistant", "content": assistant_response}
                    if api_content:
                        assistant_msg["api_content"] = api_content
                    st.session_state[messages_key].append(assistant_msg)

                except Exception as e:
                    error_msg = f"🚨 Unexpected error: {str(e)}"
                    st.error(error_msg)
                    st.session_state[messages_key].append({"role": "assistant", "content": error_msg})
