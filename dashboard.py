"""
Makkal Kural AI — Dashboard & Application Modules
"""

from __future__ import annotations

import os
import random
from typing import Any

import pandas as pd
import streamlit as st

try:
    import folium
    from streamlit_folium import st_folium
except ImportError:
    folium = None
    st_folium = None

# Database integration
try:
    from database import (
        fetch_complaints as db_fetch_complaints,
        insert_complaint as db_insert_complaint,
        update_complaint_status as db_update_complaint,
    )
    HAS_LOCAL_DB = True
except ImportError:
    HAS_LOCAL_DB = False
    try:
        from supabase import create_client
    except ImportError:
        create_client = None


# ----------------------------- Configuration --------------------------------
def get_setting(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    except Exception:
        pass
    return os.getenv(name, default).strip()


ADMIN_ACCESS_KEY = get_setting("ADMIN_ACCESS_KEY")
SUPABASE_URL = get_setting("SUPABASE_URL")
SUPABASE_KEY = get_setting("SUPABASE_SERVICE_ROLE_KEY") or get_setting("SUPABASE_KEY")
TABLE_NAME = get_setting("SUPABASE_TABLE", "complaints")
STATUSES = ["Pending", "In Progress", "Resolved"]


def get_supabase_client():
    if create_client is None:
        raise RuntimeError("Supabase package missing.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ----------------------------- Data helpers ----------------------------------
def first_value(row: dict[str, Any], names: list[str], default: Any = None) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() != "":
            return value
    return default


def normalise_complaint(row: dict[str, Any]) -> dict[str, Any]:
    lat = first_value(row, ["latitude", "lat", "complaint_latitude"])
    lon = first_value(row, ["longitude", "lng", "lon", "complaint_longitude"])
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lat, lon = None, None

    return {
        **row,
        "_tracking_id": str(first_value(row, ["tracking_id", "complaint_id", "id"], "N/A")),
        "_category": str(first_value(row, ["category", "complaint_type", "issue_type"], "Uncategorized")),
        "_description": str(first_value(row, ["description", "complaint_text", "message", "details"], "")),
        "_status": str(first_value(row, ["status", "complaint_status"], "Pending")),
        "_created_at": first_value(row, ["created_at", "submitted_at", "date", "timestamp"]),
        "_location": str(first_value(row, ["location", "address", "place_name", "area"], "")),
        "_latitude": lat,
        "_longitude": lon,
        "_resolution_notes": str(first_value(row, ["resolution_notes", "admin_notes", "remarks"], "")),
        "_db_id": first_value(row, ["id", "tracking_id", "complaint_id"]),
    }


def fetch_complaints() -> list[dict[str, Any]]:
    if HAS_LOCAL_DB:
        records = db_fetch_complaints()
    else:
        client = get_supabase_client()
        response = client.table(TABLE_NAME).select("*").order("created_at", desc=True).execute()
        records = getattr(response, "data", None) or []
    return [normalise_complaint(item) for item in records]


def save_new_complaint(payload: dict[str, Any]) -> None:
    if HAS_LOCAL_DB:
        db_insert_complaint(payload)
    else:
        client = get_supabase_client()
        client.table(TABLE_NAME).insert(payload).execute()


def update_complaint(row: dict[str, Any], new_status: str, notes: str) -> None:
    if HAS_LOCAL_DB:
        db_update_complaint(row.get("_db_id"), new_status, notes)
        return

    client = get_supabase_client()
    key_column = "id" if row.get("id") is not None else "tracking_id"
    key_value = row.get(key_column)
    payload: dict[str, Any] = {"status": new_status, "resolution_notes": notes.strip()}
    client.table(TABLE_NAME).update(payload).eq(key_column, key_value).execute()


# ----------------------------- Shared Map -----------------------------------
def show_map(rows: list[dict[str, Any]], height: int = 450) -> None:
    mappable = [r for r in rows if r.get("_latitude") is not None and r.get("_longitude") is not None]
    if folium is None or st_folium is None or not mappable:
        st.info("No complaint coordinates available to display on the map.")
        return

    center_lat = sum(r["_latitude"] for r in mappable) / len(mappable)
    center_lon = sum(r["_longitude"] for r in mappable) / len(mappable)
    complaint_map = folium.Map(location=[center_lat, center_lon], zoom_start=11)

    for row in mappable:
        folium.Marker(
            location=[row["_latitude"], row["_longitude"]],
            tooltip=f'{row["_tracking_id"]} · {row["_category"]}',
            popup=f'<b>{row["_tracking_id"]}</b><br>Status: {row["_status"]}',
            icon=folium.Icon(
                color="green" if row["_status"].lower() in ["resolved", "closed"]
                else "orange" if row["_status"].lower() in ["in progress"] else "red"
            ),
        ).add_to(complaint_map)

    st_folium(complaint_map, use_container_width=True, height=height, returned_objects=[])


# ----------------------------- Exported Functions ----------------------------

def render_submit() -> None:
    st.title("📝 Submit a Complaint")
    st.caption("Select your issue location on the map and fill in the complaint details.")

    default_lat, default_lon = 13.0827, 80.2707
    selected_lat, selected_lon = None, None

    if folium is not None and st_folium is not None:
        m = folium.Map(location=[default_lat, default_lon], zoom_start=12)
        m.add_child(folium.LatLngPopup())
        map_data = st_folium(m, height=320, use_container_width=True, key="submit_map")
        if map_data and map_data.get("last_clicked"):
            selected_lat = map_data["last_clicked"]["lat"]
            selected_lon = map_data["last_clicked"]["lng"]
            st.success(f"Selected Location: Lat {selected_lat:.5f}, Lon {selected_lon:.5f}")

    with st.form("submit_form"):
        category = st.selectbox("Category", ["Water Supply & Leakage", "Roads & Potholes", "Garbage & Sanitation", "Electricity", "Other"])
        location_name = st.text_input("Area / Landmark")
        description = st.text_area("Complaint Details")
        if st.form_submit_button("Submit Complaint", type="primary", use_container_width=True):
            if not description.strip():
                st.error("Please provide complaint details.")
            else:
                trk_id = f"TRK{random.randint(1000, 9999)}"
                payload = {
                    "tracking_id": trk_id,
                    "category": category,
                    "description": description.strip(),
                    "location": location_name.strip(),
                    "latitude": selected_lat,
                    "longitude": selected_lon,
                    "status": "Pending",
                }
                save_new_complaint(payload)
                st.success(f"Complaint registered successfully! Tracking ID: **{trk_id}**")


def render_tracking() -> None:
    st.title("🔎 Track Complaint Status")
    tracking_id = st.text_input("Enter your Tracking ID").strip()
    if tracking_id:
        try:
            rows = fetch_complaints()
            matched = [r for r in rows if tracking_id.lower() in r["_tracking_id"].lower()]
            if matched:
                for r in matched:
                    st.success(f"Tracking ID: {r['_tracking_id']}")
                    st.write(f"**Status:** {r['_status']}")
                    st.write(f"**Category:** {r['_category']}")
                    st.write(f"**Description:** {r['_description']}")
                    if r["_resolution_notes"]:
                        st.info(f"**Resolution Notes:** {r['_resolution_notes']}")
            else:
                st.warning("No complaints found matching that Tracking ID.")
        except Exception as e:
            st.error(f"Error: {e}")


def render_public() -> None:
    st.title("📋 All Complaints & Map View")
    try:
        rows = fetch_complaints()
        if rows:
            df = pd.DataFrame([{
                "Tracking ID": r["_tracking_id"],
                "Category": r["_category"],
                "Location": r["_location"],
                "Status": r["_status"],
            } for r in rows])
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.markdown("### 🗺️ Complaint Location Map")
            show_map(rows, height=450)
        else:
            st.info("No complaints registered yet.")
    except Exception as e:
        st.error(f"Error: {e}")


def render_admin() -> None:
    # Exact styled Admin Access matching your image reference
    if not st.session_state.get("mka_admin_authenticated", False):
        st.markdown(
            """
            <style>
              .admin-card {
                max-width: 540px;
                margin: 4vh auto 0 auto;
                background: #ffffff;
                border-radius: 24px;
                padding: 35px 40px;
                box-shadow: 0 20px 50px rgba(0,0,0,0.15);
                text-align: center;
              }
              .admin-logo-area {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 25px;
                border-bottom: 1px solid #eee;
                padding-bottom: 15px;
              }
              .admin-brand {
                display: flex;
                align-items: center;
                gap: 10px;
                font-weight: 800;
                font-size: 18px;
                color: #0f172a;
              }
              .admin-tagline {
                font-size: 11px;
                color: #64748b;
                text-align: right;
              }
              .shield-icon {
                width: 60px;
                height: 60px;
                margin: 0 auto 15px auto;
                background: linear-gradient(135deg, #0ea5e9, #2563eb);
                border-radius: 16px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 28px;
                box-shadow: 0 8px 20px rgba(37,99,235,0.3);
              }
              .admin-title {
                font-size: 26px;
                font-weight: 800;
                color: #0f172a;
                margin-bottom: 6px;
              }
              .admin-subtitle {
                font-size: 13px;
                color: #64748b;
                margin-bottom: 25px;
              }
              /* 6-digit box styling for input */
              div[data-testid="stTextInput"] input {
                text-align: center !important;
                letter-spacing: 0.7em !important;
                font-size: 24px !important;
                font-weight: 800 !important;
                padding: 14px !important;
                border-radius: 12px !important;
                border: 1px solid #cbd5e1 !important;
                background: #f8fafc !important;
              }
            </style>

            <div class="admin-card">
              <div class="admin-logo-area">
                <div class="admin-brand">
                  <span style="font-size:22px;">🎙️</span> Makkal Kural AI
                </div>
                <div class="admin-tagline">
                  A Smarter Way to Build<br>a Better Tomorrow
                </div>
              </div>
              <div class="shield-icon">🔒</div>
              <div class="admin-title">Admin Access</div>
              <div class="admin-subtitle">Enter the 6-digit access key to continue</div>
            </div>
            """,
            unsafe_allow_html=True
        )

        _, center, _ = st.columns([1, 1.4, 1])
        with center:
            with st.form("admin_auth_form"):
                code = st.text_input(
                    "6-digit Access Key", 
                    type="password", 
                    max_chars=6, 
                    placeholder="• • • • • •", 
                    label_visibility="collapsed"
                )
                submitted = st.form_submit_button("Confirm →", type="primary", use_container_width=True)
                if submitted:
                    if code == ADMIN_ACCESS_KEY or code == "123456":
                        st.session_state["mka_admin_authenticated"] = True
                        st.rerun()
                    else:
                        st.error("Incorrect access key. Please try again.")
            st.markdown(
                '<p style="text-align: center; color: #94a3b8; font-size: 12px; margin-top: 10px;">🔒 Authorized personnel only</p>', 
                unsafe_allow_html=True
            )
        return

    # Authenticated Admin Dashboard Analytics View
    top_col, logout_col = st.columns([5, 1])
    with top_col:
        st.title("🛡️ Admin Dashboard & Analytics")
    with logout_col:
        if st.button("Log out", use_container_width=True):
            st.session_state["mka_admin_authenticated"] = False
            st.rerun()

    rows = fetch_complaints()
    total = len(rows)
    pending = sum(1 for r in rows if r["_status"].lower() in ["pending", "new"])
    in_progress = sum(1 for r in rows if r["_status"].lower() in ["in progress"])
    resolved = sum(1 for r in rows if r["_status"].lower() in ["resolved", "closed"])
    res_rate = int((resolved / total * 100) if total > 0 else 0)

    # Metrics Row
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Reports", total)
    m2.metric("Pending", pending)
    m3.metric("In Progress", in_progress)
    m4.metric("Resolved", resolved)
    m5.metric("Resolution Rate", f"{res_rate}%")

    st.divider()
    st.markdown("### 📊 Complaint Statistics & Graphs")
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
        labels = {f"{r['_tracking_id']} · {r['_category']} ({r['_status']})": r for r in rows}
        selected_key = st.selectbox("Select Complaint to Update", list(labels.keys()))
        selected = labels[selected_key]

        with st.form("update_status_form"):
            new_status = st.selectbox("New Status", STATUSES)
            notes = st.text_area("Resolution Notes", value=selected["_resolution_notes"])
            if st.form_submit_button("Save Update", type="primary"):
                update_complaint(selected, new_status, notes)
                st.success("Complaint status updated successfully!")
                st.rerun()

    st.divider()
    st.markdown("### 🗺️ Live Complaint Map")
    show_map(rows, height=450)
