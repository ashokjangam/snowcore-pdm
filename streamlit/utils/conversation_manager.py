"""
Conversation Management for Predictive Maintenance Assistant

This module handles conversation persistence, context management,
and conversation analytics.
"""

import streamlit as st
import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import logging
from .data_loader import run_query

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConversationManager:
    """
    Manages conversation state, persistence, and context.
    Provides features like conversation history, summarization, and analytics.
    """
    
    def __init__(self, storage_backend: str = "session"):
        """
        Initialize conversation manager.
        
        Args:
            storage_backend: Where to store conversations ('session', 'snowflake')
        """
        self.storage_backend = storage_backend
        self._initialize_storage()
    
    def _initialize_storage(self):
        """Initialize storage backend."""
        if self.storage_backend == "session":
            if "conversations" not in st.session_state:
                st.session_state["conversations"] = {}
        elif self.storage_backend == "snowflake":
            # Ensure conversation tables exist
            self._ensure_conversation_tables()
    
    def _ensure_conversation_tables(self):
        """Ensure Snowflake tables for conversation storage exist."""
        try:
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS SNOWCORE_INDUSTRIES.ANALYTICS.CONVERSATION_HISTORY (
                conversation_id VARCHAR(255),
                message_id VARCHAR(255),
                user_id VARCHAR(255),
                timestamp TIMESTAMP_NTZ,
                role VARCHAR(50),
                content VARCHAR,
                backend_used VARCHAR(50),
                response_time_ms INTEGER,
                metadata VARIANT
            );
            """
            run_query(create_table_sql)
            logger.info("✅ Conversation tables verified")
        except Exception as e:
            logger.warning(f"⚠️ Could not verify conversation tables: {e}")
    
    def get_conversation_id(self, context: str = "default") -> str:
        """
        Get or create a conversation ID for the current session.
        
        Args:
            context: Context identifier (e.g., page name)
            
        Returns:
            Conversation ID string
        """
        key = f"conversation_id_{context}"
        if key not in st.session_state:
            # Generate new conversation ID
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            user_id = self._get_user_id()
            st.session_state[key] = f"{user_id}_{context}_{timestamp}"
        
        return st.session_state[key]
    
    def _get_user_id(self) -> str:
        """Get current user ID from Streamlit user info or session."""
        try:
            # Try to get from Streamlit user info (if available)
            user_info = st.user
            return user_info.get("email", "anonymous")
        except:
            # Fallback to session-based ID
            if "user_id" not in st.session_state:
                import uuid
                st.session_state.user_id = str(uuid.uuid4())
            return st.session_state.user_id
    
    def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        backend_used: Optional[str] = None,
        response_time_ms: Optional[int] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Save a message to the conversation.
        
        Args:
            conversation_id: Conversation identifier
            role: Message role (user, assistant)
            content: Message content
            backend_used: Which backend generated the response
            response_time_ms: Response time in milliseconds
            metadata: Additional metadata
            
        Returns:
            Message ID
        """
        import uuid
        message_id = str(uuid.uuid4())
        
        message = {
            "message_id": message_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "backend_used": backend_used,
            "response_time_ms": response_time_ms,
            "metadata": metadata or {}
        }
        
        if self.storage_backend == "session":
            self._save_to_session(conversation_id, message)
        elif self.storage_backend == "snowflake":
            self._save_to_snowflake(conversation_id, message)
        
        return message_id
    
    def _save_to_session(self, conversation_id: str, message: Dict):
        """Save message to session state."""
        # Use dictionary key access instead of attribute access
        if "conversations" not in st.session_state:
            st.session_state["conversations"] = {}
        
        if conversation_id not in st.session_state["conversations"]:
            st.session_state["conversations"][conversation_id] = []
        
        st.session_state["conversations"][conversation_id].append(message)
    
    def _save_to_snowflake(self, conversation_id: str, message: Dict):
        """Save message to Snowflake."""
        try:
            insert_sql = f"""
            INSERT INTO SNOWCORE_INDUSTRIES.ANALYTICS.CONVERSATION_HISTORY (
                conversation_id,
                message_id,
                user_id,
                timestamp,
                role,
                content,
                backend_used,
                response_time_ms,
                metadata
            ) VALUES (
                '{conversation_id}',
                '{message["message_id"]}',
                '{self._get_user_id()}',
                '{message["timestamp"]}',
                '{message["role"]}',
                '{message["content"].replace("'", "''")}',
                '{message["backend_used"]}',
                {message["response_time_ms"] or "NULL"},
                PARSE_JSON('{json.dumps(message["metadata"])}')
            );
            """
            run_query(insert_sql)
            logger.info(f"✅ Saved message {message['message_id']} to Snowflake")
        except Exception as e:
            logger.error(f"❌ Failed to save message to Snowflake: {e}")
            # Fallback to session storage
            self._save_to_session(conversation_id, message)
    
    def get_conversation_history(
        self,
        conversation_id: str,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Get conversation history.
        
        Args:
            conversation_id: Conversation identifier
            limit: Maximum number of messages to return
            
        Returns:
            List of messages
        """
        if self.storage_backend == "session":
            # Ensure conversations dict exists
            if "conversations" not in st.session_state:
                st.session_state["conversations"] = {}
            messages = st.session_state["conversations"].get(conversation_id, [])
        else:
            messages = self._load_from_snowflake(conversation_id)
        
        if limit:
            return messages[-limit:]
        return messages
    
    def _load_from_snowflake(self, conversation_id: str) -> List[Dict]:
        """Load conversation from Snowflake."""
        try:
            query = f"""
            SELECT
                message_id,
                role,
                content,
                timestamp,
                backend_used,
                response_time_ms,
                metadata
            FROM SNOWCORE_INDUSTRIES.ANALYTICS.CONVERSATION_HISTORY
            WHERE conversation_id = '{conversation_id}'
            ORDER BY timestamp ASC;
            """
            df = run_query(query)
            
            messages = []
            for _, row in df.iterrows():
                messages.append({
                    "message_id": row["MESSAGE_ID"],
                    "role": row["ROLE"],
                    "content": row["CONTENT"],
                    "timestamp": row["TIMESTAMP"],
                    "backend_used": row["BACKEND_USED"],
                    "response_time_ms": row["RESPONSE_TIME_MS"],
                    "metadata": json.loads(row["METADATA"]) if row["METADATA"] else {}
                })
            
            return messages
        except Exception as e:
            logger.error(f"❌ Failed to load conversation from Snowflake: {e}")
            return []
    
    def clear_conversation(self, conversation_id: str):
        """
        Clear conversation history.
        
        Args:
            conversation_id: Conversation to clear
        """
        if self.storage_backend == "session":
            if "conversations" in st.session_state:
                if conversation_id in st.session_state["conversations"]:
                    del st.session_state["conversations"][conversation_id]
        else:
            # Don't actually delete from Snowflake (for audit purposes)
            # Just mark as cleared
            logger.info(f"Conversation {conversation_id} marked as cleared")
    
    def manage_context_window(
        self,
        messages: List[Dict],
        max_messages: int = 20,
        max_tokens: int = 8000
    ) -> List[Dict]:
        """
        Manage context window to prevent exceeding token limits.
        
        Strategy:
        1. Keep system/welcome messages (first 1-2)
        2. Keep recent messages for context
        3. Summarize older messages if needed
        
        Args:
            messages: List of conversation messages
            max_messages: Maximum number of messages to keep
            max_tokens: Maximum total tokens (rough estimate)
            
        Returns:
            Pruned message list
        """
        if len(messages) <= max_messages:
            return messages
        
        # Estimate token count (rough: ~4 chars per token)
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        estimated_tokens = total_chars / 4
        
        if estimated_tokens < max_tokens:
            return messages
        
        logger.info(f"⚠️ Context window management needed: {len(messages)} messages, ~{estimated_tokens:.0f} tokens")
        
        # Strategy: Keep first message + last N messages
        keep_last = min(15, max_messages - 1)
        
        # Keep first message (usually system/welcome)
        pruned_messages = [messages[0]]
        
        # Add summary of middle messages
        if len(messages) > keep_last + 1:
            middle_summary = self._summarize_messages(messages[1:-keep_last])
            pruned_messages.append({
                "role": "system",
                "content": f"[Previous conversation summary: {middle_summary}]"
            })
        
        # Add recent messages
        pruned_messages.extend(messages[-keep_last:])
        
        logger.info(f"✅ Context pruned to {len(pruned_messages)} messages")
        return pruned_messages
    
    def _summarize_messages(self, messages: List[Dict]) -> str:
        """
        Summarize a list of messages.
        
        Args:
            messages: Messages to summarize
            
        Returns:
            Summary string
        """
        # Simple summarization for now
        # In production, could use Cortex Complete for better summaries
        
        user_queries = [msg["content"] for msg in messages if msg["role"] == "user"]
        
        if len(user_queries) == 0:
            return "No significant conversation history"
        elif len(user_queries) <= 3:
            return "Previous questions: " + "; ".join(user_queries)
        else:
            return f"User asked {len(user_queries)} questions about asset health, maintenance, and OEE metrics"
    
    def export_conversation(
        self,
        conversation_id: str,
        format: str = "markdown"
    ) -> str:
        """
        Export conversation in specified format.
        
        Args:
            conversation_id: Conversation to export
            format: Export format ('markdown', 'json', 'pdf')
            
        Returns:
            Exported conversation string
        """
        messages = self.get_conversation_history(conversation_id)
        
        if format == "markdown":
            return self._export_as_markdown(messages, conversation_id)
        elif format == "json":
            return self._export_as_json(messages, conversation_id)
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def _export_as_markdown(self, messages: List[Dict], conversation_id: str) -> str:
        """Export conversation as Markdown."""
        md = f"# Conversation Export\n\n"
        md += f"**Conversation ID:** {conversation_id}\n\n"
        md += f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        md += f"**Total Messages:** {len(messages)}\n\n"
        md += "---\n\n"
        
        for i, msg in enumerate(messages, 1):
            role = msg['role'].title()
            content = msg['content']
            timestamp = msg.get('timestamp', '')
            backend = msg.get('backend_used', '')
            
            md += f"## Message {i}: {role}\n\n"
            if timestamp:
                md += f"*{timestamp}*"
            if backend:
                md += f" | *Backend: {backend}*"
            md += "\n\n"
            md += f"{content}\n\n"
            md += "---\n\n"
        
        return md
    
    def _export_as_json(self, messages: List[Dict], conversation_id: str) -> str:
        """Export conversation as JSON."""
        export_data = {
            "conversation_id": conversation_id,
            "export_timestamp": datetime.now().isoformat(),
            "message_count": len(messages),
            "messages": messages
        }
        return json.dumps(export_data, indent=2)
    
    def get_conversation_analytics(self, conversation_id: str) -> Dict:
        """
        Get analytics for a conversation.
        
        Args:
            conversation_id: Conversation to analyze
            
        Returns:
            Dictionary with analytics metrics
        """
        messages = self.get_conversation_history(conversation_id)
        
        user_messages = [m for m in messages if m["role"] == "user"]
        assistant_messages = [m for m in messages if m["role"] == "assistant"]
        
        # Calculate average response time
        response_times = [
            m.get("response_time_ms", 0) 
            for m in assistant_messages 
            if m.get("response_time_ms")
        ]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        # Count backend usage
        backends = {}
        for m in assistant_messages:
            backend = m.get("backend_used", "unknown")
            backends[backend] = backends.get(backend, 0) + 1
        
        return {
            "total_messages": len(messages),
            "user_queries": len(user_messages),
            "assistant_responses": len(assistant_messages),
            "avg_response_time_ms": avg_response_time,
            "backend_distribution": backends,
            "duration_minutes": self._calculate_duration(messages)
        }
    
    def _calculate_duration(self, messages: List[Dict]) -> float:
        """Calculate conversation duration in minutes."""
        if len(messages) < 2:
            return 0.0
        
        try:
            first_time = datetime.fromisoformat(messages[0]["timestamp"])
            last_time = datetime.fromisoformat(messages[-1]["timestamp"])
            duration = (last_time - first_time).total_seconds() / 60
            return round(duration, 2)
        except:
            return 0.0


# ==================================================================================================
# GLOBAL CONVERSATION MANAGER
# ==================================================================================================

_conversation_manager: Optional[ConversationManager] = None


def get_conversation_manager(storage_backend: str = "session") -> ConversationManager:
    """
    Get or create global conversation manager instance.
    
    Args:
        storage_backend: Storage backend ('session' or 'snowflake')
        
    Returns:
        ConversationManager instance
    """
    global _conversation_manager
    
    if _conversation_manager is None:
        _conversation_manager = ConversationManager(storage_backend=storage_backend)
    
    return _conversation_manager

