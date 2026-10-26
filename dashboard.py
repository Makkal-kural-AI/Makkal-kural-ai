
import pandas as pd
import streamlit as st

from classifier import classify_complaint
from database import (
    get_all_complaints,
    init_db,
    save_complaint as save_to_database,
    update_status,
)
from voice_ai import get_voice_complaint

CATEGORIES = [
    "Garbage",
    "Drainage",
    "Water Supply",
    "Water Leakage",
    "Road Damage",
    "Street Light",
    "Electricity",
    "Public Safety",
    "Public Toilets",
    "Stray Animals",
    "Mosquitoes and Pests",
    "Other",
]

STATUSES = ["Pending", "In Progress", "Resolved"]


# ---------------- PAGE CONFIGURATION ----------------

st.set_page_config(
    page_title="Makkal Kural AI",
    page_icon="📢",
    layout="wide",
)


# ---------------- DATABASE ----------------

def initialize_database():
    init_db()


def get_complaints():
    return pd.DataFrame(get_all_complaints())


def save_complaint(complaint_text, location):
    category = classify_complaint(complaint_text)
    tracking_id, _ = save_to_database(
        complaint_text,
        category,
        location,
    )
    update_status(tracking_id, "Pending")

    return tracking_id, category


def change_status(tracking_id, new_status):
    return update_status(tracking_id, new_status)


initialize_database()


# ---------------- SESSION STATE ----------------

if "complaint_text" not in st.session_state:
    st.session_state["complaint_text"] = ""

if "voice_message" not in st.session_state:
    st.session_state["voice_message"] = ""


# ---------------- SIDEBAR ----------------

st.sidebar.title("📢 Makkal Kural AI")
st.sidebar.caption("Public Complaint Management")

page = st.sidebar.radio(
    "Navigation",
    [
        "Submit Complaint",
        "Admin Dashboard",
        "All Complaints",
        "Update Status",
    ],
)

st.sidebar.divider()
st.sidebar.caption("Helping communities report local problems.")


# ---------------- SUBMIT COMPLAINT ----------------

if page == "Submit Complaint":

    st.title("Submit a Complaint")
    st.write(
        "Report a public issue in your village or local area."
    )

    st.subheader("1. Enter your complaint")

    if st.button("🎤 Speak Your Complaint", use_container_width=False):
        with st.spinner(
            "Listening... Please speak in Tamil or English."
        ):
            voice_text = get_voice_complaint()

        if voice_text:
            st.session_state["complaint_text"] = voice_text
            st.session_state["voice_message"] = (
                "Voice complaint captured successfully."
            )
            st.rerun()
        else:
            st.session_state["voice_message"] = (
                "Voice was not detected. Please try again "
                "or type your complaint."
            )

    if st.session_state["voice_message"]:
        st.info(st.session_state["voice_message"])

    complaint_text = st.text_area(
        "Complaint details",
        key="complaint_text",
        placeholder=(
            "Example: Garbage has not been collected "
            "in our village for three days."
        ),
        height=130,
    )

    if complaint_text.strip():
        category = classify_complaint(complaint_text)
        st.success(f"Detected category: {category}")

    st.subheader("2. Enter your location")

    location = st.text_input(
        "Village / Area",
        placeholder="Example: Kovilpatti Village",
    )

    if st.button(
        "Submit Complaint",
        type="primary",
        use_container_width=True,
    ):
        if not complaint_text.strip():
            st.error("Please enter or speak your complaint.")

        elif not location.strip():
            st.error("Please enter your village or location.")

        else:
            try:
                tracking_id, category = save_complaint(
                    complaint_text.strip(),
                    location.strip(),
                )

                st.success("Complaint saved successfully!")

                st.subheader("Your Complaint Details")
                st.write(f"**Tracking ID:** {tracking_id}")
                st.write(f"**Category:** {category}")
                st.write("**Status:** Pending")

                st.info(
                    "Please save your tracking ID "
                    "to check your complaint later."
                )

                st.session_state["voice_message"] = ""
                st.rerun()

            except Exception as error:
                st.error(f"Could not save complaint: {error}")


