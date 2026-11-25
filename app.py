"""
Makkal Kural AI — Main Entry Point
Calls render_submit(), render_tracking(), render_public(), render_admin(),
and render_notifications_banner() from dashboard.py.
"""

import streamlit as st
import streamlit.components.v1 as components
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


def _is_mobile_viewport() -> bool:
    """Detect mobile viewport width via query param / JS bridge without breaking desktop."""
    if "mka_is_mobile" not in st.session_state:
        st.session_state.mka_is_mobile = False

    # Check if JS reported screen width in URL query params
    qp_w = st.query_params.get("mka_w")
    if qp_w is not None:
        try:
            st.session_state.mka_is_mobile = int(qp_w) <= 768
        except ValueError:
            pass

    components.html(
        """
        <script>
        (function() {
            const w = window.innerWidth;
            const url = new URL(window.parent.location.href);
            const current = url.searchParams.get("mka_w");
            if (String(w) !== current) {
                url.searchParams.set("mka_w", String(w));
                window.parent.history.replaceState({}, "", url.toString());
                if ((w <= 768) !== (Number(current || 9999) <= 768)) {
                    window.parent.location.reload();
                }
            }
        })();
        </script>
        """,
        height=0,
    )
    return bool(st.session_state.mka_is_mobile)


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

is_mobile = _is_mobile_viewport()

if is_mobile:
    r1_c1, r1_c2 = st.columns(2)
    with r1_c1:
        if st.button("Home", use_container_width=True, key="nav_m_Home"):
            go("Home")
    with r1_c2:
        if st.button("Submit", use_container_width=True, key="nav_m_Submit Complaint"):
            go("Submit Complaint")

    r2_c1, r2_c2 = st.columns(2)
    with r2_c1:
        if st.button("Track", use_container_width=True, key="nav_m_Tracking"):
            go("Tracking")
    with r2_c2:
        if st.button("All Complaints", use_container_width=True, key="nav_m_All Complaints"):
            go("All Complaints")

    if st.button("Admin", use_container_width=True, key="nav_m_Admin Dashboard"):
        go("Admin Dashboard")
else:
    cols = st.columns(len(nav_items))
    for col, (label, page_name) in zip(cols, nav_items):
        with col:
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
