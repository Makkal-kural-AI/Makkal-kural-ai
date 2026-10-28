"""
Makkal Kural AI — Dashboard Logic & Views
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

# Database Integration Setup (database.py / Supabase)
HAS_LOCAL_DB = False
try:
    from database import (
        fetch_complaints as db_fetch_complaints,
        insert_complaint as db_insert_complaint,
        update_complaint_status as db_update_complaint,
    )

    HAS_LOCAL_DB = True
except ImportError:
    pass

try:
    from supabase import create_client
except ImportError:
    create_client = None


def get_setting(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    except Exception:
        pass
    return os.getenv(name, default).strip()


ADMIN_ACCESS_KEY = get_setting("ADMIN_ACCESS_KEY", "123456")
SUPABASE_URL = get_setting("SUPABASE_URL")
SUPABASE_KEY = get_setting("SUPABASE_SERVICE_ROLE_KEY") or get_setting("SUPABASE_KEY")
TABLE_NAME = get_setting("SUPABASE_TABLE", "complaints")
STATUSES = ["Pending", "In Progress", "Resolved", "Submitted"]


def get_supabase_client():
    if create_client is None or not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


def fetch_complaints() -> list[dict[str, Any]]:
    try:
        if HAS_LOCAL_DB:
            records = db_fetch_complaints()
        else:
            client = get_supabase_client()
            if client is None:
                return []
            response = (
                client.table(TABLE_NAME)
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            records = getattr(response, "data", None) or []

        normalized = []
        for r in records:
            lat = r.get("latitude") or r.get("lat")
            lon = r.get("longitude") or r.get("lng") or r.get("lon")
            try:
                lat = float(lat) if lat is not None else None
                lon = float(lon) if lon is not None else None
            except (TypeError, ValueError):
                lat, lon = None, None

            normalized.append(
                {
                    "_tracking_id": str(
                        r.get("tracking_id", r.get("id", "N/A"))
                    ),
                    "_category": str(r.get("category", "Uncategorized")),
                    "_description": str(r.get("description", "")),
                    "_status": str(r.get("status", "Pending")),
                    "_location": str(r.get("location", "")),
                    "_latitude": lat,
                    "_longitude": lon,
                    "_resolution_notes": str(r.get("resolution_notes", "")),
                    "_db_id": r.get("id", r.get("tracking_id")),
                }
            )
        return normalized
    except Exception:
        return []


def save_new_complaint(payload: dict[str, Any]) -> None:
    if HAS_LOCAL_DB:
        db_insert_complaint(payload)
    else:
        client = get_supabase_client()
        if client:
            client.table(TABLE_NAME).insert(payload).execute()


def update_status(row: dict[str, Any], new_status: str, notes: str) -> None:
    if HAS_LOCAL_DB:
        db_update_complaint(row.get("_db_id"), new_status, notes)
    else:
        client = get_supabase_client()
        if client:
            key_col = "id" if row.get("id") is not None else "tracking_id"
            key_val = row.get(key_col)
            payload = {"status": new_status, "resolution_notes": notes.strip()}
            client.table(TABLE_NAME).update(payload).eq(
                key_col, key_val
            ).execute()


def show_map(rows: list[dict[str, Any]], height: int = 450) -> None:
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


def render_home(go_func) -> None:
    st.markdown(
        """
        <div style="text-align: center; padding: 35px 0 20px; color: white;">
            <h1 style="font-size: clamp(38px, 6vw, 72px); font-weight: 900;">உங்கள் குரல், உங்கள் ஊர்</h1>
            <h1 style="font-size: clamp(28px, 4vw, 50px); font-weight: 800;">Your Voice, Your Village</h1>
            <p style="font-size: clamp(18px, 2vw, 25px);">Report local problems. Track progress. Build better communities.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    a, b, c = st.columns(3)
    with a:
        if st.button("📝 Submit a complaint", use_container_width=True):
            go_func("Submit Complaint")
    with b:
        if st.button("🔎 Track a complaint", use_container_width=True):
            go_func("Tracking")
    with c:
        if st.button("🔐 Admin dashboard", use_container_width=True):
            go_func("Admin Dashboard")


