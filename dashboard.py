
# dashboard.py
# Makkal Kural AI - Streamlit complaint management UI

import os
import inspect
from datetime import datetime

import pandas as pd
import streamlit as st

from database import get_all_complaints, save_complaint, update_status

try:
    import hashlib
    from voice_ai import process_complaint_audio, confirmation_audio
except ImportError:
    transcribe_audio_bytes = None


# =========================================================
# BACKGROUND + COMMON UI
# =========================================================

VILLAGE_BACKGROUND = (
    "https://images.unsplash.com/photo-1500382017468-9049fed747ef"
    "?auto=format&fit=crop&w=1920&q=85"
)

def apply_app_style():
    st.markdown(
        f"""
        <style>
        .stApp {{
            background:
                linear-gradient(
                    rgba(7, 35, 23, 0.58),
                    rgba(7, 35, 23, 0.66)
                ),
                url("{VILLAGE_BACKGROUND}");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
        }}

        [data-testid="stHeader"] {{
            background: rgba(8, 30, 25, 0.35);
        }}

        [data-testid="stSidebar"] {{
            background: rgba(9, 35, 29, 0.92);
        }}

        h1, h2, h3, p, label,
        [data-testid="stMarkdownContainer"] {{
            color: white;
        }}

        [data-testid="stVerticalBlockBorderWrapper"] {{
            background: rgba(12, 32, 43, 0.78);
            border: 1px solid rgba(255,255,255,0.16);
            border-radius: 16px;
        }}

        .stTextInput input,
        .stTextArea textarea {{
            background-color: rgba(255,255,255,0.96);
            color: #17212b;
            border-radius: 8px;
        }}

        [data-baseweb="select"] {{
            background-color: rgba(255,255,255,0.96);
            border-radius: 8px;
        }}

        .stButton > button,
        .stFormSubmitButton > button {{
            background-color: #0759a6;
            color: white;
            border: none;
            border-radius: 10px;
            min-height: 42px;
            font-weight: 600;
        }}

        .stButton > button:hover,
        .stFormSubmitButton > button:hover {{
            background-color: #0877ce;
            color: white;
            border: 1px solid white;
        }}

        .app-subtitle {{
            color: #f0f7f2;
            font-size: 1.05rem;
        }}

        .status-pill {{
            display: inline-block;
            padding: 5px 12px;
            border-radius: 20px;
            font-weight: 600;
            color: white;
        }}

        .stDataFrame {{
            background: rgba(255,255,255,0.96);
            border-radius: 10px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_heading(title, subtitle=""):
    st.title(title)
    if subtitle:
        st.markdown(
            f'<p class="app-subtitle">{subtitle}</p>',
            unsafe_allow_html=True,
        )


def load_complaints():
    """Load complaints from the existing database module."""
    try:
        data = get_all_complaints()
        if data is None:
            return pd.DataFrame()
        if isinstance(data, pd.DataFrame):
            return data.copy()
        return pd.DataFrame(data)
    except Exception as exc:
        st.error(f"Could not load complaints: {exc}")
        return pd.DataFrame()


def normalise_columns(df):
    """Handle common naming variations without changing the database."""
    if df.empty:
        return df

    aliases = {
        "tracking_id": ["tracking_id", "trackingid", "complaint_id"],
        "complaint_text": [
            "complaint_text", "complaint", "description", "text"
        ],
        "location": ["location", "address", "place"],
        "category": ["category", "complaint_category"],
        "status": ["status", "complaint_status"],
        "submitted_at": [
            "submitted_at", "created_at", "date", "submitted_on"
        ],
        "latitude": ["latitude", "lat"],
        "longitude": ["longitude", "lon", "lng"],
    }

    rename = {}
    existing = {str(c).lower(): c for c in df.columns}

    for standard, options in aliases.items():
        if standard not in df.columns:
            for option in options:
                if option in existing:
                    rename[existing[option]] = standard
                    break

    return df.rename(columns=rename)


def call_save_complaint(description, location, category, latitude, longitude):
    """
    Adapt to common save_complaint parameter names.
    If your database function has a different signature, adjust this helper.
    """
    try:
        signature = inspect.signature(save_complaint)
        params = signature.parameters

        values = {
            "complaint_text": description,
            "complaint": description,
            "description": description,
            "text": description,
            "location": location,
            "category": category,
            "latitude": latitude,
            "longitude": longitude,
            "lat": latitude,
            "lon": longitude,
            "lng": longitude,
        }

        kwargs = {
            name: values[name]
            for name, param in params.items()
            if name in values
            and param.kind
            not in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            )
        }

        required = [
            name for name, param in params.items()
            if param.default is inspect.Parameter.empty
            and param.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        ]

        if all(name in kwargs for name in required):
            return save_complaint(**kwargs)

        # Fallback for a positional database function.
        return save_complaint(
            description, location, category, latitude, longitude
        )

    except Exception:
        raise


# =========================================================
# 1. SUBMIT COMPLAINT + VOICE INPUT
# =========================================================

def render_submit(show_title=True):
    apply_app_style()

    if show_title:
        page_heading(
            "Submit Your Complaint",
            "Share your issue with us. We'll make sure it reaches the right authorities.",
        )

    with st.container(border=True):
        st.subheader("Complaint Details")

        st.markdown("**Complaint Description**")

       audio = st.audio_input("🎙️ Speak Your Complaint")

if audio is not None:
    audio_bytes = audio.getvalue()
    audio_id = hashlib.sha256(audio_bytes).hexdigest()

    if st.session_state.get("processed_voice_id") != audio_id:
        try:
            with st.spinner("Recognizing and translating your voice..."):
                result = process_complaint_audio(audio_bytes)

            if result:
                st.session_state["complaint_description"] = result["english"]
                st.session_state["voice_language"] = result["language"]
                st.session_state["processed_voice_id"] = audio_id

                st.success("Voice converted successfully!")
                st.rerun()
            else:
                st.warning("Could not recognize speech. Please try again.")

        except Exception as exc:
            st.error(f"Voice processing failed: {exc}")

        if audio is not None:
            if st.button("Convert Voice to Text", key="transcribe_voice"):
                if transcribe_audio_bytes is None:
                    st.error(
                        "Voice transcription is unavailable. "
                        "Please check voice_ai.py."
                    )
                else:
                    try:
                        with st.spinner("Converting voice to text..."):
                            transcript = transcribe_audio_bytes(audio.getvalue())

                        if transcript:
                            st.session_state["voice_complaint_text"] = str(
                                transcript
                            )
                            st.success("Voice converted to text.")
                        else:
                            st.warning("No text was detected. Please try again.")
                    except Exception as exc:
                        st.error(f"Voice transcription failed: {exc}")

       description = st.text_area(
    "Type your complaint here...",
    height=140,
    key="complaint_description",
    placeholder="Describe the issue you are facing...",
)

        categories = [
            "Roads & Infrastructure",
            "Water Supply",
            "Sanitation",
            "Electricity",
            "Public Safety",
            "Healthcare",
            "Education",
            "Other",
        ]

        category = st.selectbox(
            "Category *",
            categories,
            index=None,
            placeholder="Select a category",
        )

        location = st.text_input(
            "Location *",
            placeholder="Village name, street, or landmark",
        )

        col1, col2 = st.columns(2)

        with col1:
            latitude_text = st.text_input(
                "Latitude (Optional)",
                placeholder="e.g. 11.1234",
            )

        with col2:
            longitude_text = st.text_input(
                "Longitude (Optional)",
                placeholder="e.g. 78.1234",
            )

        st.caption(
            "You can submit without coordinates. Add latitude and longitude "
            "if you want to place the complaint on the map."
        )

        submitted = st.button(
            "📨 Submit Complaint",
            use_container_width=True,
            key="submit_complaint_button",
        )

        if submitted:
            if not description.strip():
                st.error("Please enter or speak your complaint.")
                return

            if not category:
                st.error("Please select a category.")
                return

            if not location.strip():
                st.error("Please enter the complaint location.")
                return

            try:
                latitude = (
                    float(latitude_text.strip())
                    if latitude_text.strip()
                    else None
                )
                longitude = (
                    float(longitude_text.strip())
                    if longitude_text.strip()
                    else None
                )

                if latitude is not None and not -90 <= latitude <= 90:
                    st.error("Latitude must be between -90 and 90.")
                    return

                if longitude is not None and not -180 <= longitude <= 180:
                    st.error("Longitude must be between -180 and 180.")
                    return

                with st.spinner("Submitting your complaint..."):
                    result = call_save_complaint(
                        description.strip(),
                        location.strip(),
                        category,
                        latitude,
                        longitude,
                    )

               language = st.session_state.pop("processed_voice_id", None)

try:
    audio_bytes = confirmation_audio(language)

    st.audio(
        audio_bytes,
        format="audio/mp3",
        autoplay=True,
    )
except Exception:
    st.warning("Complaint saved, but audio confirmation is unavailable.")
                if isinstance(result, dict):
                    tracking_id = result.get("tracking_id")
                else:
                    tracking_id = getattr(result, "tracking_id", None)

                if tracking_id:
                    st.info(f"Your tracking ID: **{tracking_id}**")
                else:
                    st.info(
                        "Please keep your tracking ID if it is returned "
                        "by your database function."
                    )

                st.session_state.pop("voice_complaint_text", None)

            except ValueError:
                st.error("Please enter valid numeric latitude and longitude.")
            except Exception as exc:
                st.error(f"Could not submit the complaint: {exc}")


# =========================================================
# 2. CHECK COMPLAINT STATUS
# =========================================================

def render_tracking(show_title=True):
    apply_app_style()

    if show_title:
        page_heading(
            "Check Complaint Status",
            "Enter your tracking ID to view the current status of your complaint.",
        )

    with st.container(border=True):
        tracking_id = st.text_input(
            "Tracking ID *",
            placeholder="Enter your tracking ID",
            key="tracking_id_search",
        )

        check = st.button(
            "🔎 Check Status",
            use_container_width=True,
            key="check_tracking_status",
        )

    if check:
        if not tracking_id.strip():
            st.warning("Please enter your tracking ID.")
            return

        df = normalise_columns(load_complaints())

        if df.empty or "tracking_id" not in df.columns:
            st.error("No complaint records are available.")
            return

        matches = df[
            df["tracking_id"].astype(str).str.strip().str.casefold()
            == tracking_id.strip().casefold()
        ]

        if matches.empty:
            st.warning("No complaint was found for that tracking ID.")
            return

        complaint = matches.iloc[0]

        st.subheader("Complaint Details")

        fields = [
            ("Tracking ID", "tracking_id"),
            ("Complaint", "complaint_text"),
            ("Category", "category"),
            ("Location", "location"),
            ("Submitted On", "submitted_at"),
            ("Status", "status"),
        ]

        for label, column in fields:
            value = complaint.get(column, "Not available")
            if pd.isna(value):
                value = "Not available"
            st.write(f"**{label}:** {value}")


# =========================================================
# 3. PASSWORD-ONLY PAGE + ALL COMPLAINTS
# =========================================================

def render_admin(show_title=True):
    apply_app_style()

    # Set ADMIN_PASSWORD in your hosting environment.
    expected_password = os.getenv("ADMIN_PASSWORD", "")

    if not st.session_state.get("complaints_access_granted", False):
        st.markdown(
            "<div style='text-align:center'>"
            "<h1>🔒 Enter Password</h1>"
            "<p>Please enter your password to continue.</p>"
            "</div>",
            unsafe_allow_html=True,
        )

        with st.form("complaints_password_form"):
            password = st.text_input(
                "Password",
                type="password",
                placeholder="Enter your password",
            )
            login = st.form_submit_button(
                "Continue",
                use_container_width=True,
            )

        if login:
            if not expected_password:
                st.error(
                    "Admin password is not configured. "
                    "Set the ADMIN_PASSWORD environment variable."
                )
            elif password == expected_password:
                st.session_state["complaints_access_granted"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")

        return

    render_public(show_title=show_title)


# =========================================================
# 4. ALL COMPLAINTS + MAP + FILTERS + LIST
# =========================================================

def render_public(show_title=True):
    apply_app_style()

    if show_title:
        page_heading(
            "All Complaints",
            "View reported complaints and their locations on the map.",
        )

    if st.button("🔄 Refresh Complaints", key="refresh_complaints"):
        st.rerun()

    df = normalise_columns(load_complaints())

    if df.empty:
        st.info("No complaints have been submitted yet.")
        return

    for col in [
        "tracking_id", "complaint_text", "location", "category",
        "status", "submitted_at", "latitude", "longitude",
    ]:
        if col not in df.columns:
            df[col] = None

    # Search and filters
    c1, c2, c3 = st.columns([2, 1, 1])

    with c1:
        search = st.text_input(
            "Search",
            placeholder="Search tracking ID, complaint, or location...",
        )

    with c2:
        category_options = ["All Categories"] + sorted(
            df["category"].dropna().astype(str).unique().tolist()
        )
        selected_category = st.selectbox("Category", category_options)

    with c3:
        status_options = ["All Status"] + sorted(
            df["status"].dropna().astype(str).unique().tolist()
        )
        selected_status = st.selectbox("Status", status_options)

    filtered = df.copy()

    if search.strip():
        search_columns = [
            c for c in ["tracking_id", "complaint_text", "location", "category"]
            if c in filtered.columns
        ]

        mask = pd.Series(False, index=filtered.index)
        for column in search_columns:
            mask |= filtered[column].fillna("").astype(str).str.contains(
                search.strip(), case=False, regex=False
            )
        filtered = filtered[mask]

    if selected_category != "All Categories":
        filtered = filtered[
            filtered["category"].astype(str) == selected_category
        ]

    if selected_status != "All Status":
        filtered = filtered[
            filtered["status"].astype(str) == selected_status
        ]

    st.caption(f"Showing {len(filtered)} complaint(s)")

    map_col, list_col = st.columns([1.05, 1.35])

    # Map panel
    with map_col:
        with st.container(border=True):
            st.subheader("📍 Map View")

            map_df = filtered.copy()
            map_df["latitude"] = pd.to_numeric(
                map_df["latitude"], errors="coerce"
            )
            map_df["longitude"] = pd.to_numeric(
                map_df["longitude"], errors="coerce"
            )

            map_df = map_df.dropna(subset=["latitude", "longitude"])

            if not map_df.empty:
                map_points = map_df.rename(
                    columns={"latitude": "lat", "longitude": "lon"}
                )[["lat", "lon"]]

                st.map(map_points, use_container_width=True)
            else:
                st.info(
                    "No map coordinates are available for these complaints. "
                    "Coordinates must be saved with a complaint to show its pin."
                )

            st.markdown("**Status legend**")
            st.markdown("🔴 Pending")
            st.markdown("🟠 In Progress")
            st.markdown("🟢 Resolved")

    # Complaints list panel
    with list_col:
        with st.container(border=True):
            st.subheader("📋 Complaints List")

            display_columns = [
                c for c in [
                    "tracking_id", "location", "category",
                    "status", "submitted_at",
                ]
                if c in filtered.columns
            ]

            display_df = filtered[display_columns].copy()

            display_df = display_df.rename(
                columns={
                    "tracking_id": "Tracking ID",
                    "location": "Location",
                    "category": "Category",
                    "status": "Status",
                    "submitted_at": "Submitted On",
                }
            )

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
            )

    # Status update controls
    st.divider()
    st.subheader("Update Complaint Status")

    if "tracking_id" not in filtered.columns or filtered.empty:
        st.info("No matching complaints to update.")
        return

    available_ids = filtered["tracking_id"].dropna().astype(str).tolist()

    if not available_ids:
        st.info("No tracking IDs are available.")
        return

    with st.form("update_complaint_status_form"):
        chosen_id = st.selectbox("Select Tracking ID", available_ids)
        new_status = st.selectbox(
            "New Status",
            ["Pending", "In Progress", "Resolved"],
        )
        update_clicked = st.form_submit_button("Update Status")

    if update_clicked:
        try:
            # Assumes update_status(tracking_id, status).
            update_status(chosen_id, new_status)
            st.success("Complaint status updated.")
            st.rerun()
        except Exception as exc:
            st.error(f"Could not update status: {exc}")


# =========================================================
# OPTIONAL ALIASES FOR EXISTING APP ROUTING
# =========================================================

def render_home(show_title=True):
    apply_app_style()
    if show_title:
        page_heading(
            "Makkal Kural AI",
            "A simple way to report local issues and track complaints.",
        )
    st.write("Use the app navigation to submit a complaint or check its status.")


def render_dashboard(show_title=True):
    # No separate analytics dashboard; show the All Complaints page instead.
    render_public(show_title=show_title)
