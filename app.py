"""
Makkal Kural AI — Main Entry Point
Calls render_submit(), render_tracking(), render_public(), render_admin(),
and render_notifications_banner() from dashboard.py.
"""

import streamlit as st
from dashboard import (
    render_admin,
    render_notifications_banner,
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


# Custom UI CSS
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

    /* Mobile layout:
       Row 1: Home | Submit (side-by-side)
       Row 2: Track | All Complaints (side-by-side)
       Row 3: Admin (full width below)
    */
    @media (max-width: 768px) {
        [data-testid="stMainBlockContainer"] > div > div > [data-testid="stHorizontalBlock"]:first-of-type,
        [data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"]:first-of-type {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: wrap !important;
            gap: 8px !important;
            align-items: stretch !important;
        }
        [data-testid="stMainBlockContainer"] [data-testid="stHorizontalBlock"]:has(.mka-nav-btn):nth-of-type(1) > [data-testid="column"]:nth-child(-n+4) {
            flex: 0 0 calc(50% - 4px) !important;
            width: calc(50% - 4px) !important;
            max-width: calc(50% - 4px) !important;
            min-width: calc(50% - 4px) !important;
        }
        [data-testid="stMainBlockContainer"] [data-testid="stHorizontalBlock"]:has(.mka-nav-btn):nth-of-type(1) > [data-testid="column"]:nth-child(5) {
            flex: 0 0 100% !important;
            width: 100% !important;
            max-width: 100% !important;
            min-width: 100% !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Brand Header
st.markdown('<div class="brand">📢 Makkal Kural AI</div>', unsafe_allow_html=True)

# Header Navigation Bar
nav_items = [
    ("Home", "Home"),
    ("Submit", "Submit Complaint"),
    ("Track", "Tracking"),
    ("All Complaints", "All Complaints"),
    ("Admin", "Admin Dashboard"),
]

cols = st.columns(len(nav_items))
for idx, (col, (label, page_name)) in enumerate(zip(cols, nav_items)):
    with col:
        st.markdown(f'<span class="mka-nav-btn" data-nav="{idx}"></span>', unsafe_allow_html=True)
        if st.button(label, use_container_width=True, key=f"nav_{page_name}"):
            go(page_name)

# Page Router
if st.session_state.page == "Home":
    render_notifications_banner()

    st.markdown(
        """
        <div style="text-align: center; padding: 24px 0 14px; color: white;">
            <h1 style="font-size: clamp(36px, 6vw, 68px); font-weight: 900; margin-bottom: 6px;">உங்கள் குரல், உங்கள் ஊர்</h1>
            <h2 style="font-size: clamp(26px, 4vw, 44px); font-weight: 800; margin-top: 0;">Your Voice, Your Village</h2>
            <p style="font-size: clamp(16px, 2vw, 22px);">Report local problems. Track progress. Build better communities.</p>
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

st.markdown(
    "<hr><p style='text-align:center;color:white;'>Makkal Kural AI · Your voice matters</p>",
    unsafe_allow_html=True,
)
