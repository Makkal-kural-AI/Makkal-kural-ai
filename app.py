"""
Makkal Kural AI — Dashboard & Application Modules
--------------------------------------------------
Exports:
- render_admin()    : Admin login, metric graphs, status updates, map view
- render_public()   : Public complaints listing and filtering
- render_submit()   : Complaint submission form with interactive location picker
- render_tracking() : Tracking view by tracking ID
"""

from __future__ import annotations

import os
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
    """Read Streamlit secrets first, then environment variables."""
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
        raise RuntimeError("Supabase package is missing. Add 'supabase' to requirements.txt.")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY).")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ----------------------------- Data helpers ----------------------------------
def first_value(row: dict[str, Any], names: list[str], default: Any = None) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() != "":
            return value
    return default


def normalise_complaint(row: dict[str, Any]) -> dict[str, Any]:
    """Map common database column names to consistent dashboard fields."""
    lat = first_value(row, ["latitude", "lat", "complaint_latitude"])
    lon = first_value(row, ["longitude", "lng", "lon", "complaint_longitude"])
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
        if lat is not None and not (-90 <= lat <= 90):
            lat = None
        if lon is not None and not (-180 <= lon <= 180):
            lon = None
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
    key_column = "id" if row.get("id") is not None else (
        "tracking_id" if row.get("tracking_id") is not None else "complaint_id"
    )
    key_value = row.get(key_column)
    if key_value is None:
        raise RuntimeError("Could not find an ID field for this complaint.")

    payload: dict[str, Any] = {"status": new_status}
    if notes.strip():
        payload["resolution_notes"] = notes.strip()

    try:
        client.table(TABLE_NAME).update(payload).eq(key_column, key_value).execute()
    except Exception:
        payload.pop("resolution_notes", None)
        client.table(TABLE_NAME).update(payload).eq(key_column, key_value).execute()


# ----------------------------- Shared Map Component ---------------------------
def show_map(rows: list[dict[str, Any]], height: int = 500) -> None:
    mappable = [
        r for r in rows
        if r.get("_latitude") is not None and r.get("_longitude") is not None
    ]
    if folium is None or st_folium is None:
        st.warning("Map packages are missing. Add folium and streamlit-folium to requirements.txt.")
        return
    if not mappable:
        st.info("No complaint coordinates recorded yet.")
        return

    center_lat = sum(r["_latitude"] for r in mappable) / len(mappable)
    center_lon = sum(r["_longitude"] for r in mappable) / len(mappable)
    complaint_map = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    for row in mappable:
        popup_html = f"""
        <div style="font-family:Arial;min-width:180px;">
          <b>{row["_tracking_id"]}</b><br>
          <b>Category:</b> {row["_category"]}<br>
          <b>Status:</b> {row["_status"]}<br>
          <b>Location:</b> {row["_location"] or "Not provided"}<br>
          <b>Details:</b> {row["_description"][:200]}
        </div>
        """
        folium.Marker(
            location=[row["_latitude"], row["_longitude"]],
            tooltip=f'{row["_tracking_id"]} · {row["_category"]}',
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(
                color="green" if row["_status"].lower() in ["resolved", "closed", "completed"]
                else "orange" if row["_status"].lower() in ["in progress", "in-progress", "processing"]
                else "red",
                icon="info-sign",
            ),
        ).add_to(complaint_map)

    st_folium(complaint_map, use_container_width=True, height=height, returned_objects=[])


# ----------------------------- App Exported Modules --------------------------

def render_submit() -> None:
    """📝 Submit a Complaint page with interactive map location selector."""
    st.title("📝 Submit a Complaint")
    st.caption("Select your issue location on the map and fill in the complaint details.")

    default_lat, default_lon = 13.0827, 80.2707  # Default center (e.g., Chennai)

    st.markdown("### 1. Select Location on Map")
    if folium is not None and st_folium is not None:
        m = folium.Map(location=[default_lat, default_lon], zoom_start=12)
        m.add_child(folium.LatLngPopup())
        map_data = st_folium(m, height=350, use_container_width=True, key="submit_map")

        selected_lat, selected_lon = None, None
        if map_data and map_data.get("last_clicked"):
            selected_lat = map_data["last_clicked"]["lat"]
            selected_lon = map_data["last_clicked"]["lng"]
            st.success(f"Selected Location: Lat {selected_lat:.5f}, Lon {selected_lon:.5f}")
    else:
        st.warning("Map functionality unavailable. Install folium and streamlit-folium.")
        selected_lat, selected_lon = None, None

    st.markdown("### 2. Complaint Information")
    with st.form("submit_complaint_form"):
        category = st.selectbox("Category", [
            "Water Supply & Leakage", "Roads & Potholes", "Garbage & Sanitation",
            "Electricity & Streetlights", "Drainage & Sewage", "Public Amenities", "Other"
        ])
        location_name = st.text_input("Area / Landmark", placeholder="e.g., Main Street, Ward 4")
        description = st.text_area("Complaint Details", placeholder="Describe the issue in detail…")

        submitted = st.form_submit_button("Submit Complaint", type="primary", use_container_width=True)
        if submitted:
            if not description.strip():
                st.error("Please provide a description for the complaint.")
            else:
                import random
                tracking_id = f"TRK{random.randint(1000, 9999)}"
                payload = {
                    "tracking_id": tracking_id,
                    "category": category,
                    "description": description.strip(),
                    "location": location_name.strip(),
                    "latitude": selected_lat,
                    "longitude": selected_lon,
                    "status": "Pending",
                }
                try:
                    save_new_complaint(payload)
                    st.balloons()
                    st.success(f"Complaint submitted successfully! Your Tracking ID is **{tracking_id}**")
                except Exception as exc:
                    st.error(f"Failed to submit complaint: {exc}")


