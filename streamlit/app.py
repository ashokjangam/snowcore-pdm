import streamlit as st
from streamlit_option_menu import option_menu

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="SnowCore Industries Predictive Maintenance Dashboard",
    page_icon="🏭",
    layout="wide"
)

from views import executive_summary, fleet_operations, oee_drilldown, financial_risk, asset_detail, line_visualization
from utils.unified_assistant import build_unified_widget

# Load custom CSS
with open('style.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

st.title("🏭 SnowCore Industries Predictive Maintenance Dashboard")

# --- TWO-FRAGMENT ARCHITECTURE ---
# Fragment 1: Navigation + Pages - clicking menu only reruns this fragment
# Fragment 2: Chat - isolated from page interactions

# Create layout columns
main_col, chat_col = st.columns([2.5, 1])

# --- FRAGMENT 1: Navigation and Page Content ---
@st.fragment
def pages_fragment():
    # Navigation menu INSIDE the fragment
    selected_page = option_menu(
        menu_title=None,
        options=["Executive Summary", "Fleet Operations", "OEE Drill-Down", "Financial Risk", "Asset Detail", "Line Visualization"],
        icons=["building", "wrench-adjustable", "graph-down", "cash-coin", "search", "diagram-3"],
        menu_icon="cast",
        default_index=0,
        orientation="horizontal",
    )
    
    # Page router
    if selected_page == "Executive Summary":
        executive_summary.show_page()
    elif selected_page == "Fleet Operations":
        fleet_operations.show_page()
    elif selected_page == "OEE Drill-Down":
        oee_drilldown.show_page()
    elif selected_page == "Financial Risk":
        financial_risk.show_page()
    elif selected_page == "Asset Detail":
        asset_detail.show_page()
    elif selected_page == "Line Visualization":
        line_visualization.show_page()

# --- FRAGMENT 2: Intelligence Assistant ---
@st.fragment
def chat_fragment():
    build_unified_widget(
        title="Intelligence Assistant 🤖",
        semantic_model_path="SNOWCORE_INDUSTRIES.GOLD.SEMANTIC_VIEW_STAGE/SNOWCORE_INDUSTRIES_SV.yaml",
        initial_message="Hi! I'm your intelligent assistant. Ask me anything about your predictive maintenance data.",
        placeholder="Ask a question...",
        page_context="global",
        enable_suggested_questions=True,
        enable_conversation_controls=True
    )

# --- RENDER FRAGMENTS ---
with main_col:
    pages_fragment()

with chat_col:
    chat_fragment()
