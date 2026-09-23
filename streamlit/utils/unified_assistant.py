import streamlit as st
import logging
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from .cortex_analyst import SnowflakeCortexAnalyst, _get_cortex_client
from .snowflake_intelligence import SnowflakeIntelligenceAgent, _get_intelligence_client
from .conversation_manager import get_conversation_manager
from .assistant_ui_components import SUGGESTED_QUESTIONS, get_contextual_suggestions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UnifiedAssistant:
    """
    Unified interface that routes between Snowflake Intelligence Agent (primary)
    and Cortex Analyst (fallback/rollback) based on configuration.
    """
    
    def __init__(self):
        self.use_intelligence = self._get_feature_flag()
        self.fallback_to_cortex = self._get_fallback_flag()
        self.intelligence_client = None
        self.cortex_client = None
    
    def _get_feature_flag(self) -> bool:
        """Check if Intelligence should be used (config-driven)"""
        try:
            if hasattr(st, 'secrets'):
                return st.secrets.get("features", {}).get("use_intelligence", True)
            return True
        except Exception:
            return True
    
    def _get_fallback_flag(self) -> bool:
        """Check if automatic fallback to Cortex is enabled"""
        try:
            if hasattr(st, 'secrets'):
                return st.secrets.get("features", {}).get("fallback_to_cortex", True)
            return True
        except Exception:
            return True
    
    def get_complete_response(self, messages: List[Dict], semantic_model_path: str) -> Tuple[str, Optional[str], Optional[List]]:
        """Get complete response from the appropriate backend."""
        if self.use_intelligence:
            try:
                response, error = self._get_intelligence_response(messages)
                return response, error, None
            except Exception as e:
                if self.fallback_to_cortex:
                    try:
                        response, error, api_content = self._get_cortex_response(messages, semantic_model_path)
                        if not error:
                            fallback_note = "\n\n*Note: Response provided by Cortex Analyst*"
                            response = response + fallback_note
                        return response, error, api_content
                    except Exception as cortex_error:
                        return "", f"🚨 Both backends failed: {str(e)}, {str(cortex_error)}", None
                else:
                    return "", f"🚨 Intelligence Agent failed: {str(e)}", None
        else:
            return self._get_cortex_response(messages, semantic_model_path)
    
    def _get_intelligence_response(self, messages: List[Dict]) -> Tuple[str, Optional[str]]:
        if self.intelligence_client is None:
            self.intelligence_client = _get_intelligence_client()
        return self.intelligence_client.get_complete_response(messages)
    
    def _get_cortex_response(self, messages: List[Dict], semantic_model_path: str) -> Tuple[str, Optional[str], Optional[List]]:
        if self.cortex_client is None:
            self.cortex_client = _get_cortex_client()
        return self.cortex_client.get_complete_response(messages, semantic_model_path)


# Global unified client instance
_unified_client: Optional[UnifiedAssistant] = None


def _get_unified_client() -> UnifiedAssistant:
    global _unified_client
    if _unified_client is None:
        _unified_client = UnifiedAssistant()
    return _unified_client


