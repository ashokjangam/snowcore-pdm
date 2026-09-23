"""
Enhanced UI Components for the Predictive Maintenance Assistant

This module provides improved UI components for better user experience,
including suggested questions, message formatting, and conversation controls.
"""

import streamlit as st
from typing import List, Dict, Optional, Callable
import json
from datetime import datetime


# ==================================================================================================
# SUGGESTED QUESTIONS COMPONENT
# ==================================================================================================

SUGGESTED_QUESTIONS = {
    "Quick Insights": [
        "What are the top 5 assets at highest risk?",
        "Show me today's OEE performance",
        "Which assets need maintenance this week?",
        "What's the current average health score?"
    ],
    "Maintenance Operations": [
        "Create a work order for critical assets",
        "Schedule preventive maintenance for high-risk equipment",
        "Show recent maintenance history",
        "Calculate downtime risk for next 30 days"
    ],
    "Financial Analysis": [
        "Show maintenance cost breakdown by type",
        "What's our cost avoidance from predictive maintenance?",
        "Calculate potential production at risk",
        "Compare planned vs unplanned maintenance costs"
    ],
    "Operational Metrics": [
        "Compare plant OEE performance",
        "Show failure prediction trends",
        "Asset health score distribution",
        "Which production lines have the lowest availability?"
    ]
}


def render_suggested_questions(
    on_click_callback: Callable[[str], None],
    page_context: Optional[str] = None,
    show_categories: bool = True
) -> None:
    """
    Render suggested questions as clickable chips/buttons.
    
    Args:
        on_click_callback: Function to call when a question is clicked
        page_context: Current page context to show relevant suggestions
        show_categories: Whether to show category headers
    """
    
    # Filter suggestions based on page context if provided
    if page_context:
        suggestions = get_contextual_suggestions(page_context)
    else:
        suggestions = SUGGESTED_QUESTIONS
    
    st.markdown("### 💡 Suggested Questions")
    
    for category, questions in suggestions.items():
        if show_categories:
            st.markdown(f"**{category}**")
        
        # Create columns for button layout
        cols = st.columns(2)
        for i, question in enumerate(questions):
            with cols[i % 2]:
                if st.button(
                    question,
                    key=f"suggest_{category}_{i}",
                    use_container_width=True
                ):
                    on_click_callback(question)


def get_contextual_suggestions(page_context: str) -> Dict[str, List[str]]:
    """
    Get contextual suggestions based on current page.
    
    Args:
        page_context: The current page (e.g., "Executive Summary", "OEE Drill-Down")
        
    Returns:
        Dictionary of categorized suggestions relevant to the page
    """
    page_suggestions = {
        "Executive Summary": {
            "Overview": [
                "Summarize enterprise-wide OEE performance",
                "What are the biggest risks to production today?",
                "Show me cost avoidance from predictive maintenance"
            ]
        },
        "OEE Drill-Down": {
            "OEE Analysis": [
                "Which assets have OEE below 85%?",
                "Compare OEE across production lines",
                "What's driving availability losses this week?"
            ]
        },
        "Financial Risk Drill-Down": {
            "Financial": [
                "Calculate total downtime risk exposure",
                "Show assets with highest financial impact",
                "Compare maintenance costs vs downtime costs"
            ]
        },
        "Asset Detail": {
            "Asset Operations": [
                "Show maintenance history for this asset",
                "When is next maintenance scheduled?",
                "Create a work order for this asset"
            ]
        }
    }
    
    return page_suggestions.get(page_context, SUGGESTED_QUESTIONS)


# ==================================================================================================
# MESSAGE RENDERING COMPONENTS
# ==================================================================================================

MESSAGE_TYPES = {
    "welcome": {"icon": "👋", "bg_color": "#E8F4F9", "border_color": "#0084C7"},
    "user": {"icon": "💬", "bg_color": "#FFFFFF", "border_color": "#E0E0E0"},
    "assistant": {"icon": "🤖", "bg_color": "#F0F7FF", "border_color": "#4A90E2"},
    "data": {"icon": "📊", "bg_color": "#F0FFF0", "border_color": "#4CAF50"},
    "action": {"icon": "⚙️", "bg_color": "#FFF4E6", "border_color": "#FF9800"},
    "error": {"icon": "⚠️", "bg_color": "#FFE5E5", "border_color": "#F44336"},
    "system": {"icon": "ℹ️", "bg_color": "#F5F5F5", "border_color": "#9E9E9E"}
}