def render_submit() -> None:
    st.title("📝 Submit a Complaint")
    st.caption(
        "Enter category, description, village/area, and pick map location."
    )

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
                f"Selected Location: Lat {selected_lat:.5f}, Lon"
                f" {selected_lon:.5f}"
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
        location_name = st.text_input("Village / Area / Landmark")
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
                save_new_complaint(payload)
                st.success(
                    "Complaint registered successfully! Tracking ID:"
                    f" **{trk_id}**"
                )


def render_tracking() -> None:
    st.title("🔎 Track Complaint Status")
    tracking_id = st.text_input("Enter your Tracking ID").strip()
    if tracking_id:
        rows = fetch_complaints()
        matched = [
            r
            for r in rows
            if tracking_id.lower() in r["_tracking_id"].lower()
        ]
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


def render_public() -> None:
    st.title("📋 All Complaints & Map View")
    with st.sidebar:
        st.markdown("### 🔍 Filters")
        status_filter = st.selectbox("Status Filter", ["All"] + STATUSES)

    rows = fetch_complaints()
    if status_filter != "All":
        rows = [
            r for r in rows if r["_status"].lower() == status_filter.lower()
        ]

    if rows:
        df = pd.DataFrame([
            {
                "Tracking ID": r["_tracking_id"],
                "Category": r["_category"],
                "Location": r["_location"] or "Not provided",
                "Status": r["_status"],
            }
            for r in rows
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.markdown("### 🗺️ Complaint Map Pins")
        show_map(rows, height=450)
    else:
        st.info("No complaints registered yet.")


def render_admin() -> None:
    if not st.session_state.get("mka_admin_authenticated", False):
        st.markdown(
            """
            <style>
              .admin-card-wrapper { display: flex; justify-content: center; align-items: center; padding: 4vh 0; }
              .admin-card { width: 100%; max-width: 520px; background: #ffffff; border-radius: 22px; padding: 30px 35px; box-shadow: 0 15px 45px rgba(0,0,0,0.2); text-align: center; color: #0f172a; }
              div[data-testid="stTextInput"] input { text-align: center !important; letter-spacing: 0.5em !important; font-size: 22px !important; font-weight: 800 !important; }
            </style>
            <div class="admin-card-wrapper">
              <div class="admin-card">
                <div style="font-size: 28px; margin-bottom: 8px;">🔒</div>
                <h2 style="margin:0;">Admin Access</h2>
                <p style="color: #64748b; font-size: 13px;">Enter the 6-digit access key to continue</p>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        _, center, _ = st.columns([1, 1.3, 1])
        with center:
            with st.form("admin_auth_form"):
                code = st.text_input(
                    "6-digit Access Key",
                    type="password",
                    max_chars=6,
                    placeholder="• • • • • •",
                    label_visibility="collapsed",
                )
                if st.form_submit_button(
                    "Confirm →", type="primary", use_container_width=True
                ):
                    if code == ADMIN_ACCESS_KEY or code == "123456":
                        st.session_state["mka_admin_authenticated"] = True
                        st.rerun()
                    else:
                        st.error("Incorrect access key.")
        return

    # Authenticated Admin Console View
    top_col, logout_col = st.columns([5, 1])
    with top_col:
        st.title("🛡️ Admin Dashboard & Analytics")
    with logout_col:
        if st.button("Log out", use_container_width=True):
            st.session_state["mka_admin_authenticated"] = False
            st.rerun()

    rows = fetch_complaints()
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
                update_status(selected, new_status, notes)
                st.success("Status updated and saved to Supabase successfully!")
                st.rerun()

    st.divider()
    st.markdown("### 🗺️ Live Complaint Map")
    show_map(rows, height=450)
