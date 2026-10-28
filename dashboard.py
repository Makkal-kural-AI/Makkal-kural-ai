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
        st.info("வரைபடத்தில் காட்ட எந்த தகவல்களும் இல்லை.")
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
    st.title("📝 புகாரைப் பதிவு செய்ய")
    st.caption("வரைபடத்தில் உங்கள் இடத்தை தேர்வு செய்து தகவல்களை நிரப்பவும்.")

    default_lat, default_lon = 13.0827, 80.2707
    selected_lat, selected_lon = None, None

    if folium is not None and st_folium is not None:
        m = folium.Map(location=[default_lat, default_lon], zoom_start=12)
        m.add_child(folium.LatLngPopup())
        map_data = st_folium(m, height=320, use_container_width=True, key="submit_map")
        if map_data and map_data.get("last_clicked"):
            selected_lat = map_data["last_clicked"]["lat"]
            selected_lon = map_data["last_clicked"]["lng"]
            st.success(f"தேர்வு செய்யப்பட்ட இடம்: Lat {selected_lat:.5f}, Lon {selected_lon:.5f}")

    with st.form("submit_form"):
        category = st.selectbox("பிரிவு (Category)", ["குடிநீர் வசதி", "சாலைப் பராமரிப்பு", "சுகாதாரம் & குப்பை", "மின்சாரம்", "இதர"])
        location_name = st.text_input("இடம் / முகவரி")
        description = st.text_area("புகாரின் விவரம்")
        if st.form_submit_button("சமர்ப்பி (Submit)", type="primary", use_container_width=True):
            if not description.strip():
                st.error("புகார் விவரங்களை உள்ளிடவும்.")
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
                st.success(f"புகார் பதிவு செய்யப்பட்டது! Tracking ID: **{trk_id}**")


def render_tracking() -> None:
    st.title("🔎 புகாரின் நிலையைக் கண்டறிய")
    tracking_id = st.text_input("Tracking ID உள்ளிடவும்").strip()
    if tracking_id:
        try:
            rows = fetch_complaints()
            matched = [r for r in rows if tracking_id.lower() in r["_tracking_id"].lower()]
            if matched:
                for r in matched:
                    st.success(f"Tracking ID: {r['_tracking_id']}")
                    st.write(f"**நிலை (Status):** {r['_status']}")
                    st.write(f"**பிரிவு:** {r['_category']}")
                    st.write(f"**விவரம்:** {r['_description']}")
                    if r["_resolution_notes"]:
                        st.info(f"**நிர்வாகக் குறிப்பு:** {r['_resolution_notes']}")
            else:
                st.warning("இந்த Tracking ID-ல் புகார்கள் எதுவும் இல்லை.")
        except Exception as e:
            st.error(f"பிழை: {e}")


def render_public() -> None:
    st.title("📋 அனைத்துப் புகார்கள் & வரைபடம்")
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
            st.markdown("### 🗺️ புகார்கள் உள்ள இடங்கள்")
            show_map(rows, height=450)
        else:
            st.info("புகார்கள் எதுவும் பதிவு செய்யப்படவில்லை.")
    except Exception as e:
        st.error(f"பிழை: {e}")


def render_admin() -> None:
    # அட்மின் லாகின் செய்யப்படாவிட்டால் மட்டுமே இந்த லாகின் கார்டு வரும்
    if not st.session_state.get("mka_admin_authenticated", False):
        st.markdown(
            """
            <div style="max-width: 440px; margin: 20px auto; padding: 25px; background: rgba(255,255,255,0.95); border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.15); text-align: center;">
              <div style="font-size: 38px; margin-bottom: 5px;">🔐</div>
              <h2 style="color:#10213d; font-size:24px; margin-bottom:5px;">Admin Access</h2>
              <p style="color: #64748b; font-size: 13px;">Enter your 6-digit access key to continue</p>
            </div>
            """,
            unsafe_allow_html=True
        )

        _, center, _ = st.columns([1, 1.2, 1])
        with center:
            with st.form("admin_auth_form"):
                code = st.text_input("Access Key", type="password", max_chars=6, placeholder="• • • • • •", label_visibility="collapsed")
                submitted = st.form_submit_button("Confirm →", type="primary", use_container_width=True)
                if submitted:
                    if code == ADMIN_ACCESS_KEY or code == "123456": # உங்களுக்குத் தேவையான Key அமைத்துக் கொள்ளலாம்
                        st.session_state["mka_admin_authenticated"] = True
                        st.rerun()
                    else:
                        st.error("தவறான Access Key. மீண்டும் முயலவும்.")
        return

    # அட்மின் உள்நுழைந்த பிறகு (Dashboard Analytics)
    top_col, logout_col = st.columns([5, 1])
    with top_col:
        st.title("🛡️ Admin Dashboard & Analytics")
    with logout_col:
        if st.button("Log out"):
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
    m1.metric("Total", total)
    m2.metric("Pending", pending)
    m3.metric("In Progress", in_progress)
    m4.metric("Resolved", resolved)
    m5.metric("Resolution", f"{res_rate}%")

    st.divider()
    st.markdown("### 📊 புகார்களின் புள்ளிவிவரங்கள் (Graphs)")
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
    st.markdown("### 📋 நிலையை மாற்றுக (Status Update)")
    if rows:
        labels = {f"{r['_tracking_id']} · {r['_category']} ({r['_status']})": r for r in rows}
        selected_key = st.selectbox("புகாரைத் தேர்ந்தெடுக்கவும்", list(labels.keys()))
        selected = labels[selected_key]

        with st.form("update_status_form"):
            new_status = st.selectbox("புதிய நிலை", STATUSES)
            notes = st.text_area("குறிப்புகள் (Resolution Notes)", value=selected["_resolution_notes"])
            if st.form_submit_button("Save Update", type="primary"):
                update_complaint(selected, new_status, notes)
                st.success("நிலை வெற்றிகரமாக மாற்றப்பட்டது!")
                st.rerun()

    st.divider()
    st.markdown("### 🗺️ நேரலை வரைபடம் (Live Map)")
    show_map(rows, height=450)