def render_message_with_actions(
    content: str,
    role: str,
    message_id: str,
    message_type: str = "assistant",
    show_actions: bool = True,
    metadata: Optional[Dict] = None
) -> None:
    """
    Render a message with enhanced styling and action buttons.
    
    Args:
        content: The message content
        role: The message role (user, assistant, etc.)
        message_id: Unique identifier for the message
        message_type: Type of message for styling
        show_actions: Whether to show action buttons
        metadata: Additional metadata (timestamp, backend used, etc.)
    """
    
    msg_style = MESSAGE_TYPES.get(message_type, MESSAGE_TYPES["assistant"])
    
    # Custom CSS for message styling
    st.markdown(f"""
        <div style="
            background-color: {msg_style['bg_color']};
            border-left: 4px solid {msg_style['border_color']};
            padding: 15px;
            border-radius: 8px;
            margin: 10px 0;
        ">
            <div style="display: flex; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 24px; margin-right: 10px;">{msg_style['icon']}</span>
                <strong>{role.title()}</strong>
                {f'<span style="color: #666; font-size: 12px; margin-left: 10px;">{metadata.get("timestamp", "")}</span>' if metadata else ''}
            </div>
            <div style="margin-left: 34px;">
                {content}
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # Action buttons
    if show_actions and role == "assistant":
        cols = st.columns([1, 1, 1, 1, 8])
        
        with cols[0]:
            if st.button("📋", key=f"copy_{message_id}", help="Copy to clipboard"):
                st.session_state[f"clipboard_{message_id}"] = content
                st.toast("Copied to clipboard!")
        
        with cols[1]:
            if st.button("🔄", key=f"rerun_{message_id}", help="Regenerate response"):
                return "rerun"
        
        with cols[2]:
            if st.button("👍", key=f"like_{message_id}", help="This was helpful"):
                log_feedback(message_id, "positive")
                st.toast("Thank you for your feedback!")
        
        with cols[3]:
            if st.button("👎", key=f"dislike_{message_id}", help="This needs improvement"):
                log_feedback(message_id, "negative")
                st.toast("Thank you for your feedback!")


def render_streaming_indicator(text: str = "Thinking") -> None:
    """
    Render a streaming/thinking indicator.
    
    Args:
        text: Text to display in the indicator
    """
    st.markdown(f"""
        <div style="
            display: flex;
            align-items: center;
            padding: 10px;
            color: #666;
        ">
            <div class="loading-dots" style="margin-right: 10px;">
                <span>•</span><span>•</span><span>•</span>
            </div>
            <em>{text}...</em>
        </div>
        <style>
            @keyframes blink {{
                0%, 20% {{ opacity: 0.2; }}
                40% {{ opacity: 1; }}
                60%, 100% {{ opacity: 0.2; }}
            }}
            .loading-dots span {{
                animation: blink 1.4s infinite;
                font-size: 24px;
                margin: 0 2px;
            }}
            .loading-dots span:nth-child(2) {{
                animation-delay: 0.2s;
            }}
            .loading-dots span:nth-child(3) {{
                animation-delay: 0.4s;
            }}
        </style>
    """, unsafe_allow_html=True)


# ==================================================================================================
# CONVERSATION CONTROLS
# ==================================================================================================

def render_conversation_controls(
    on_clear: Callable[[], None],
    on_export: Callable[[], None],
    on_settings: Optional[Callable[[], None]] = None,
    show_message_count: bool = True,
    message_count: int = 0
) -> None:
    """
    Render conversation control buttons in the header.
    
    Args:
        on_clear: Callback for clear conversation
        on_export: Callback for export conversation
        on_settings: Optional callback for settings
        show_message_count: Whether to show message count
        message_count: Number of messages in conversation
    """
    
    cols = st.columns([4, 1, 1, 1] if on_settings else [5, 1, 1])
    
    with cols[0]:
        if show_message_count and message_count > 0:
            st.caption(f"💬 {message_count} messages in conversation")
    
    with cols[-3]:
        if st.button("📤", key="export_conv", help="Export conversation"):
            on_export()
    
    with cols[-2]:
        if st.button("🗑️", key="clear_conv", help="Clear conversation"):
            if confirm_clear_conversation():
                on_clear()
    
    if on_settings:
        with cols[-1]:
            if st.button("⚙️", key="settings", help="Settings"):
                on_settings()


def confirm_clear_conversation() -> bool:
    """
    Show confirmation dialog before clearing conversation.
    
    Returns:
        True if user confirms, False otherwise
    """
    return st.checkbox(
        "Confirm clear conversation",
        key="confirm_clear",
        help="Check this box and click clear again to confirm"
    )


def export_conversation_to_markdown(messages: List[Dict]) -> str:
    """
    Export conversation to markdown format.
    
    Args:
        messages: List of conversation messages
        
    Returns:
        Markdown formatted conversation
    """
    markdown = "# Conversation Export\n\n"
    markdown += f"*Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n"
    markdown += "---\n\n"
    
    for i, msg in enumerate(messages, 1):
        role = msg['role'].title()
        content = msg['content']
        timestamp = msg.get('timestamp', '')
        
        markdown += f"## Message {i} - {role}\n\n"
        if timestamp:
            markdown += f"*{timestamp}*\n\n"
        markdown += f"{content}\n\n"
        markdown += "---\n\n"
    
    return markdown


def export_conversation_to_json(messages: List[Dict]) -> str:
    """
    Export conversation to JSON format.
    
    Args:
        messages: List of conversation messages
        
    Returns:
        JSON formatted conversation
    """
    export_data = {
        "export_timestamp": datetime.now().isoformat(),
        "message_count": len(messages),
        "messages": messages
    }
    
    return json.dumps(export_data, indent=2)


# ==================================================================================================
# FEEDBACK COLLECTION
# ==================================================================================================

def render_feedback_form(message_id: str) -> None:
    """
    Render detailed feedback form for a message.
    
    Args:
        message_id: ID of the message to provide feedback for
    """
    with st.expander("📝 Provide detailed feedback"):
        rating = st.radio(
            "How helpful was this response?",
            ["Very helpful", "Somewhat helpful", "Not helpful"],
            key=f"rating_{message_id}"
        )
        
        feedback_text = st.text_area(
            "What could be improved?",
            key=f"feedback_{message_id}",
            placeholder="Optional: Share your thoughts on how we can improve..."
        )
        
        if st.button("Submit Feedback", key=f"submit_fb_{message_id}"):
            log_detailed_feedback(message_id, rating, feedback_text)
            st.success("Thank you for your detailed feedback!")


def log_feedback(message_id: str, rating: str) -> None:
    """
    Log simple feedback (thumbs up/down).
    
    Args:
        message_id: ID of the message
        rating: 'positive' or 'negative'
    """
    # In production, this would log to Snowflake
    feedback_data = {
        "message_id": message_id,
        "rating": rating,
        "timestamp": datetime.now().isoformat()
    }
    
    # Store in session state for now
    if "feedback_log" not in st.session_state:
        st.session_state.feedback_log = []
    st.session_state.feedback_log.append(feedback_data)
    
    print(f"📊 Feedback logged: {feedback_data}")


def log_detailed_feedback(message_id: str, rating: str, feedback_text: str) -> None:
    """
    Log detailed feedback with text.
    
    Args:
        message_id: ID of the message
        rating: Rating level
        feedback_text: User's detailed feedback
    """
    feedback_data = {
        "message_id": message_id,
        "rating": rating,
        "feedback_text": feedback_text,
        "timestamp": datetime.now().isoformat()
    }
    
    # Store in session state for now
    if "feedback_log" not in st.session_state:
        st.session_state.feedback_log = []
    st.session_state.feedback_log.append(feedback_data)
    
    print(f"📊 Detailed feedback logged: {feedback_data}")


# ==================================================================================================
# RESPONSE TYPE DETECTION
# ==================================================================================================

def detect_response_type(content: str) -> str:
    """
    Detect the type of response to apply appropriate styling.
    
    Args:
        content: The response content
        
    Returns:
        Message type string
    """
    content_lower = content.lower()
    
    if any(word in content_lower for word in ["error", "failed", "unable to"]):
        return "error"
    elif any(word in content_lower for word in ["created", "scheduled", "completed", "work order"]):
        return "action"
    elif "query results" in content_lower or "📊" in content:
        return "data"
    else:
        return "assistant"


# ==================================================================================================
# LAYOUT UTILITIES
# ==================================================================================================

def get_layout_config(mode: str = "standard") -> Dict:
    """
    Get layout configuration for different widget modes.
    
    Args:
        mode: Layout mode ('compact', 'standard', 'expanded')
        
    Returns:
        Dictionary with layout configuration
    """
    configs = {
        "compact": {
            "ratio": [3.5, 1],
            "height": 400,
            "show_categories": False,
            "max_suggestions": 4
        },
        "standard": {
            "ratio": [2.5, 1],
            "height": 600,
            "show_categories": True,
            "max_suggestions": 8
        },
        "expanded": {
            "ratio": [1.5, 1],
            "height": 800,
            "show_categories": True,
            "max_suggestions": 12
        }
    }
    
    return configs.get(mode, configs["standard"])


def render_widget_mode_selector() -> str:
    """
    Render widget mode selector.
    
    Returns:
        Selected mode
    """
    mode = st.radio(
        "Widget Size:",
        ["Compact", "Standard", "Expanded"],
        index=1,
        horizontal=True,
        key="widget_mode"
    )
    
    return mode.lower()

