"""
Makkal Kural AI — Main Entry Point
"""

import streamlit as st
from dashboard import (
    render_admin,
    render_notifications_banner,
    render_notifications_page,
    render_public,
    render_submit,
    render_tracking,
)

st.set_page_config(
    page_title="Makkal Kural AI",
    page_icon="📢",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "page" not in st.session_state:
    st.session_state.page = "Home"


def go(page: str):
    st.session_state.page = page
    st.rerun()


st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(rgba(4,18,37,.68), rgba(4,18,37,.82)),
                    url('https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=1920&q=85');
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }
    [data-testid='stHeader'] { background: transparent; }
    [data-testid='stMainBlockContainer'] { max-width: 1250px; padding-top: 1.4rem; }
    .brand { font-size: clamp(25px, 3vw, 40px); font-weight: 900; color: white; text-shadow: 0 2px 8px #000; margin-bottom: 10px; }
    .stButton>button {
        min-height: 48px;
        border-radius: 12px;
        font-weight: 800;
        background: #073e70;
        color: white;
        border: 1px solid #c5e4ff;
    }
    .stButton>button:hover { background: #0877ce; color: white; }

    /* Mobile layout: Home|Submit, Track|All Complaints, Admin full-width, Notifications full-width */
    @media (max-width: 768px) {
        .mka-nav-row [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: 8px !important;
        }
        .mka-nav-row [data-testid="column"]:nth-child(1),
        .mka-nav-row [data-testid="column"]:nth-child(2),
        .mka-nav-row [data-testid="column"]:nth-child(3),
        .mka-nav-row [data-testid="column"]:nth-child(4) {
            flex: 0 0 calc(50% - 4px) !important;
            width: calc(50% - 4px) !important;
            min-width: calc(50% - 4px) !important;
        }
        .mka-nav-row [data-testid="column"]:nth-child(5),
        .mka-nav-row [data-testid="column"]:nth-child(6) {
            flex: 0 0 100% !important;
            width: 100% !important;
            min-width: 100% !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Header Navigation Bar
st.markdown('<div class="brand">📢 Makkal Kural AI</div>', unsafe_allow_html=True)

st.markdown('<div class="mka-nav-row">', unsafe_allow_html=True)
nav_items = [
    ("Home", "Home"),
    ("Submit", "Submit Complaint"),
    ("Track", "Tracking"),
    ("All Complaints", "All Complaints"),
    ("Admin", "Admin Dashboard"),
    ("Notifications", "Notifications"),
]
cols = st.columns(len(nav_items))
for col, (label, page_name) in zip(cols, nav_items):
    with col:
        if st.button(label, use_container_width=True, key=f"nav_{page_name}"):
            go(page_name)
st.markdown("</div>", unsafe_allow_html=True)

# Page Router
if st.session_state.page == "Home":
    render_notifications_banner()

    st.markdown(
        """
        <div style="text-align: center; padding: 28px 0 16px; color: white;">
            <h1 style="font-size: clamp(38px, 6vw, 72px); font-weight: 900;">உங்கள் குரல், உங்கள் ஊர்</h1>
            <h1 style="font-size: clamp(28px, 4vw, 50px); font-weight: 800;">Your Voice, Your Village</h1>
            <p style="font-size: clamp(18px, 2vw, 25px);">Report local problems. Track progress. Build better communities.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    a, b, c = st.columns(3)
    with a:
        if st.button("📝 Submit a complaint", use_container_width=True):
            go("Submit Complaint")
    with b:
        if st.button("🔎 Track a complaint", use_container_width=True):
            go("Tracking")
    with c:
        if st.button("🔐 Admin dashboard", use_container_width=True):
            go("Admin Dashboard")

elif st.session_state.page == "Submit Complaint":
    render_submit()

elif st.session_state.page == "Tracking":
    render_tracking()

elif st.session_state.page == "All Complaints":
    render_public()

elif st.session_state.page == "Admin Dashboard":
    render_admin()

elif st.session_state.page == "Notifications":
    render_notifications_page()

st.markdown(
    "<hr><p style='text-align:center;color:white;'>Makkal Kural AI · Your voice matters</p>",
    unsafe_allow_html=True,
)
