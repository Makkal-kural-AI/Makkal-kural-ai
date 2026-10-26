
import streamlit as st


def render_submit(show_title=True):
    if show_title:
        st.title("📝 Submit Your Complaint")

    st.markdown("### 🎙️ Speak Your Complaint")

    # Voice transcription integration
    # Uses the existing voice_ai.py
    from voice_ai import transcribe_audio_bytes

    audio = st.audio_input("Record your complaint")

    if audio is not None:
        if st.button("Convert Speech to Text", key="convert_voice"):
            with st.spinner("Transcribing audio..."):
                try:
                    text = transcribe_audio_bytes(audio.getvalue())
                    if text:
                        st.session_state["complaint_text"] = text
                        st.success("Speech converted. Please review it.")
                    else:
                        st.warning("Speech not recognized. Try again.")
                except Exception as e:
                    st.error(f"Transcription failed: {e}")

    with st.form("complaint_form"):
        description = st.text_area(
            "Complaint Description",
            key="complaint_text",
        )
        category = st.selectbox(
            "Category",
            ["Roads", "Water", "Electricity",
             "Sanitation", "Streetlight", "Other"],
        )
        location = st.text_input("Location")

        submitted = st.form_submit_button("Submit Complaint")

    if submitted:
        if description.strip() and location.strip():
            st.info(
                "Connect your existing save_complaint() function "
                "here to save the complaint."
            )
        else:
            st.error("Enter the complaint and location.")


def render_tracking(show_title=True):
    if show_title:
        st.title("🔎 Check Complaint Status")

    tracking_id = st.text_input("Enter Tracking ID")

    if st.button("Check Status", key="check_tracking"):
        st.info(
            "Connect your existing get_all_complaints() "
            "function here to look up this tracking ID."
        )


def render_admin(show_title=True):
    if show_title:
        st.title("📊 Admin Dashboard")

    st.subheader("Complaint Overview")

    c1, c2, c3 = st.columns(3)
    c1.metric("Pending", "—")
    c2.metric("In Progress", "—")
    c3.metric("Resolved", "—")

    st.info(
        "Connect your existing database functions here "
        "to display live statistics, charts and complaints."
    )

    if st.button("View All Complaints", key="dashboard_all"):
        st.session_state["page"] = "All Complaints"
        st.rerun()


def render_public(show_title=True):
    if show_title:
        st.title("📋 All Complaints")

    st.text_input("Search complaints")
    st.selectbox(
        "Category",
        ["All", "Roads", "Water", "Electricity", "Other"],
    )
    st.selectbox(
        "Status",
        ["All", "Pending", "In Progress", "Resolved"],
    )

    st.info(
        "Connect your existing database and map code here "
        "to display complaint pins and the complaints table."
    )
