
import streamlit as st
from database import save_complaint, get_complaint
from streamlit_mic_recorder import mic_recorder
import whisper
import os
import hashlib

st.set_page_config(
    page_title="Makkal Kural AI",
    page_icon="📢",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------- SESSION STATE ----------------
defaults = {
    "complaint_text": "",
    "selected_category": "",
    "citizen_name": "",
    "village_name": "",
    "city_name": "",
    "map_lat": 13.0827,
    "map_lon": 80.2707,
    "map_selected": False,
    "submitted_complaint": None,
    "current_page": "home",
    "tracking_search": "",
    "processed_audio_id": None,
    "whisper_model": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ---------------- DESIGN ----------------
st.markdown(
    """
    <style>
    .stApp {
        background:
            linear-gradient(rgba(5,16,43,0.48), rgba(5,16,43,0.62)),
            url("https://images.unsplash.com/photo-1500382017468-9049fed747ef");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
        color: white;
    }

    [data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stDecoration"] {
        background: transparent !important;
    }

    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stMainBlockContainer"] {
        background: transparent !important;
    }

    [data-testid="stMainBlockContainer"] {
        padding-top: 1.2rem !important;
        padding-bottom: 1rem !important;
        max-width: 1400px !important;
    }

    h1, h2, h3, h4, p, label, li,
    [data-testid="stMarkdownContainer"] {
        color: #FFFFFF;
    }

    .brand {
        font-size: 29px;
        font-weight: 800;
        color: white;
    }

    .tagline {
        color: #D9E6F5;
        font-size: 14px;
        margin-top: 3px;
    }

    .hero {
        font-size: clamp(32px, 4vw, 48px);
        line-height: 1.17;
        font-weight: 850;
        color: white;
        margin-top: 35px;
        margin-bottom: 14px;
    }

    .teal { color: #40E0D0; }

    .intro {
        font-size: 16px;
        line-height: 1.7;
        color: #E0EAF7;
        margin-bottom: 22px;
    }

    .section-heading {
        font-size: 23px;
        font-weight: 800;
        color: white;
        margin: 8px 0 12px 0;
    }

    .category-description {
        font-size: 14px;
        line-height: 1.5;
        color: #E1EAF5;
        margin: -2px 0 14px 3px;
    }

    .stTextInput input,
    .stTextArea textarea {
        background-color: rgba(8,27,55,0.94) !important;
        color: white !important;
        border: 1px solid #6F91B5 !important;
        border-radius: 9px !important;
        -webkit-text-fill-color: white !important;
    }

    .stTextInput input::placeholder,
    .stTextArea textarea::placeholder {
        color: #C5D3E3 !important;
        -webkit-text-fill-color: #C5D3E3 !important;
        opacity: 1 !important;
    }

    [data-testid="stWidgetLabel"] label,
    [data-testid="stWidgetLabel"] p {
        color: white !important;
        font-weight: 650 !important;
    }

    .stButton > button {
        min-height: 45px;
        border-radius: 10px;
        font-weight: 700;
        transition: 0.2s;
    }

    .stButton > button[kind="primary"] {
        background-color: #0D9488 !important;
        color: white !important;
        border: 1px solid #40E0D0 !important;
    }

    .stButton > button[kind="secondary"] {
        background-color: rgba(11,34,68,0.94) !important;
        color: white !important;
        border: 1px solid #6887AD !important;
    }

    .stButton > button:hover {
        border-color: #40E0D0 !important;
        color: white !important;
    }

    iframe { border-radius: 12px; }

    hr {
        border-color: rgba(207,224,244,0.55) !important;
    }

    [data-testid="stAlert"] {
        background-color: rgba(8,27,55,0.94);
    }

    .footer {
        text-align: center;
        font-size: 14px;
        color: #D8E5F3;
        padding: 15px 0 5px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------- HEADER / NAVIGATION ----------------
header_left, header_right = st.columns([1.5, 1.5])

with header_left:
    st.markdown(
        '<div class="brand">📢 Makkal Kural AI</div>'
        '<div class="tagline">Your Voice • Our Priority</div>',
        unsafe_allow_html=True,
    )

with header_right:
    n1, n2, n3 = st.columns(3)

    with n1:
        if st.button("Home", use_container_width=True):
            st.session_state.current_page = "home"
            st.session_state.submitted_complaint = None
            st.rerun()

    with n2:
        if st.button("Track Complaint", use_container_width=True):
            st.session_state.current_page = "track"
            st.session_state.submitted_complaint = None
            st.rerun()

    with n3:
        if st.button("About", use_container_width=True):
            st.session_state.current_page = "about"
            st.rerun()

st.divider()

# ---------------- CONFIRMATION PAGE ----------------
if st.session_state.submitted_complaint:
    result = st.session_state.submitted_complaint

    st.markdown(
        """
        <div style="text-align:center; padding:30px 10px;">
            <div style="font-size:60px;">✅</div>
            <h1>Complaint Submitted Successfully!</h1>
            <p>Your complaint has been saved successfully.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.success("Keep your Tracking ID safe for checking your complaint later.")

    st.markdown("### Your Complaint Details")
    st.markdown("**Tracking ID**")
    st.code(result["tracking_id"])

    c1, c2 = st.columns(2)

    with c1:
        st.write("**Category:**", result["category"])
        st.write("**Village / Area:**", result["village"])
        st.write("**City / District:**", result["district"])

    with c2:
        st.write("**Submitted on:**", result["created_at"])
        st.write("**Current status:**", result["status"])

    st.info("Your complaint is recorded with the status 'Submitted'.")

    if st.button("Submit Another Complaint", type="primary",
                 use_container_width=True):
        for key, value in {
            "complaint_text": "",
            "selected_category": "",
            "citizen_name": "",
            "village_name": "",
            "city_name": "",
            "map_lat": 13.0827,
            "map_lon": 80.2707,
            "map_selected": False,
            "submitted_complaint": None,
            "processed_audio_id": None,
            "current_page": "home",
        }.items():
            st.session_state[key] = value

        st.rerun()

    if st.button("Track This Complaint", use_container_width=True):
        st.session_state.tracking_search = result["tracking_id"]
        st.session_state.submitted_complaint = None
        st.session_state.current_page = "track"
        st.rerun()

    st.markdown(
        '<div class="footer">A cleaner village | A safer tomorrow</div>',
        unsafe_allow_html=True,
    )
    st.stop()


# ---------------- TRACK COMPLAINT PAGE ----------------
if st.session_state.current_page == "track":
    st.markdown(
        '<div class="section-heading">🔎 Track Your Complaint</div>',
        unsafe_allow_html=True,
    )

    st.write("Enter the Tracking ID you received after submitting your complaint.")

    tracking_id = st.text_input(
        "Tracking ID",
        key="tracking_search",
        placeholder="Example: MKAI-ABC1234567",
    )

    if st.button("Check Status", type="primary",
                 use_container_width=True):
        if not tracking_id.strip():
            st.warning("Please enter your Tracking ID.")
        else:
            try:
                found = get_complaint(tracking_id.strip())

                if found:
                    st.success("Complaint found.")
                    st.code(found["tracking_id"])
                    st.write("**Current status:**", found["status"])
                    st.write("**Category:**", found["category"])
                    st.write("**Complaint:**", found["description"])
                    st.write("**Village / Area:**", found["village"])
                    st.write(
                        "**City / District:**",
                        found.get("district") or "Not provided",
                    )
                    st.write("**Submitted on:**", found["created_at"])
                else:
                    st.error(
                        "No complaint found. Please check your Tracking ID."
                    )

            except Exception as e:
                st.error("We couldn't check the complaint right now.")
                st.caption(f"Database error: {e}")

    if st.button("Back to Home"):
        st.session_state.current_page = "home"
        st.rerun()

    st.markdown(
        '<div class="footer">A cleaner village | A safer tomorrow</div>',
        unsafe_allow_html=True,
    )
    st.stop()


# ---------------- ABOUT PAGE ----------------
if st.session_state.current_page == "about":
    st.markdown(
        '<div class="section-heading">ℹ️ About Makkal Kural AI</div>',
        unsafe_allow_html=True,
    )

    st.write(
        "Makkal Kural AI helps people report local community problems "
        "through text or voice. Users can select an issue category, "
        "provide the location, and receive a Tracking ID to check "
        "their complaint status."
    )

    if st.button("Back to Home", type="primary"):
        st.session_state.current_page = "home"
        st.rerun()

    st.markdown(
        '<div class="footer">A cleaner village | A safer tomorrow</div>',
        unsafe_allow_html=True,
    )
    st.stop()

# ---------------- HERO ----------------
st.markdown(
    """
    <div class="hero">
        Real People.<br>
        Real Problems.<br>
        <span class="teal">Real Change.</span>
    </div>
    <div class="intro">
        Help improve your village by reporting local problems.
        Speak or type your complaint, select an issue, and tell us
        where the problem is located.
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------- TWO-COLUMN CONTENT ----------------
left, right = st.columns([1.15, 1], gap="large")


# ================ LEFT: COMPLAINT FORM ================
with left:
    st.markdown(
        '<div class="section-heading">📝 Report a Complaint</div>',
        unsafe_allow_html=True,
    )

    st.caption("Click Start Speaking, explain the problem, then stop recording.")

    # Compact voice recorder
        # Wider recorder control
    voice_left, voice_center, voice_right = st.columns([1, 4, 1])

    with voice_center:
        audio_data = mic_recorder(
            start_prompt="🎙️ Start Speaking",
            stop_prompt="⏹️ Stop Recording",
            just_once=True,
            use_container_width=True,
            key="complaint_recorder",
        )


    # Transcribe each recording only once
    if audio_data and audio_data.get("bytes"):
        audio_bytes = audio_data["bytes"]
        audio_id = hashlib.sha256(audio_bytes).hexdigest()

        if audio_id != st.session_state.processed_audio_id:
            st.session_state.processed_audio_id = audio_id
            audio_filename = "complaint_recording.wav"

            try:
                with st.spinner("Converting your speech to text..."):
                    with open(audio_filename, "wb") as audio_file:
                        audio_file.write(audio_bytes)

                    if st.session_state.whisper_model is None:
                        st.session_state.whisper_model = whisper.load_model("base")

                    model = st.session_state.whisper_model

                    result = model.transcribe(
                        audio_filename,
                        task="transcribe",
                        fp16=False,
                        temperature=0,
                    )

                    text = result["text"].strip()

                    # Translate Tamil speech into English text
                    if result.get("language") == "ta" and text:
                        translated = model.transcribe(
                            audio_filename,
                            task="translate",
                            fp16=False,
                            temperature=0,
                        )
                        text = translated["text"].strip()

                    if text:
                        st.session_state.complaint_text = text
                        st.success("Speech converted! Check the text below.")
                    else:
                        st.warning("No clear speech detected. Please try again.")

            except Exception as error:
                st.error("Could not convert the recording. Please try again.")
                st.caption(f"Error: {error}")

            finally:
                if os.path.exists(audio_filename):
                    os.remove(audio_filename)

    # IMPORTANT: These fields must stay outside the audio_data condition.
    st.text_area(
        "What happened?",
        key="complaint_text",
        height=145,
        placeholder="Speak above or type your complaint here...",
    )

    st.markdown("### 👤 Your Details")

    st.text_input(
        "Your Name (Optional)",
        key="citizen_name",
        placeholder="Enter your name",
    )

    st.text_input(
        "Village / Area Name *",
        key="village_name",
        placeholder="Enter your village or area",
    )

    st.text_input(
        "City / District *",
        key="city_name",
        placeholder="Enter your city or district",
    )

    st.caption(
        "Enter your village and city. Exact map coordinates are optional."
    )


# ================ RIGHT: CATEGORY + LOCATION ================
with right:
    st.markdown(
        '<div class="section-heading">📌 What issue are you facing?</div>',
        unsafe_allow_html=True,
    )
    
    categories = [
        ("🗑️", "Garbage", "Waste and cleanliness", "#16A34A"),
        ("💧", "Water Supply", "Leaks and water issues", "#2563EB"),
        ("🛣️", "Road Damage", "Potholes and roads", "#EA580C"),
        ("🚿", "Drainage", "Blocked drains", "#9333EA"),
        ("💡", "Streetlights", "Lights not working", "#CA8A04"),
    ]

    # Four square-style cards in two columns
    for i in range(0, 4, 2):
        card_left, card_right = st.columns(2, gap="medium")

        for col, item in zip(
            [card_left, card_right],
            categories[i:i + 2],
        ):
            icon, category, description, color = item
            selected = st.session_state.selected_category == category

            with col:
                st.markdown(
                    f"""
                    <div style="
                        background: {color}33;
                        border: 1px solid {color};
                        border-radius: 16px;
                        padding: 18px 12px;
                        min-height: 145px;
                        text-align: center;
                    ">
                        <div style="
                            font-size: 36px;
                            margin-bottom: 8px;
                        ">{icon}</div>
                        <div style="
                            font-size: 18px;
                            font-weight: 800;
                        ">{category}</div>
                        <div style="
                            font-size: 13px;
                            margin-top: 6px;
                            color: #E1EAF5;
                        ">{description}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if st.button(
                    "✓ Selected" if selected else f"Select {category}",
                    key=f"select_{category}",
                    use_container_width=True,
                ):
                    st.session_state.selected_category = category
                    st.rerun()

    # Streetlights: full-width card below the four cards
    icon, category, description, color = categories[4]
    selected = st.session_state.selected_category == category

    st.markdown(
        f"""
        <div style="
            background: {color}33;
            border: 1px solid {color};
            border-radius: 16px;
            padding: 16px;
            margin-top: 10px;
            display: flex;
            align-items: center;
            gap: 16px;
        ">
            <div style="font-size: 38px;">{icon}</div>
            <div>
                <div style="font-size:18px;font-weight:800;">
                    {category}
                </div>
                <div style="font-size:13px;color:#E1EAF5;">
                    {description}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        "✓ Streetlights Selected" if selected else "Select Streetlights",
        key="select_Streetlights",
        use_container_width=True,
    ):
        st.session_state.selected_category = "Streetlights"
        st.rerun()

# ---------------- PROBLEM LOCATION MAP ----------------
    st.divider()

    st.markdown(
        '<div class="section-heading">📍 Problem Location</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<p style="font-size:14px;color:#E0EAF7;">'
        'Tap the map to mark the problem location. '
        'You can also continue using your village and city names.'
        '</p>',
        unsafe_allow_html=True,
    )

    try:
        import folium
        from streamlit_folium import st_folium

        location_map = folium.Map(
            location=[
                st.session_state.map_lat,
                st.session_state.map_lon,
            ],
            zoom_start=11,
            control_scale=True,
        )

        if st.session_state.map_selected:
            folium.Marker(
                [
                    st.session_state.map_lat,
                    st.session_state.map_lon,
                ],
                tooltip="Selected problem location",
                popup="Problem location",
                icon=folium.Icon(color="green", icon="map-marker"),
            ).add_to(location_map)

        map_result = st_folium(
            location_map,
            height=300,
            use_container_width=True,
            key="problem_location_map",
            returned_objects=["last_clicked"],
        )

        if map_result and map_result.get("last_clicked"):
            point = map_result["last_clicked"]
            lat = float(point["lat"])
            lon = float(point["lng"])

            if (
                not st.session_state.map_selected
                or lat != st.session_state.map_lat
                or lon != st.session_state.map_lon
            ):
                st.session_state.map_lat = lat
                st.session_state.map_lon = lon
                st.session_state.map_selected = True
                st.rerun()

        if st.session_state.map_selected:
            st.success("Problem location marked on the map.")
        else:
            st.caption(
                "No map pin selected. Village and city names are enough to continue."
            )

    except ImportError:
        st.info(
            "Map packages are not installed. You can still submit your location names."
        )

    except Exception:
        st.info(
            "The map is temporarily unavailable. You can still enter your location details."
        )


# ---------------- SUBMIT COMPLAINT ----------------
st.divider()

if st.button(
    "📨 Submit Complaint",
    type="primary",
    use_container_width=True,
):
    complaint = st.session_state.complaint_text.strip()
    village = st.session_state.village_name.strip()
    city = st.session_state.city_name.strip()
    category = st.session_state.selected_category
    name = st.session_state.citizen_name.strip()

    if not complaint:
        st.error("Please enter your complaint first.")

    elif not category:
        st.error("Please select an issue category.")

    elif not village:
        st.error("Please enter your village or area name.")

    elif not city:
        st.error("Please enter your city or district.")

    else:
        try:
            tracking_id, created_at = save_complaint(
                name=name,
                description=complaint,
                category=category,
                village=village,
                district=city,
                latitude=(
                    st.session_state.map_lat
                    if st.session_state.map_selected
                    else None
                ),
                longitude=(
                    st.session_state.map_lon
                    if st.session_state.map_selected
                    else None
                ),
            )

            st.session_state.submitted_complaint = {
                "tracking_id": tracking_id,
                "category": category,
                "village": village,
                "district": city,
                "created_at": created_at,
                "status": "Submitted",
            }

            st.rerun()

        except Exception as e:
            st.error("We couldn't save your complaint. Please try again.")
            st.caption(f"Database error: {e}")


# ---------------- FOOTER ----------------
st.divider()

st.markdown(
    '<div class="footer">'
    'A cleaner village | A safer tomorrow'
    '</div>',
    unsafe_allow_html=True,
)
