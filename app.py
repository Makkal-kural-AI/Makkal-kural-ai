"""
Makkal Kural AI — Main Streamlit Entrypoint (app.py)
-----------------------------------------------------
Routes user navigation between:
- Home (Hero banner & quick actions)
- Submit Complaint (Interactive map picker & form)
- Tracking (Lookup by tracking ID)
- All Complaints (Public grievances list & map)
- Admin Dashboard (6-digit PIN verification & analytics)
"""

import streamlit as st
from dashboard import (
    render_admin,
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


# Custom styling for background imagery, headers, and navigation
st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(rgba(4,18,37,.64), rgba(4,18,37,.78)), 
                    url('https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=1920&q=85');
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }
    [data-testid='stHeader'] { background: transparent; }
    [data-testid='stMainBlockContainer'] { max-width: 1250px; padding-top: 1.4rem; }
    .brand {
        font-size: clamp(25px, 3vw, 40px);
        font-weight: 900;
        color: white;
        text-shadow: 0 2px 8px #000;
    }
    .hero {
        text-align: center;
        padding: 35px 0 20px;
        color: white;
    }
    .hero h1 {
        font-size: clamp(38px, 6vw, 72px);
        font-weight: 900;
        color: white;
    }
    .hero p {
        font-size: clamp(18px, 2vw, 25px);
        color: white;
    }
    .stButton>button {
        min-height: 48px;
        border-radius: 12px;
        font-weight: 800;
        background: #073e70;
        color: white;
        border: 1px solid #c5e4ff;
    }
    .stButton>button:hover {
        background: #0877ce;
        color: white;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Top Navigation Bar
brand, nav = st.columns([2, 5], vertical_alignment="center")
with brand:
    st.markdown('<div class="brand">📢 Makkal Kural AI</div>', unsafe_allow_html=True)

with nav:
    cols = st.columns(5)
    nav_items = [
        ("Home", "Home"),
        ("Submit", "Submit Complaint"),
        ("Track", "Tracking"),
        ("Complaints", "All Complaints"),
        ("Admin", "Admin Dashboard"),
    ]
    for col, (label, page_name) in zip(cols, nav_items):
        with col:
            if st.button(label, use_container_width=True, key=f"nav_{page_name}"):
                go(page_name)

# Page Routing Logic
if st.session_state.page == "Home":
    st.markdown(
        """
        <div class="hero">
            <h1>உங்கள் குரல், உங்கள் ஊர்</h1>
            <h1>Your Voice, Your Village</h1>
            <p>Report local problems. Track progress. Build better communities.</p>
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
    "<hr><p style='text-align:center;color:white'>Makkal Kural AI · Your voice matters</p>",
    unsafe_allow_html=True,
)
