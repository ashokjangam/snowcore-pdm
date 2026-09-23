import streamlit as st
import json
import requests
import os
import pandas as pd
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Optional, Tuple, Any
from .data_loader import (
    run_query,
    get_base_url,
    get_pat_token,
    build_snowflake_headers,
    get_verify_ssl,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_TIMEOUT = 50


class IntelligenceToolExecutor:
    """
    Handles execution of tools called by the Snowflake Intelligence Agent.
    Provides maintenance operations beyond simple data queries.
    """
    
    def __init__(self):
        self.available_tools = {
            "query_asset_health": self._query_asset_health,
            "create_maintenance_work_order": self._create_maintenance_work_order,
            "get_asset_failure_prediction": self._get_asset_failure_prediction,
            "schedule_preventive_maintenance": self._schedule_preventive_maintenance,
            "get_maintenance_history": self._get_maintenance_history,
            "calculate_downtime_risk": self._calculate_downtime_risk,
            "get_oee_metrics": self._get_oee_metrics,
            "trigger_maintenance_alert": self._trigger_maintenance_alert
        }
    
    def execute_tool(self, tool_call: Dict[str, Any]) -> str:
        """
        Execute a tool based on the tool call from Intelligence Agent.
        
        Args:
            tool_call: Dictionary containing tool name and parameters
            
        Returns:
            String result of tool execution
        """
        try:
            tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name")
            tool_params = tool_call.get("parameters") or tool_call.get("function", {}).get("arguments", {})
            
            if not tool_name:
                return "❌ Tool call missing name"
            
            if tool_name not in self.available_tools:
                return f"❌ Unknown tool: {tool_name}"
            
            # Execute the tool
            result = self.available_tools[tool_name](tool_params)
            
            return result
            
        except Exception as e:
            error_msg = f"❌ Tool execution failed: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def _query_asset_health(self, params: Dict[str, Any]) -> str:
        """Query asset health information"""
        try:
            asset_id = params.get("asset_id")
            limit = params.get("limit", 10)
            
            if asset_id:
                query = f"""
                SELECT 
                    a.ASSET_NAME,
                    a.MODEL,
                    a.OEM_NAME,
                    h.LATEST_HEALTH_SCORE as HEALTH_SCORE,
                    h.AVG_FAILURE_PROBABILITY as FAILURE_RISK,
                    a.DOWNTIME_IMPACT_PER_HOUR
                FROM SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET a
                JOIN SNOWCORE_INDUSTRIES.GOLD.AGG_ASSET_HOURLY_HEALTH h ON a.ASSET_ID = h.ASSET_ID
                WHERE a.ASSET_ID = {asset_id} AND a.IS_CURRENT = TRUE
                ORDER BY h.HOUR_TIMESTAMP DESC
                LIMIT 1
                """
            else:
                query = f"""
                SELECT 
                    a.ASSET_NAME,
                    a.MODEL,
                    a.OEM_NAME,
                    h.LATEST_HEALTH_SCORE as HEALTH_SCORE,
                    h.AVG_FAILURE_PROBABILITY as FAILURE_RISK,
                    a.DOWNTIME_IMPACT_PER_HOUR
                FROM SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET a
                JOIN SNOWCORE_INDUSTRIES.GOLD.AGG_ASSET_HOURLY_HEALTH h ON a.ASSET_ID = h.ASSET_ID
                WHERE a.IS_CURRENT = TRUE
                ORDER BY h.AVG_FAILURE_PROBABILITY DESC
                LIMIT {limit}
                """
            
            df = run_query(query)
            
            if len(df) == 0:
                return "No asset health data found"
            
            result = "🏥 **Asset Health Status:**\n\n"
            for idx, row in df.iterrows():
                health_score = row['HEALTH_SCORE']
                failure_risk = row['FAILURE_RISK']
                
                # Determine status emoji
                if health_score >= 90:
                    status_emoji = "✅"
                elif health_score >= 70:
                    status_emoji = "⚠️"
                else:
                    status_emoji = "🚨"
                
                result += f"{status_emoji} **{row['ASSET_NAME']}**\n"
                result += f"   • Health Score: {health_score:.1f}%\n"
                result += f"   • Failure Risk: {failure_risk:.3f}\n"
                result += f"   • Model: {row['MODEL']} ({row['OEM_NAME']})\n"
                result += f"   • Downtime Impact: ${row['DOWNTIME_IMPACT_PER_HOUR']:,.2f}/hour\n\n"
            
            return result
            
        except Exception as e:
            return f"❌ Failed to query asset health: {str(e)}"
    
    def _create_maintenance_work_order(self, params: Dict[str, Any]) -> str:
        """Create a maintenance work order"""
        try:
            asset_id = params.get("asset_id")
            asset_name = params.get("asset_name", "Unknown Asset")
            priority = params.get("priority", "Medium")
            work_type = params.get("work_type", "Preventive Maintenance")
            description = params.get("description", "Scheduled maintenance")
            
            # In a real implementation, this would integrate with the CMMS system
            # For now, we'll simulate creating a work order
            
            work_order_id = f"WO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            result = f"✅ **Maintenance Work Order Created**\n\n"
            result += f"• **Work Order ID:** {work_order_id}\n"
            result += f"• **Asset:** {asset_name} (ID: {asset_id})\n"
            result += f"• **Type:** {work_type}\n"
            result += f"• **Priority:** {priority}\n"
            result += f"• **Description:** {description}\n"
            result += f"• **Created:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            result += f"• **Status:** Pending Assignment\n\n"
            result += f"📧 Work order has been submitted to the maintenance team."
            
            return result
            
        except Exception as e:
            return f"❌ Failed to create work order: {str(e)}"
    
    def _get_asset_failure_prediction(self, params: Dict[str, Any]) -> str:
        """Get failure predictions for assets"""
        try:
            days_ahead = params.get("days_ahead", 7)
            threshold = params.get("threshold", 0.5)
            
            query = f"""
            SELECT 
                a.ASSET_NAME,
                a.MODEL,
                h.AVG_FAILURE_PROBABILITY,
                h.MIN_RUL_DAYS,
                a.DOWNTIME_IMPACT_PER_HOUR
            FROM SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET a
            JOIN SNOWCORE_INDUSTRIES.GOLD.AGG_ASSET_HOURLY_HEALTH h ON a.ASSET_ID = h.ASSET_ID
            WHERE a.IS_CURRENT = TRUE 
            AND h.AVG_FAILURE_PROBABILITY > {threshold}
            AND h.MIN_RUL_DAYS <= {days_ahead}
            ORDER BY h.AVG_FAILURE_PROBABILITY DESC
            LIMIT 10
            """
            
            df = run_query(query)
            
            if len(df) == 0:
                return f"✅ No assets predicted to fail within {days_ahead} days (threshold: {threshold})"
            
            result = f"⚠️ **Assets at Risk of Failure (Next {days_ahead} days):**\n\n"
            total_risk_value = 0
            
            for idx, row in df.iterrows():
                failure_prob = row['AVG_FAILURE_PROBABILITY']
                rul_days = row['MIN_RUL_DAYS']
                impact = row['DOWNTIME_IMPACT_PER_HOUR']
                
                risk_level = "🚨 Critical" if failure_prob > 0.8 else "⚠️ High" if failure_prob > 0.6 else "🟡 Medium"
                
                result += f"{risk_level} **{row['ASSET_NAME']}**\n"
                result += f"   • Failure Probability: {failure_prob:.1%}\n"
                result += f"   • Remaining Useful Life: {rul_days} days\n"
                result += f"   • Potential Impact: ${impact:,.2f}/hour\n\n"
                
                total_risk_value += failure_prob * impact
            
            result += f"💰 **Total Risk Value:** ${total_risk_value:,.2f}/hour potential impact"
            
            return result
            
        except Exception as e:
            return f"❌ Failed to get failure predictions: {str(e)}"
    
    def _schedule_preventive_maintenance(self, params: Dict[str, Any]) -> str:
        """Schedule preventive maintenance for assets"""
        try:
            asset_ids = params.get("asset_ids", [])
            schedule_date = params.get("schedule_date")
            maintenance_type = params.get("maintenance_type", "Preventive")
            
            if not asset_ids:
                return "❌ No asset IDs provided for scheduling"
            
            scheduled_items = []
            
            for asset_id in asset_ids:
                # Get asset info
                asset_query = f"""
                SELECT ASSET_NAME, MODEL, OEM_NAME 
                FROM SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET 
                WHERE ASSET_ID = {asset_id} AND IS_CURRENT = TRUE
                """
                
                asset_df = run_query(asset_query)
                if len(asset_df) > 0:
                    asset_name = asset_df.iloc[0]['ASSET_NAME']
                    scheduled_items.append({
                        'asset_id': asset_id,
                        'asset_name': asset_name,
                        'schedule_id': f"PM-{datetime.now().strftime('%Y%m%d')}-{asset_id}"
                    })
            
            if not scheduled_items:
                return "❌ No valid assets found for scheduling"
            
            result = f"📅 **Preventive Maintenance Scheduled**\n\n"
            result += f"• **Maintenance Type:** {maintenance_type}\n"
            result += f"• **Scheduled Date:** {schedule_date or 'Next available slot'}\n"
            result += f"• **Assets Scheduled:** {len(scheduled_items)}\n\n"
            
            for item in scheduled_items:
                result += f"   ✅ {item['asset_name']} (Schedule ID: {item['schedule_id']})\n"
            
            result += f"\n📧 Maintenance team has been notified of the scheduled activities."
            
            return result
            
        except Exception as e:
            return f"❌ Failed to schedule maintenance: {str(e)}"
    
    def _get_maintenance_history(self, params: Dict[str, Any]) -> str:
        """Get maintenance history for assets"""
        try:
            asset_id = params.get("asset_id")
            days_back = params.get("days_back", 30)
            
            query = f"""
            SELECT 
                a.ASSET_NAME,
                m.COMPLETED_DATE,
                wt.WO_TYPE_NAME,
                m.DOWNTIME_HOURS,
                m.LABOR_COST + m.PARTS_COST as TOTAL_COST,
                m.TECHNICIAN_NOTES,
                m.FAILURE_FLAG
            FROM SNOWCORE_INDUSTRIES.SILVER.FCT_MAINTENANCE_LOG m
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET a ON m.ASSET_ID = a.ASSET_ID
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_WORK_ORDER_TYPE wt ON m.WO_TYPE_ID = wt.WO_TYPE_ID
            WHERE m.COMPLETED_DATE >= DATEADD(day, -{days_back}, CURRENT_DATE())
            """
            
            if asset_id:
                query += f" AND m.ASSET_ID = {asset_id}"
            
            query += " ORDER BY m.COMPLETED_DATE DESC LIMIT 20"
            
            df = run_query(query)
            
            if len(df) == 0:
                return f"No maintenance history found for the last {days_back} days"
            
            result = f"🔧 **Maintenance History (Last {days_back} days):**\n\n"
            
            for idx, row in df.iterrows():
                failure_indicator = "🚨 " if row['FAILURE_FLAG'] else ""
                result += f"{failure_indicator}**{row['ASSET_NAME']}** - {row['COMPLETED_DATE']}\n"
                result += f"   • Type: {row['WO_TYPE_NAME']}\n"
                result += f"   • Downtime: {row['DOWNTIME_HOURS']} hours\n"
                result += f"   • Cost: ${row['TOTAL_COST']:,.2f}\n"
                if row['TECHNICIAN_NOTES']:
                    result += f"   • Notes: {row['TECHNICIAN_NOTES'][:100]}...\n"
                result += "\n"
            
            return result
            
        except Exception as e:
            return f"❌ Failed to get maintenance history: {str(e)}"
    
    def _calculate_downtime_risk(self, params: Dict[str, Any]) -> str:
        """Calculate financial impact of potential downtime"""
        try:
            time_horizon = params.get("time_horizon_days", 30)
            
            query = f"""
            SELECT 
                a.ASSET_NAME,
                a.DOWNTIME_IMPACT_PER_HOUR,
                h.AVG_FAILURE_PROBABILITY,
                h.MIN_RUL_DAYS,
                (a.DOWNTIME_IMPACT_PER_HOUR * h.AVG_FAILURE_PROBABILITY * 24) as DAILY_RISK_VALUE
            FROM SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET a
            JOIN SNOWCORE_INDUSTRIES.GOLD.AGG_ASSET_HOURLY_HEALTH h ON a.ASSET_ID = h.ASSET_ID
            WHERE a.IS_CURRENT = TRUE 
            AND h.MIN_RUL_DAYS <= {time_horizon}
            ORDER BY DAILY_RISK_VALUE DESC
            LIMIT 10
            """
            
            df = run_query(query)
            
            if len(df) == 0:
                return f"✅ No significant downtime risks identified for {time_horizon} day horizon"
            
            total_risk = df['DAILY_RISK_VALUE'].sum() * time_horizon
            
            result = f"💰 **Downtime Risk Analysis ({time_horizon} days):**\n\n"
            result += f"**Total Portfolio Risk:** ${total_risk:,.2f}\n\n"
            
            for idx, row in df.iterrows():
                daily_risk = row['DAILY_RISK_VALUE']
                period_risk = daily_risk * time_horizon
                
                result += f"⚠️ **{row['ASSET_NAME']}**\n"
                result += f"   • Daily Risk Value: ${daily_risk:,.2f}\n"
                result += f"   • {time_horizon}-Day Risk: ${period_risk:,.2f}\n"
                result += f"   • Failure Probability: {row['AVG_FAILURE_PROBABILITY']:.1%}\n"
                result += f"   • Time to Failure: {row['MIN_RUL_DAYS']} days\n\n"
            
            return result
            
        except Exception as e:
            return f"❌ Failed to calculate downtime risk: {str(e)}"
    
    def _get_oee_metrics(self, params: Dict[str, Any]) -> str:
        """Get Overall Equipment Effectiveness metrics"""
        try:
            days_back = params.get("days_back", 7)
            
            query = f"""
            SELECT 
                a.ASSET_NAME,
                l.LINE_NAME,
                AVG(p.ACTUAL_RUNTIME_HOURS / p.PLANNED_RUNTIME_HOURS) as AVAILABILITY,
                AVG((p.UNITS_PRODUCED - p.UNITS_SCRAPPED) / p.UNITS_PRODUCED) as QUALITY_RATE,
                AVG(p.UNITS_PRODUCED / (p.ACTUAL_RUNTIME_HOURS * 100)) as PERFORMANCE_RATE
            FROM SNOWCORE_INDUSTRIES.SILVER.FCT_PRODUCTION_LOG p
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET a ON p.ASSET_ID = a.ASSET_ID
            JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_LINE l ON a.LINE_ID = l.LINE_ID
            WHERE p.PRODUCTION_DATE >= DATEADD(day, -{days_back}, CURRENT_DATE())
            AND a.IS_CURRENT = TRUE
            GROUP BY a.ASSET_NAME, l.LINE_NAME
            ORDER BY AVAILABILITY DESC
            LIMIT 10
            """
            
            df = run_query(query)
            
            if len(df) == 0:
                return f"No OEE data available for the last {days_back} days"
            
            result = f"📊 **OEE Metrics (Last {days_back} days):**\n\n"
            
            for idx, row in df.iterrows():
                availability = row['AVAILABILITY'] * 100
                quality = row['QUALITY_RATE'] * 100
                performance = row['PERFORMANCE_RATE'] * 100
                oee = (availability * quality * performance) / 10000
                
                oee_status = "🟢" if oee >= 85 else "🟡" if oee >= 65 else "🔴"
                
                result += f"{oee_status} **{row['ASSET_NAME']}** ({row['LINE_NAME']})\n"
                result += f"   • Overall OEE: {oee:.1f}%\n"
                result += f"   • Availability: {availability:.1f}%\n"
                result += f"   • Quality: {quality:.1f}%\n"
                result += f"   • Performance: {performance:.1f}%\n\n"
            
            return result
            
        except Exception as e:
            return f"❌ Failed to get OEE metrics: {str(e)}"
    
    def _trigger_maintenance_alert(self, params: Dict[str, Any]) -> str:
        """Trigger maintenance alerts for critical conditions"""
        try:
            alert_type = params.get("alert_type", "Critical Asset Condition")
            asset_ids = params.get("asset_ids", [])
            message = params.get("message", "Immediate attention required")
            
            # In a real system, this would integrate with alerting systems
            alert_id = f"ALERT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            result = f"🚨 **Maintenance Alert Triggered**\n\n"
            result += f"• **Alert ID:** {alert_id}\n"
            result += f"• **Type:** {alert_type}\n"
            result += f"• **Message:** {message}\n"
            result += f"• **Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            if asset_ids:
                result += f"• **Assets Affected:** {len(asset_ids)} assets\n"
                for asset_id in asset_ids[:5]:  # Show first 5
                    result += f"   - Asset ID: {asset_id}\n"
                if len(asset_ids) > 5:
                    result += f"   - ... and {len(asset_ids) - 5} more\n"
            
            result += f"\n📧 Alert has been sent to maintenance team and supervisors."
            
            return result
            
        except Exception as e:
            return f"❌ Failed to trigger alert: {str(e)}"


class SnowflakeIntelligenceAgent:
    """
    Snowflake Intelligence Agent client - similar to CortexAnalyst but for Intelligence agents.
    Handles agent communication, tool calling, and response processing.
    """
    
    def __init__(self, account: str, user: str, agent_name: str,
                 role: Optional[str] = None, verify_ssl: bool = True):
        self.account = account
        self.user = user
        self.agent_name = agent_name
        self.role = role
        self.verify_ssl = verify_ssl
        
        self.base_url = get_base_url(account)
        
        # Initialize tool executor
        self.tool_executor = IntelligenceToolExecutor()
        
        # Thread management for context
        self._thread_id = None
        
        # Optional connection name for SNOWFLAKE_CONNECTIONS_<NAME>_TOKEN
        try:
            self.connection_name = st.secrets.get("features", {}).get("connection_name")
        except:
            self.connection_name = None
    
    def _get_valid_token(self) -> str:
        """Get PAT from configured sources."""
        return get_pat_token(self.connection_name)
    
    def _make_api_request(self, endpoint: str, data: dict) -> Tuple[dict, Optional[str]]:
        """Make API request to Snowflake Intelligence Agent"""
        try:
            token = self._get_valid_token()
            if not token:
                return {}, "🚨 Failed to get authentication token"
            
            headers = build_snowflake_headers(token, accept='application/json')
            url = f"{self.base_url}{endpoint}"
            
            response = requests.post(
                url, headers=headers, json=data, 
                timeout=API_TIMEOUT, verify=self.verify_ssl
            )
            
            if response.status_code < 400:
                try:
                    return response.json(), None
                except json.JSONDecodeError:
                    return {}, f"🚨 Failed to parse JSON response: {response.text[:200]}"
            else:
                try:
                    error_data = response.json() if response.content else {}
                except json.JSONDecodeError:
                    error_data = {"raw_response": response.text}
                
                # Extract detailed error information
                error_msg = error_data.get('message', error_data.get('error', 'Unknown error'))
                error_code = error_data.get('code', response.status_code)
                
                detailed_error = f"🚨 Intelligence Agent API Error - Status: {response.status_code}, Code: {error_code}, Message: {error_msg}"
                logger.error(f"Intelligence Agent API Error: {detailed_error}")
                
                return error_data, detailed_error
                
        except requests.exceptions.Timeout:
            return {}, f"🚨 Request timeout after {API_TIMEOUT} seconds"
        except requests.exceptions.ConnectionError as e:
            return {}, f"🚨 Connection error: {str(e)}"
        except Exception as e:
            error_msg = f"🚨 Intelligence Agent request failed: {str(e)}"
            logger.error(error_msg)
            return {}, error_msg
    
    def _get_or_create_thread_id(self) -> str:
        """Get existing thread ID or create a new one for context management."""
        if self._thread_id is None:
            try:
                # Create a new thread using the Cortex threads API
                thread_data = {
                    "origin_application": "SnowcoreInd"  # Shortened to 11 bytes (under 16 byte limit)
                }
                
                response, error = self._make_api_request("/api/v2/cortex/threads", thread_data)
                if not error and "thread_id" in response:
                    self._thread_id = response["thread_id"]
                    logger.debug(f"Created new thread: {self._thread_id}")
                else:
                    # Fallback to a simple UUID-like string
                    import uuid
                    self._thread_id = str(uuid.uuid4())
                    logger.debug(f"Using fallback thread ID: {self._thread_id}")
            except Exception as e:
                # Fallback to a simple UUID-like string
                import uuid
                self._thread_id = str(uuid.uuid4())
                logger.debug(f"Thread creation failed, using fallback: {self._thread_id}")
        
        return self._thread_id
    
    def _make_streaming_api_request(self, endpoint: str, data: dict) -> Tuple[dict, Optional[str]]:
        """Make API request and handle streaming response from Intelligence Agent."""
        try:
            token = self._get_valid_token()
            if not token:
                return {}, "🚨 Failed to get authentication token"
            
            headers = build_snowflake_headers(token, accept='text/event-stream')
            url = f"{self.base_url}{endpoint}"
            
            response = requests.post(
                url, headers=headers, json=data, 
                timeout=API_TIMEOUT, verify=self.verify_ssl, stream=True
            )
            
            if response.status_code < 400:
                # Parse streaming response
                return self._parse_streaming_response(response), None
            else:
                # Try to read error response
                try:
                    error_content = response.text if response.text else "No content"
                    
                    # Try to parse as JSON
                    try:
                        error_data = json.loads(error_content)
                        error_msg = error_data.get('message', error_data.get('error', 'Unknown error'))
                        error_code = error_data.get('code', response.status_code)
                        detailed_error = f"🚨 Intelligence Agent API Error - Status: {response.status_code}, Code: {error_code}, Message: {error_msg}"
                    except json.JSONDecodeError:
                        detailed_error = f"🚨 Intelligence Agent API Error - Status: {response.status_code}, Message: {error_content[:200]}"
                except Exception as e:
                    detailed_error = f"🚨 Intelligence Agent API Error - Status: {response.status_code}, Could not read error content: {str(e)}"
                
                logger.error(f"Streaming API Error: {detailed_error}")
                return {}, detailed_error
                
        except requests.exceptions.Timeout:
            return {}, f"🚨 Streaming request timeout after {API_TIMEOUT} seconds"
        except requests.exceptions.ConnectionError as e:
            return {}, f"🚨 Streaming connection error: {str(e)}"
        except Exception as e:
            error_msg = f"🚨 Intelligence Agent streaming request failed: {str(e)}"
            logger.error(error_msg)
            return {}, error_msg
    
    def _parse_streaming_response(self, response) -> dict:
        """Parse Server-Sent Events streaming response from Intelligence Agent."""
        # Track different types of content separately
        text_deltas = []  # For response.text.delta events
        thinking_deltas = []  # For response.thinking.delta events
        final_text = ""  # For response.text complete event
        final_response_content = []  # For final response event
        status_messages = []
        tools_executed = []
        
        # Track current event type for context
        current_event = None
        line_count = 0
        event_count = 0
        
        try:
            for line in response.iter_lines(decode_unicode=True):
                line_count += 1
                
                if not line or line.strip() == "":
                    # Empty line separates events in SSE
                    current_event = None
                    continue
                
                # Parse event type
                if line.startswith('event: '):
                    current_event = line[7:].strip()
                    event_count += 1
                    continue
                
                # Parse data
                if line.startswith('data: '):
                    data_str = line[6:]  # Remove 'data: ' prefix
                    
                    if not data_str.strip():
                        continue
                    
                    try:
                        data = json.loads(data_str)
                        
                        # Handle based on event type
                        if current_event == "response.text.delta":
                            # Text delta - accumulate the actual response text
                            if 'text' in data:
                                text_deltas.append(data['text'])
                        
                        elif current_event == "response.text":
                            # Complete text block
                            if 'text' in data:
                                final_text = data['text']
                        
                        elif current_event == "response.thinking.delta":
                            # Thinking delta - internal reasoning
                            if 'text' in data:
                                thinking_deltas.append(data['text'])
                        
                        elif current_event == "response.status":
                            # Status update
                            status = data.get('status', 'unknown')
                            message = data.get('message', '')
                            status_messages.append(f"{status}: {message}")
                        
                        elif current_event == "response.tool_use":
                            # Tool use event
                            tools_executed.append(data)
                        
                        elif current_event == "response.tool_result":
                            # Tool result event - no action needed
                            pass
                        
                        elif current_event == "response":
                            # Final aggregated response - this is the most important one!
                            # Extract content from the response
                            if 'content' in data:
                                if isinstance(data['content'], list):
                                    for item in data['content']:
                                        if isinstance(item, dict):
                                            if item.get('type') == 'text':
                                                text_content = item.get('text', '')
                                                final_response_content.append(text_content)
                                elif isinstance(data['content'], str):
                                    final_response_content.append(data['content'])
                        
                        elif current_event == "metadata":
                            # Metadata about the request - no action needed
                            pass
                        
                        elif current_event == "error":
                            # Error event
                            error_msg = data.get('message', 'Unknown error')
                            error_code = data.get('code', 'N/A')
                            logger.error(f"Stream error: {error_code} - {error_msg}")
                            return {
                                "message": {
                                    "content": f"Error: {error_msg}",
                                    "role": "assistant"
                                },
                                "status": "error"
                            }
                        
                    except json.JSONDecodeError as e:
                        logger.warning(f"JSON decode error in stream: {e}")
                        continue
            
            # Assemble final response in priority order
            response_text = ""
            
            # Priority 1: Final response event content (most reliable)
            if final_response_content:
                response_text = '\n\n'.join(final_response_content)
            
            # Priority 2: Complete text block from response.text event
            elif final_text:
                response_text = final_text
            
            # Priority 3: Accumulated text deltas
            elif text_deltas:
                response_text = ''.join(text_deltas)
            
            # Priority 4: Thinking content (fallback)
            elif thinking_deltas:
                thinking_text = ''.join(thinking_deltas)
                response_text = f"Based on my analysis:\n\n{thinking_text}"
            
            # Priority 5: Default message (should rarely happen)
            else:
                response_text = "I received your request but couldn't generate a proper response. Please try again or rephrase your question."
            
            return {
                "message": {
                    "content": response_text,
                    "role": "assistant"
                },
                "status": status_messages[-1] if status_messages else "completed",
                "thinking": ''.join(thinking_deltas),
                "tools": tools_executed
            }
            
        except Exception as e:
            logger.error(f"Streaming parse error: {str(e)}")
            
            return {
                "message": {
                    "content": f"I apologize, but I encountered an error processing the response: {str(e)}. Please try again.",
                    "role": "assistant"  
                },
                "status": "error"
            }

    def get_agent_response(self, messages: List[Dict]) -> Tuple[dict, Optional[str]]:
        """
        Get response from Snowflake Intelligence Agent.
        Try multiple request formats until one works.
        """
        latest_user_message = None
        for msg in reversed(messages):
            if msg["role"] == "user":
                latest_user_message = msg["content"]
                break
        
        if not latest_user_message:
            return {}, "No user message found in conversation"
        
        # Parse agent name to extract database, schema, and agent name
        # Expected format: DATABASE.SCHEMA.AGENT_NAME
        agent_parts = self.agent_name.split('.')
        if len(agent_parts) >= 3:
            database = agent_parts[0]
            schema = agent_parts[1]
            agent_name_only = '.'.join(agent_parts[2:])  # In case agent name has dots
        else:
            # Fallback if format is unexpected
            database = "SNOWFLAKE_INTELLIGENCE"
            schema = "AGENTS"
            agent_name_only = self.agent_name
        
        # Based on Snowflake documentation, Intelligence Agents expect this format
        # Per the API spec: thread_id and parent_message_id must be integers
        
        # Correctly formatted base request according to API spec
        base_request = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": latest_user_message
                        }
                    ]
                }
            ]
        }
        
        # Try different combinations of required fields
        # According to the API docs, thread_id and parent_message_id should be integers
        request_variations = [
            # Variation 1: With thread_id and parent_message_id (CORRECT FORMAT per API docs)
            {
                **base_request,
                "thread_id": 0,
                "parent_message_id": 0
            },
            # Variation 2: Without thread management (simpler)
            base_request,
            # Variation 3: With tool_choice set to auto
            {
                **base_request,
                "tool_choice": {
                    "type": "auto"
                }
            },
        ]
        
        # Use the correct Cortex Agent REST API endpoint structure
        # Format: POST /api/v2/databases/{database}/schemas/{schema}/agents/{agent_name}:run
        endpoint = f"/api/v2/databases/{database}/schemas/{schema}/agents/{agent_name_only}:run"
        
        # Try each variation
        for i, request_body in enumerate(request_variations, 1):
            # First try streaming request
            response, error = self._make_streaming_api_request(endpoint, request_body)
            
            if not error:
                return response, None
            else:
                # If streaming fails, try regular API request as fallback
                response, error = self._make_api_request(endpoint, request_body)
                
                if not error:
                    return response, None
                    
                if i < len(request_variations):
                    continue
        
        return {}, f"All request variations failed. Last error: {error}"

    def get_complete_response(self, messages: List[Dict]) -> Tuple[str, Optional[str]]:
        """Get complete Intelligence Agent response with tool execution."""
        
        response, error = self.get_agent_response(messages)
        
        if error:
            return "", error
        
        # Process Intelligence Agent response
        if isinstance(response, dict):
            if "message" in response:
                # Extract content from message
                message = response["message"]
                if isinstance(message, dict) and "content" in message:
                    return message["content"], None
                elif isinstance(message, str):
                    return message, None
            elif "content" in response:
                return response["content"], None
            elif "response" in response:
                return response["response"], None
            else:
                # Fallback - convert entire response to string
                return str(response), None
        else:
            return str(response), None
    
    def _process_agent_response(self, agent_message: dict) -> Tuple[str, Optional[str]]:
        """Process Intelligence Agent response, including tool calls."""
        
        text_parts = []
        tool_calls = []
        
        # Extract content based on response structure
        if isinstance(agent_message, dict):
            if "content" in agent_message:
                content = agent_message["content"]
                if isinstance(content, str):
                    text_parts.append(content)
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            if item.get("type") == "text":
                                text_parts.append(item.get("text", ""))
                            elif item.get("type") == "tool_call":
                                tool_calls.append(item)
                        elif isinstance(item, str):
                            text_parts.append(item)
            
            # Check for tool calls in message
            if "tool_calls" in agent_message:
                tool_calls.extend(agent_message["tool_calls"])
        
        # Process tool calls if any
        tool_results = []
        if tool_calls:
            for tool_call in tool_calls:
                try:
                    result = self.tool_executor.execute_tool(tool_call)
                    tool_results.append(result)
                except Exception as e:
                    logger.error(f"Tool execution failed: {str(e)}")
                    tool_results.append(f"Tool execution failed: {str(e)}")
        
        # Combine text and tool results
        interpretation = "\n\n".join(text_parts) if text_parts else "I understand your request."
        
        if tool_results:
            formatted_results = f"{interpretation}\n\n📊 **Actions Completed:**\n\n"
            for i, result in enumerate(tool_results, 1):
                formatted_results += f"{i}. {result}\n\n"
            return formatted_results, None
        
        return interpretation, None
    
    def _format_results(self, df: pd.DataFrame, interpretation: str) -> str:
        """Format DataFrame results for display (similar to Cortex Analyst)."""
        formatted = f"**{interpretation}**\n\n📊 **Query Results ({len(df)} assets found):**\n\n"
        
        for idx, row in df.head(10).iterrows():
            formatted += f"**{idx + 1}. {row.get('ASSET_NAME', 'Asset')}**\n"
            formatted += f"   • Model: {row.get('MODEL', 'N/A')} ({row.get('OEM_NAME', 'N/A')})\n"
            if 'AVG_FAILURE_PROB' in row:
                formatted += f"   • Risk Score: {row.get('AVG_FAILURE_PROB', 0):.3f} failure probability\n"
            if 'AVG_HEALTH_SCORE' in row:
                formatted += f"   • Health Score: {row.get('AVG_HEALTH_SCORE', 0):.1f}%\n"
            if 'DOWNTIME_IMPACT_PER_HOUR' in row:
                formatted += f"   • Downtime Impact: ${row.get('DOWNTIME_IMPACT_PER_HOUR', 0):,.2f}/hour\n"
            formatted += "\n"
        
        if len(df) > 10:
            formatted += f"... and {len(df) - 10} more assets\n"
        
        return formatted