# ---------------- ADMIN DASHBOARD ----------------

elif page == "Admin Dashboard":

    st.title("📊 Admin Dashboard")
    st.caption("Overview of reported public complaints")

    try:
        df = get_complaints()

        if df.empty:
            st.info(
                "No complaints submitted yet. "
                "New complaints will appear here."
            )

        else:
            total = len(df)
            pending = int((df["status"] == "Pending").sum())
            progress = int((df["status"] == "In Progress").sum())
            resolved = int((df["status"] == "Resolved").sum())

            col1, col2, col3, col4 = st.columns(4)

            col1.metric("Total Complaints", total)
            col2.metric("Pending", pending)
            col3.metric("In Progress", progress)
            col4.metric("Resolved", resolved)

            st.divider()

            left, right = st.columns(2)

            with left:
                st.subheader("Complaints by Category")
                category_counts = df["category"].value_counts()
                st.bar_chart(category_counts)

            with right:
                st.subheader("Complaints by Status")
                status_counts = (
                    df["status"]
                    .value_counts()
                    .reindex(STATUSES, fill_value=0)
                )
                st.bar_chart(status_counts)

            st.subheader("Recent Complaints")

            display_columns = [
                "tracking_id",
                "complaint_text",
                "location",
                "category",
                "status",
            ]

            st.dataframe(
                df[display_columns].head(10),
                use_container_width=True,
                hide_index=True,
            )

    except Exception as error:
        st.error(f"Could not load dashboard data: {error}")


# ---------------- ALL COMPLAINTS ----------------

elif page == "All Complaints":

    st.title("📋 All Complaints")

    try:
        df = get_complaints()

        if df.empty:
            st.info("No complaints available.")

        else:
            col1, col2 = st.columns(2)

            with col1:
                selected_category = st.selectbox(
                    "Filter by category",
                    ["All"] + CATEGORIES,
                )

            with col2:
                selected_status = st.selectbox(
                    "Filter by status",
                    ["All"] + STATUSES,
                )

            search = st.text_input(
                "Search by tracking ID or location"
            )

            filtered = df.copy()

            if selected_category != "All":
                filtered = filtered[
                    filtered["category"] == selected_category
                ]

            if selected_status != "All":
                filtered = filtered[
                    filtered["status"] == selected_status
                ]

            if search.strip():
                query = search.strip()

                match = (
                    filtered["tracking_id"].str.contains(
                        query, case=False, na=False
                    )
                    | filtered["location"].str.contains(
                        query, case=False, na=False
                    )
                )

                filtered = filtered[match]

            st.write(f"Complaints found: {len(filtered)}")

            st.dataframe(
                filtered,
                use_container_width=True,
                hide_index=True,
            )

    except Exception as error:
        st.error(f"Could not load complaints: {error}")


# ---------------- UPDATE STATUS ----------------

elif page == "Update Status":

    st.title("🔄 Update Complaint Status")

    try:
        df = get_complaints()

        if df.empty:
            st.info("There are no complaints to update.")

        else:
            tracking_id = st.selectbox(
                "Select complaint tracking ID",
                df["tracking_id"].tolist(),
            )

            complaint = df[
                df["tracking_id"] == tracking_id
            ].iloc[0]

            st.subheader("Complaint Details")
            st.write(f"**Complaint:** {complaint['complaint_text']}")
            st.write(f"**Location:** {complaint['location']}")
            st.write(f"**Category:** {complaint['category']}")
            st.write(f"**Current status:** {complaint['status']}")

            current_status = complaint["status"]

            status_index = (
                STATUSES.index(current_status)
                if current_status in STATUSES
                else 0
            )

            new_status = st.selectbox(
                "Choose new status",
                STATUSES,
                index=status_index,
            )

            if st.button("Save Status", type="primary"):
                change_status(tracking_id, new_status)
                st.success("Complaint status updated successfully!")
                st.rerun()

    except Exception as error:
        st.error(f"Could not update status: {error}")