def build_unified_widget(
    title: str = "SnowCore Industries Assistant 🤖",
    semantic_model_path: str = "SNOWCORE_INDUSTRIES.GOLD.SEMANTIC_VIEW_STAGE/SNOWCORE_INDUSTRIES_SV.yaml",
    initial_message: str = "Hi! I'm your intelligent manufacturing assistant. I can analyze data and help with maintenance operations.",
    placeholder: str = "e.g., 'What assets have the highest risk?' or 'Create a work order for pump maintenance'",
    page_context: Optional[str] = None,
    enable_suggested_questions: bool = True,
    enable_conversation_controls: bool = True
):
    """
    Unified chat widget designed to work inside a @st.fragment.
    Uses a two-phase approach: Phase 1 stores prompt, Phase 2 processes it.
    """
    
    # Initialize client and conversation manager
    try:
        client = _get_unified_client()
        conv_manager = get_conversation_manager(storage_backend="session")
        conversation_id = conv_manager.get_conversation_id(page_context or "default")
    except Exception as e:
        st.error(f"Failed to initialize assistant: {e}")
        return

    messages_key = f"unified_messages_{semantic_model_path.replace('/', '_').replace('.', '_')}"
    processing_key = f"processing_{messages_key}"
    
    if messages_key not in st.session_state:
        st.session_state[messages_key] = [{
            "role": "assistant",
            "content": initial_message,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }]
    
    # Header with title and controls
    if enable_conversation_controls:
        header_col1, header_col2, header_col3 = st.columns([10, 1, 1])
    else:
        header_col1 = st.container()
    
    with header_col1:
        st.subheader(title)
    
    if enable_conversation_controls:
        with header_col2:
            if st.button("📤", key="export_conv", help="Export conversation"):
                export_data = conv_manager.export_conversation(conversation_id, format="markdown")
                st.download_button(
                    label="Download",
                    data=export_data,
                    file_name=f"conversation_{conversation_id}.md",
                    mime="text/markdown",
                    key="download_md"
                )
        
        with header_col3:
            if "confirm_clear" not in st.session_state:
                st.session_state["confirm_clear"] = False
            
            if st.session_state["confirm_clear"]:
                if st.button("✓", key="confirm_clear_btn", help="Confirm clear"):
                    st.session_state[messages_key] = [{
                        "role": "assistant",
                        "content": initial_message,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }]
                    if processing_key in st.session_state:
                        del st.session_state[processing_key]
                    conv_manager.clear_conversation(conversation_id)
                    st.session_state["confirm_clear"] = False
                    st.rerun()
            else:
                if st.button("🗑️", key="clear_conv", help="Clear conversation"):
                    st.session_state["confirm_clear"] = True
                    st.rerun()
    
    st.divider()
    
    # Suggested questions section
    if enable_suggested_questions and len(st.session_state[messages_key]) <= 2:
        with st.expander("💡 Need inspiration? Try these questions:", expanded=False):
            suggestions = get_contextual_suggestions(page_context) if page_context else SUGGESTED_QUESTIONS
            
            for category, questions in suggestions.items():
                st.markdown(f"**{category}**")
                cols = st.columns(2)
                for i, question in enumerate(questions[:4]):
                    with cols[i % 2]:
                        if st.button(question, key=f"sq_{category}_{i}", use_container_width=True):
                            # Add user message and set processing flag
                            st.session_state[messages_key].append({
                                "role": "user",
                                "content": question,
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            })
                            conv_manager.save_message(conversation_id=conversation_id, role="user", content=question)
                            st.session_state[processing_key] = True
                            st.rerun()
        st.divider()
    
    # Check if we need to process a pending request
    is_processing = st.session_state.get(processing_key, False)
    
    # Display conversation history (all messages except during processing show the last user msg)
    messages_to_show = st.session_state[messages_key]
    for i, message in enumerate(messages_to_show):
        with st.chat_message(message["role"]):
            st.markdown(message["content"], unsafe_allow_html=True)
            if message["role"] == "assistant" and i > 0:
                _render_feedback_buttons(f"msg_{i}")
    
    # If processing, show spinner and get response
    if is_processing:
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                start_time = time.time()
                
                # Prepare messages for API
                api_messages = []
                for msg in st.session_state[messages_key]:
                    if msg["role"] in ["user", "assistant"]:
                        api_messages.append(msg)
                
                try:
                    assistant_response, error_msg, api_content = client.get_complete_response(
                        api_messages,
                        semantic_model_path
                    )
                    
                    response_time_ms = int((time.time() - start_time) * 1000)
                    
                    if error_msg:
                        assistant_response = error_msg
                    elif not assistant_response or assistant_response.strip() == "":
                        assistant_response = "I apologize, but I didn't receive a proper response. Please try again."
                    
                except Exception as e:
                    assistant_response = f"🚨 Unexpected error: {str(e)}"
                    response_time_ms = int((time.time() - start_time) * 1000)
            
            # Display response
            st.markdown(assistant_response, unsafe_allow_html=True)
        
        # Add to history
        assistant_msg = {
            "role": "assistant",
            "content": assistant_response,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "backend_used": "Intelligence Agent" if client.use_intelligence else "Cortex Analyst",
            "response_time_ms": response_time_ms
        }
        st.session_state[messages_key].append(assistant_msg)
        conv_manager.save_message(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_response,
            backend_used=assistant_msg["backend_used"],
            response_time_ms=response_time_ms
        )
        
        # Clear processing flag and rerun to clean up display
        del st.session_state[processing_key]
        st.rerun()
    
    # Chat input - only show when not processing
    if not is_processing:
        prompt = st.chat_input(placeholder)
        
        if prompt:
            # Add user message and set processing flag
            st.session_state[messages_key].append({
                "role": "user",
                "content": prompt,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            conv_manager.save_message(conversation_id=conversation_id, role="user", content=prompt)
            st.session_state[processing_key] = True
            st.rerun()


def _render_feedback_buttons(message_id: str):
    """Render simple feedback buttons for assistant messages."""
    cols = st.columns([1, 1, 10])
    
    with cols[0]:
        if st.button("👍", key=f"like_{message_id}", help="Helpful"):
            _log_feedback(message_id, "positive")
            st.toast("Thanks for your feedback!")
    
    with cols[1]:
        if st.button("👎", key=f"dislike_{message_id}", help="Not helpful"):
            _log_feedback(message_id, "negative")
            st.toast("Thanks! We'll improve.")


def _log_feedback(message_id: str, rating: str):
    """Log feedback for continuous improvement."""
    if "feedback_log" not in st.session_state:
        st.session_state["feedback_log"] = []
    
    st.session_state["feedback_log"].append({
        "message_id": message_id,
        "rating": rating,
        "timestamp": datetime.now().isoformat()
    })


# Legacy compatibility
def build_analyst_widget(*args, **kwargs):
    return build_unified_widget(*args, **kwargs)
