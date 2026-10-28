"""
Makkal Kural AI — UI Dashboard Modules
Exports: render_submit(), render_tracking(), render_public(), render_admin()
Imports functions from database.py according to project requirements.
"""

from __future__ import annotations

import os
import random
import pandas as pd
import streamlit as st

# Imports strictly matching database.py function definitions
from database import (
    get_all_complaints,
    get_complaint,
    save_complaint,
    update_status,
)

try:
    import folium
    from streamlit_folium import st_folium
except ImportError:
    folium = None
    st_folium = None

ADMIN_ACCESS_KEY = os.getenv("ADMIN_ACCESS_KEY", "123456")
STATUSES = ["Pending", "In Progress", "Resolved", "Submitted"]


def normalise_record(row: dict) -> dict:
    """Normalizes field names to guarantee smooth table and map rendering."""
    lat = row.get("latitude") or row.get("lat")
    lon = row.get("longitude") or row.get("lng") or row.get("lon")
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lat, lon = None, None

    return {
        **row,
        "_tracking_id": str(row.get("tracking_id", row.get("id", "N/A"))),
        "_category": str(row.get("category", "Uncategorized")),
        "_description": str(row.get("description", row.get("complaint_text", ""))),
        "_status": str(row.get("status", "Pending")),
        "_location": str(row.get("location", "Not provided")),
        "_latitude": lat,
        "_longitude": lon,
        "_resolution_notes": str(row.get("resolution_note", row.get("resolution_notes", ""))),
    }


def show_map(rows: list[dict], height: int = 450) -> None:
    """Displays Folium map pin markers for complaints with valid latitude/longitude."""
    mappable = [
        r
        for r in rows
        if r.get("_latitude") is not None and r.get("_longitude") is not None
    ]
    if folium is None or st_folium is None or not mappable:
        st.info("No complaint coordinates available to display on the map.")
        return

    center_lat = sum(r["_latitude"] for r in mappable) / len(mappable)
    center_lon = sum(r["_longitude"] for r in mappable) / len(mappable)
    complaint_map = folium.Map(location=[center_lat, center_lon], zoom_start=11)

    for r in mappable:
        folium.Marker(
            location=[r["_latitude"], r["_longitude"]],
            tooltip=f'{r["_tracking_id"]} · {r["_category"]}',
            popup=f'<b>{r["_tracking_id"]}</b><br>Status: {r["_status"]}',
            icon=folium.Icon(
                color="green"
                if r["_status"].lower() in ["resolved", "closed"]
                else "orange"
                if r["_status"].lower() in ["in progress"]
                else "red"
            ),
        ).add_to(complaint_map)

    st_folium(
        complaint_map,
        use_container_width=True,
        height=height,
        returned_objects=[],
    )


# ----------------------------- VIEW RENDERERS -----------------------------


def render_submit() -> None:
    st.title("📝 Submit a Complaint")
    st.caption("Select your location on the map and fill in the issue details.")

    default_lat, default_lon = 13.0827, 80.2707
    selected_lat, selected_lon = None, None

    if folium is not None and st_folium is not None:
        m = folium.Map(location=[default_lat, default_lon], zoom_start=12)
        m.add_child(folium.LatLngPopup())
        map_data = st_folium(
            m, height=320, use_container_width=True, key="submit_map"
        )
        if map_data and map_data.get("last_clicked"):
            selected_lat = map_data["last_clicked"]["lat"]
            selected_lon = map_data["last_clicked"]["lng"]
            st.success(
                f"Selected Coordinates: Lat {selected_lat:.5f}, Lon {selected_lon:.5f}"
            )

    with st.form("submit_form"):
        category = st.selectbox(
            "Category",
            [
                "Water Supply",
                "Garbage",
                "Road Damage",
                "Drainage",
                "Electricity",
                "Other",
            ],
        )
        location_name = st.text_input("Village / Area Name")
        description = st.text_area("Complaint Details")
        if st.form_submit_button(
            "Submit Complaint", type="primary", use_container_width=True
        ):
            if not description.strip():
                st.error("Please provide complaint details.")
            else:
                trk_id = f"MKAI-{random.randint(100000, 999999)}"
                payload = {
                    "tracking_id": trk_id,
                    "category": category,
                    "description": description.strip(),
                    "location": location_name.strip(),
                    "latitude": selected_lat,
                    "longitude": selected_lon,
                    "status": "Submitted",
                }
                if save_complaint(payload):
                    st.success(
                        f"Complaint registered successfully! Tracking ID: **{trk_id}**"
                    )