def render_tracking() -> None:
    """🔎 Track Complaint status by Tracking ID."""
    st.title("🔎 Track Complaint")
    st.caption("Enter your tracking ID to check status updates and resolution notes.")

    tracking_id = st.text_input("Tracking ID", placeholder="e.g., TRK1234").strip()
    if tracking_id:
        try:
            rows = fetch_complaints()
            matched = [r for r in rows if tracking_id.lower() in r["_tracking_id"].lower()]
            if matched:
                for r in matched:
                    st.success(f"Record Found for ID: {r['_tracking_id']}")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Status", r["_status"])
                    c2.metric("Category", r["_category"])
                    c3.metric("Submitted", str(r["_created_at"])[:10] if r["_created_at"] else "N/A")

                    st.markdown(f"**Location:** {r['_location'] or 'Not provided'}")
                    st.markdown(f"**Description:** {r['_description']}")
                    if r["_resolution_notes"]:
                        st.info(f"**Resolution Notes:** {r['_resolution_notes']}")
            else:
                st.warning("No complaint record found matching that Tracking ID.")
        except Exception as exc:
            st.error(f"Error reading complaint status: {exc}")


def render_public() -> None:
    """📋 All Public Complaints list and map view."""
    st.title("📋 Public Complaints View")
    st.caption("View and filter active public grievances across all regions.")

    try:
        rows = fetch_complaints()
    except Exception as exc:
        st.error(f"Could not load complaints: {exc}")
        return

    if not rows:
        st.info("No complaints registered in the system yet.")
        return

    col1, col2 = st.columns([1, 1])
    with col1:
        cat_filter = st.selectbox("Filter Category", ["All"] + sorted({r["_category"] for r in rows}))
    with col2:
        stat_filter = st.selectbox("Filter Status", ["All"] + sorted({r["_status"] for r in rows}))

    filtered = rows
    if cat_filter != "All":
        filtered = [r for r in filtered if r["_category"] == cat_filter]
    if stat_filter != "All":
        filtered = [r for r in filtered if r["_status"] == stat_filter]

    df_display = pd.DataFrame([{
        "Tracking ID": r["_tracking_id"],
        "Category": r["_category"],
        "Location": r["_location"],
        "Status": r["_status"],
        "Submitted": str(r["_created_at"])[:19] if r["_created_at"] else "N/A"
    } for r in filtered])

    st.dataframe(df_display, use_container_width=True, hide_index=True)
    st.markdown("### Complaint Map")
    show_map(filtered, height=450)


def render_admin() -> None:
    """🔐 Admin Dashboard with 6-digit key verification, statistics, and resolution controls."""
    if not st.session_state.get("mka_admin_authenticated", False):
        st.markdown("## 🔐 Admin Authentication")
        st.caption("Enter the 6-digit access key to access the administration console.")

        _, center, _ = st.columns([1, 1.2, 1])
        with center:
            with st.form("admin_auth_form"):
                code = st.text_input("Access Key", type="password", max_chars=6, placeholder="• • • • • •")
                submitted = st.form_submit_button("Verify & Open Dashboard", type="primary", use_container_width=True)
                if submitted:
                    if not ADMIN_ACCESS_KEY:
                        st.error("ADMIN_ACCESS_KEY is not configured in server secrets or environment variables.")
                    elif code == ADMIN_ACCESS_KEY:
                        st.session_state["mka_admin_authenticated"] = True
                        st.rerun()
                    else:
                        st.error("Invalid access key. Please try again.")
        return

    # Admin view once authenticated
    top_col, logout_col = st.columns([5, 1])
    with top_col:
        st.title("🛡️ Admin Console")
    with logout_col:
        if st.button("Log out"):
            st.session_state["mka_admin_authenticated"] = False
            st.rerun()

    try:
        rows = fetch_complaints()
    except Exception as exc:
        st.error(f"Error fetching data: {exc}")
        return

    # Summary Statistics
    total = len(rows)
    pending = sum(1 for r in rows if r["_status"].lower() in ["pending", "new"])
    in_progress = sum(1 for r in rows if r["_status"].lower() in ["in progress", "in-progress"])
    resolved = sum(1 for r in rows if r["_status"].lower() in ["resolved", "closed"])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Reports", total)
    m2.metric("Pending", pending)
    m3.metric("In Progress", in_progress)
    m4.metric("Resolved", resolved)

    st.divider()
    st.markdown("### Update Complaint Status")
    if rows:
        labels = {f"{r['_tracking_id']} · {r['_category']} ({r['_status']})": r for r in rows}
        selected_key = st.selectbox("Select Complaint", list(labels.keys()))
        selected = labels[selected_key]

        with st.form("admin_update_form"):
            new_status = st.selectbox("Status", STATUSES, index=STATUSES.index(selected["_status"]) if selected["_status"] in STATUSES else 0)
            notes = st.text_area("Resolution Notes", value=selected["_resolution_notes"])
            if st.form_submit_button("Save Update", type="primary"):
                try:
                    update_complaint(selected, new_status, notes)
                    st.success("Status updated successfully.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to update status: {e}")

    st.divider()
    st.markdown("### Interactive Geographic Distribution")
    show_map(rows, height=500)
