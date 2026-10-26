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
    initial_sidebar_state="collapsed"
)

# ---------------- SESSION STATE ----------------
if "page" not in st.session_state:
    st.session_state.page = "Home"


def go(page):
    st.session_state.page = page
    st.rerun()


# ---------------- DESIGN ----------------
st.markdown("""
<style>
.stApp {
    background:
        linear-gradient(rgba(5,16,43,.48), rgba(5,16,43,.62)),
        url("https://images.unsplash.com/photo-1500382017468-9049fed747ef");
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    color: white;
}

[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background: transparent !important;
}

[data-testid="stMainBlockContainer"] {
    max-width: 100% !important;
    padding: 1.2rem 3.2vw 2rem !important;
}

.header-brand {
    font-size: clamp(24px, 2.1vw, 35px);
    font-weight: 850;
    color: white;
    white-space: nowrap;
    text-shadow: 0 2px 8px #15243b;
}

.header-rule {
    height: 2px;
    background: rgba(255,255,255,.65);
    width: 100%;
    margin: 12px 0 22px;
}

.hero-wrap {
    text-align: center;
    padding-top: clamp(30px, 5vh, 70px);
}

.hero-title {
    font-size: clamp(46px, 5.3vw, 86px);
    font-weight: 900;
    line-height: 1.16;
    color: white;
    text-shadow: 0 4px 12px rgba(0,0,0,.65);
}

.hero-tag {
    font-size: clamp(25px, 2.5vw, 40px);
    font-weight: 800;
    margin-top: 28px;
    color: white;
    text-shadow: 0 3px 9px #15243b;
}

.hero-desc {
    font-size: clamp(19px, 1.65vw, 27px);
    font-weight: 550;
    line-height: 1.5;
    margin: 28px auto;
    color: white;
    text-shadow: 0 2px 8px #182234;
}

.footer {
    text-align: center;
    color: white;
    font-size: 17px;
    font-weight: 600;
    margin-top: 28px;
    text-shadow: 0 2px 7px black;
}

.stButton > button {
    width: 100%;
    color: white !important;
    background: rgba(10,31,60,.93) !important;
    border: 1.5px solid rgba(211,231,249,.8) !important;
    border-radius: 13px !important;
    font-weight: 800 !important;
    box-shadow: 0 4px 12px rgba(0,0,0,.18);
    transition: background .15s ease;
}

.stButton > button:hover {
    background: rgba(18,82,117,.97) !important;
    border-color: #52eadb !important;
}

.stButton > button p {
    color: white !important;
    font-size: inherit !important;
    font-weight: inherit !important;
}

.st-key-nav_home button,
.st-key-nav_tracking button,
.st-key-nav_status button,
.st-key-nav_about button {
    min-height: 53px !important;
    font-size: clamp(18px, 1.4vw, 27px) !important;
}

.st-key-card_submit button,
.st-key-card_check button,
.st-key-card_admin button,
.st-key-card_all button {
    min-height: 165px !important;
    font-size: clamp(23px, 2.2vw, 42px) !important;
    padding: 20px !important;
    background: rgba(10,31,60,.93) !important;
    border: 1.5px solid rgba(211,231,249,.8) !important;
}

.st-key-card_submit button:hover,
.st-key-card_check button:hover,
.st-key-card_admin button:hover,
.st-key-card_all button:hover {
    background: rgba(18,82,117,.97) !important;
    border-color: #52eadb !important;
}

.st-key-card_submit button p,
.st-key-card_check button p,
.st-key-card_admin button p,
.st-key-card_all button p {
    font-size: inherit !important;
    font-weight: 900 !important;
    text-align: center !important;
}

@media(max-width:760px) {
    [data-testid="stMainBlockContainer"] {
        padding: 1rem 4vw 2rem !important;
    }

    .header-brand {
        white-space: normal;
    }

    .hero-wrap {
        padding-top: 20px;
    }

    .hero-tag {
        margin-top: 16px;
    }

    .hero-desc {
        margin-top: 16px;
    }

    .st-key-card_submit button,
    .st-key-card_check button,
    .st-key-card_admin button,
    .st-key-card_all button {
        min-height: 112px !important;
    }
}
</style>
""", unsafe_allow_html=True)


# ---------------- HEADER / NAVIGATION ----------------
brand, spacer, navigation = st.columns(
    [3, 1, 5],
    gap="small",
    vertical_alignment="center"
)

with brand:
    st.markdown(
        '<div class="header-brand">📢 Makkal Kural AI</div>',
        unsafe_allow_html=True
    )

with navigation:
    n1, n2, n3, n4 = st.columns(4, gap="small")

    with n1:
        if st.button("Home", key="nav_home",
                     use_container_width=True):
            go("Home")

    with n2:
        if st.button("Tracking", key="nav_tracking",
                     use_container_width=True):
            go("Tracking")

    with n3:
        if st.button("Status", key="nav_status",
                     use_container_width=True):
            go("Status")

    with n4:
        if st.button("About", key="nav_about",
                     use_container_width=True):
            go("About")

st.markdown(
    '<div class="header-rule"></div>',
    unsafe_allow_html=True
)


# ---------------- HOME PAGE ----------------
if st.session_state.page == "Home":

    st.markdown("""
    <div class="hero-wrap">
        <div class="hero-title">📢 Makkal Kural AI</div>
        <div class="hero-tag">Your Voice, Your Village.</div>
        <div class="hero-desc">
            Report local issues easily through our
            community complaint management system.
        </div>
    </div>
    """, unsafe_allow_html=True)

    left, right = st.columns(2, gap="large")

    with left:
        if st.button(
            "📝 Submit Your Complaint",
            key="card_submit",
            use_container_width=True
        ):
            go("Submit Your Complaint")

        if st.button(
            "🛡️ Admin Dashboard",
            key="card_admin",
            use_container_width=True
        ):
            go("Admin Dashboard")

    with right:
        if st.button(
            "🔎 Check Status",
            key="card_check",
            use_container_width=True
        ):
            go("Status")

        if st.button(
            "📋 All Complaints",
            key="card_all",
            use_container_width=True
        ):
            go("All Complaints")


# ---------------- OTHER PAGES ----------------
else:
    st.markdown(
        f"""
        <div class="hero-wrap">
            <div class="hero-tag">{st.session_state.page}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.session_state.page == "Submit Your Complaint":
        render_submit(show_title=False)

    elif st.session_state.page == "Admin Dashboard":
        render_admin(show_title=False)

    elif st.session_state.page == "All Complaints":
        render_public(show_title=False)

    elif st.session_state.page in ("Tracking", "Status"):
        render_tracking(show_title=False)

    elif st.session_state.page == "About":
        st.write(
            "Makkal Kural AI helps communities report "
            "local problems through a complaint management system."
        )
        st.markdown(
            "[Open the live app](https://makkal-kural-ai.onrender.com)"
        )

    if st.button("← Back to Home", key="back_home"):
        go("Home")


# ---------------- FOOTER ----------------
st.markdown(
    '<div class="footer">'
    'Makkal Kural AI | Your voice matters 💙'
    '</div>',
    unsafe_allow_html=True
)