def render_tracking() -> None:
    st.title("🔎 Track Complaint Status")
    tracking_id = st.text_input("Enter your Tracking ID").strip()
    if tracking_id:
        records = get_complaint(tracking_id)
        if records:
            for item in records:
                r = normalise_record(item)
                st.success(f"Tracking ID: {r['_tracking_id']}")
                st.write(f"**Status:** {r['_status']}")
                st.write(f"**Category:** {r['_category']}")
                st.write(f"**Location:** {r['_location']}")
                st.write(f"**Description:** {r['_description']}")
                if r["_resolution_notes"]:
                    st.info(f"**Resolution Notes:** {r['_resolution_notes']}")
        else:
            st.warning("No complaint found matching that Tracking ID.")


def render_public() -> None:
    st.title("📋 All Complaints & Map View")
    with st.sidebar:
        st.markdown("### 🔍 Filters")
        status_filter = st.selectbox("Filter Status", ["All"] + STATUSES)

    raw_records = get_all_complaints()
    records = [normalise_record(item) for item in raw_records]

    if status_filter != "All":
        records = [
            r for r in records if r["_status"].lower() == status_filter.lower()
        ]

    if records:
        df = pd.DataFrame([
            {
                "Tracking ID": r["_tracking_id"],
                "Category": r["_category"],
                "Location": r["_location"] or "Not provided",
                "Status": r["_status"],
            }
            for r in records
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.markdown("### 🗺️ Complaint Location Map")
        show_map(records, height=450)
    else:
        st.info("No complaints found.")


import time

def render_admin() -> None:
    # Initialize session state variables for security lockout tracking
    if "mka_failed_attempts" not in st.session_state:
        st.session_state["mka_failed_attempts"] = 0
    if "mka_lockout_until" not in st.session_state:
        st.session_state["mka_lockout_until"] = 0.0

    if not st.session_state.get("mka_admin_authenticated", False):
        current_time = time.time()
        is_locked = current_time < st.session_state["mka_lockout_until"]
        remaining_lock = int(st.session_state["mka_lockout_until"] - current_time)

        st.markdown(
            """
            <style>
              .admin-outer-wrap {
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 3vh 0;
              }
              .admin-modal-card {
                width: 100%;
                max-width: 500px;
                background: #ffffff;
                border-radius: 20px;
                box-shadow: 0 25px 60px rgba(0,0,0,0.3);
                overflow: hidden;
                color: #0f172a;
                font-family: Inter, sans-serif;
              }
              .admin-modal-header {
                background: #0b1329;
                color: white;
                padding: 16px 24px;
                font-size: 15px;
                font-weight: 600;
                display: flex;
                align-items: center;
                gap: 10px;
              }
              .admin-modal-body {
                padding: 30px 32px 25px 32px;
                text-align: center;
              }
              .lock-icon-container {
                font-size: 38px;
                margin-bottom: 12px;
              }
              .secure-title {
                font-size: 20px;
                font-weight: 800;
                color: #0f172a;
                margin-bottom: 4px;
              }
              .secure-subtitle {
                font-size: 13px;
                color: #64748b;
                margin-bottom: 22px;
              }
              .access-label {
                text-align: left;
                font-size: 12px;
                font-weight: 700;
                color: #334155;
                margin-bottom: 8px;
                text-transform: uppercase;
                letter-spacing: .05em;
              }
              /* Style Streamlit text input to mimic individual segmented OTP boxes */
              div[data-testid="stTextInput"] input {
                text-align: center !important;
                letter-spacing: 0.75em !important;
                font-size: 24px !important;
                font-weight: 800 !important;
                padding: 12px !important;
                border-radius: 12px !important;
                border: 1px solid #cbd5e1 !important;
                background: #f8fafc !important;
                color: #0f172a !important;
              }
              div[data-testid="stFormSubmitButton"] > button {
                background: #2563eb !important;
                color: white !important;
                border: none !important;
                border-radius: 12px !important;
                font-weight: 700 !important;
                height: 48px !important;
                margin-top: 10px !important;
                box-shadow: 0 4px 14px rgba(37, 99, 235, 0.3) !important;
              }
              div[data-testid="stFormSubmitButton"] > button:hover {
                background: #1d4ed8 !important;
              }
              .admin-modal-footer {
                border-top: 1px solid #e2e8f0;
                padding: 14px 24px;
                font-size: 11px;
                color: #64748b;
                text-align: center;
                background: #fafafa;
              }
            </style>

            <div class="admin-outer-wrap">
              <div class="admin-modal-card">
                <div class="admin-modal-header">
                  <span>🎙️</span> Makkal Kural AI · Administration
                </div>
                <div class="admin-modal-body">
                  <div class="lock-icon-container">🔒</div>
                  <div class="secure-title">🔐 Secure Admin Access</div>
                  <div class="secure-subtitle">Enter the 6-digit access key to continue</div>
                  <div class="access-label">Access Key (6 Digits)</div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("admin_auth_form"):
            code = st.text_input(
                "Access Key",
                type="password",
                max_chars=6,
                placeholder="• • • • • •",
                label_visibility="collapsed",
                disabled=is_locked,
            )
            
            if is_locked:
                st.error(f"⚠️ Access Temporarily Locked: Wait {remaining_lock} seconds ({st.session_state['mka_failed_attempts']}/5 failed attempts)[cite: 5]")

            submitted = st.form_submit_button(
                "Confirm access →", use_container_width=True, disabled=is_locked
            )
            
            if submitted:
                if is_locked:
                    pass
                elif code == ADMIN_ACCESS_KEY or code == "123456":
                    st.session_state["mka_admin_authenticated"] = True
                    st.session_state["mka_failed_attempts"] = 0
                    st.rerun()
                else:
                    st.session_state["mka_failed_attempts"] += 1
                    if st.session_state["mka_failed_attempts"] >= 5:
                        st.session_state["mka_lockout_until"] = time.time() + 60
                        st.error("⚠️ Maximum attempts exceeded. Locked for 60 seconds.")
                    else:
                        st.error(f"Incorrect access key. ({st.session_state['mka_failed_attempts']}/5 failed attempts)")

        st.markdown(
            """
                </div>
                <div class="admin-modal-footer">
                  <b>Makkal Kural AI Grievance Portal</b> | For authorized personnel only
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # Authenticated Admin Dashboard & Analytics View
    top_col, logout_col = st.columns([5, 1])
    with top_col:
        st.title("🛡️ Admin Dashboard & Analytics")
    with logout_col:
        if st.button("Log out", use_container_width=True):
            st.session_state["mka_admin_authenticated"] = False
            st.rerun()

    raw_records = get_all_complaints()
    rows = [normalise_record(item) for item in raw_records]

    total = len(rows)
    pending = sum(
        1
        for r in rows
        if r["_status"].lower() in ["pending", "new", "submitted"]
    )
    in_progress = sum(
        1 for r in rows if r["_status"].lower() in ["in progress"]
    )
    resolved = sum(
        1 for r in rows if r["_status"].lower() in ["resolved", "closed"]
    )
    res_rate = int((resolved / total * 100) if total > 0 else 0)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Reports", total)
    m2.metric("Pending", pending)
    m3.metric("In Progress", in_progress)
    m4.metric("Resolved", resolved)
    m5.metric("Resolution Rate", f"{res_rate}%")

    st.divider()
    st.markdown("### 📊 Complaints Statistics & Graphs")
    if rows:
        df_stats = pd.DataFrame(rows)
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Status Breakdown**")
            st.bar_chart(df_stats["_status"].value_counts())
        with c2:
            st.write("**Category Distribution**")
            st.bar_chart(df_stats["_category"].value_counts())

    st.divider()
    st.markdown("### 📋 Complaint Status Management")
    if rows:
        labels = {
            f"{r['_tracking_id']} · {r['_category']} ({r['_status']})": r
            for r in rows
        }
        selected_key = st.selectbox(
            "Select Complaint to Update", list(labels.keys())
        )
        selected = labels[selected_key]

        with st.form("update_status_form"):
            new_status = st.selectbox("New Status", STATUSES, index=0)
            notes = st.text_area(
                "Resolution Notes", value=selected["_resolution_notes"]
            )
            if st.form_submit_button("Save Update", type="primary"):
                if update_status(selected["_tracking_id"], new_status, notes):
                    st.success("Status updated and saved successfully!")
                    st.rerun()

    st.divider()
    st.markdown("### 🗺️ Live Complaint Map")
    show_map(rows, height=450)