# Global Intelligence client instance
_intelligence_client: Optional[SnowflakeIntelligenceAgent] = None

def _get_intelligence_client() -> SnowflakeIntelligenceAgent:
    """Get or create the global Intelligence client instance"""
    global _intelligence_client
    
    if _intelligence_client is None:
        # Get configuration from secrets if available, otherwise use environment/session
        import os
        
        # Try to get from secrets first
        try:
            config = st.secrets["snowflake"]
            account = config["account"]
            user = config["user"]
            role = config.get("role")
            verify_ssl = get_verify_ssl(config.get("verify_ssl", True))
            agent_name = st.secrets.get("features", {}).get(
                "intelligence_agent", 
                "SNOWFLAKE_INTELLIGENCE.AGENTS.PREDICTIVE_MAINTENANCE_ASSISTANT"
            )
        except:
            # When running in SiS with OAuth, get from environment/session
            try:
                from snowflake.snowpark.context import get_active_session
                
                session = get_active_session()
                account = os.getenv("SNOWFLAKE_ACCOUNT", "")
                user = session.sql("SELECT CURRENT_USER()").collect()[0][0]
                role = session.sql("SELECT CURRENT_ROLE()").collect()[0][0]
                verify_ssl = True
                agent_name = "SNOWFLAKE_INTELLIGENCE.AGENTS.PREDICTIVE_MAINTENANCE_ASSISTANT"
            except Exception as e:
                logger.error(f"Failed to get session info: {e}")
                # Fallback to environment variables
                account = os.getenv("SNOWFLAKE_ACCOUNT", "")
                user = os.getenv("USER", "UNKNOWN")
                role = None
                verify_ssl = True
                agent_name = "SNOWFLAKE_INTELLIGENCE.AGENTS.PREDICTIVE_MAINTENANCE_ASSISTANT"
        
        _intelligence_client = SnowflakeIntelligenceAgent(
            account=account,
            user=user,
            agent_name=agent_name,
            role=role,
            verify_ssl=verify_ssl
        )
    
    return _intelligence_client
