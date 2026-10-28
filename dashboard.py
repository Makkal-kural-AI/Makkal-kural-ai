"""
Makkal Kural AI — Admin Dashboard
---------------------------------
Features:
- Styled admin login using ADMIN_ACCESS_KEY from environment / Streamlit secrets
- All Complaints table with search and filters
- Interactive Folium map with complaint pins
- Status updates and optional resolution notes
- Summary metrics

Expected Supabase table by default: "complaints"
Common expected columns: tracking_id, category, description, status, created_at,
latitude, longitude, location, resolution_notes

If your database.py already contains database helpers, you can replace the
Supabase functions below with calls to those helpers. The exact project ZIP
was not available while this file was prepared, so verify table/column names
against your existing schema before deploying.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

try:
    import folium
    from streamlit_folium import st_folium
except ImportError:
    folium = None
    st_folium = None

try:
    from supabase import create_client
except ImportError:
    create_client = None


# ----------------------------- Page setup -----------------------------------
st.set_page_config(
    page_title="Makkal Kural AI | Admin",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
      html, body, [class*="css"] { font-family: Inter, sans-serif; }
      .stApp {
        background:
          radial-gradient(circle at 10% 0%, rgba(14,165,233,.10), transparent 30%),
          linear-gradient(135deg, #f7faff 0%, #f1f5fb 55%, #f8fafc 100%);
      }
      [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0b1730 0%, #10264a 100%);
      }
      [data-testid="stSidebar"] * { color: #edf5ff !important; }
      .brand { display:flex; align-items:center; gap:12px; margin: 0 0 20px 0; }
      .brand-icon {
        width:48px;height:48px;border-radius:15px;
        display:flex;align-items:center;justify-content:center;
        background:linear-gradient(135deg,#0ea5e9,#2563eb);
        color:white;font-size:24px;box-shadow:0 10px 25px rgba(37,99,235,.25);
      }
      .brand-name { font-size:22px;font-weight:800;color:#12213b;line-height:1.1; }
      .brand-sub { color:#64748b;font-size:12px;margin-top:4px; }
      .login-wrap {
        max-width: 470px; margin: 5vh auto 0 auto; padding: 34px;
        background: rgba(255,255,255,.94); border:1px solid #e3eaf4;
        border-radius:26px; box-shadow:0 24px 70px rgba(15,35,70,.12);
      }
      .login-icon {
        height:64px;width:64px;margin:0 auto 16px auto;border-radius:20px;
        display:flex;align-items:center;justify-content:center;
        background:linear-gradient(135deg,#0ea5e9,#2563eb);
        color:#fff;font-size:30px;
      }
      .login-title {text-align:center;color:#10213d;font-size:28px;font-weight:800;}
      .login-sub {text-align:center;color:#64748b;font-size:14px;margin:8px 0 22px;}
      .metric-card {
        background:white;border:1px solid #e5edf7;border-radius:18px;
        padding:18px 20px;box-shadow:0 5px 18px rgba(15,35,70,.04);
      }
      .metric-label {font-size:12px;text-transform:uppercase;letter-spacing:.07em;color:#64748b;font-weight:700;}
      .metric-value {font-size:30px;font-weight:800;color:#10213d;margin-top:7px;}
      .metric-note {font-size:12px;color:#64748b;margin-top:3px;}
      .section-heading {font-size:20px;font-weight:800;color:#10213d;margin:5px 0 3px;}
      .section-caption {font-size:13px;color:#64748b;margin-bottom:14px;}
      div[data-testid="stForm"] {background:white;border:1px solid #e5edf7;padding:18px;border-radius:16px;}
      .stButton > button, div[data-testid="stFormSubmitButton"] > button {
        border-radius:10px;font-weight:700;min-height:42px;
      }
      .small-muted {font-size:12px;color:#64748b;}
    </style>
    """,
    unsafe_allow_html=True,
)


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
        raise RuntimeError(
            "Supabase package is missing. Add 'supabase' to requirements.txt."
        )
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY) "
            "in Render Environment Variables / Streamlit secrets."
        )
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ----------------------------- Authentication --------------------------------
def show_login():
    st.markdown(
        """
        <div class="login-wrap">
          <div class="login-icon">🔐</div>
          <div class="login-title">Admin Verification</div>
          <div class="login-sub">Enter your 6-digit access code to open the Makkal Kural AI dashboard.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # OTP-style UI: six separate visual boxes, without username/name fields.
    # This verifies the configured ADMIN_ACCESS_KEY; it does not send an SMS/email OTP.
    left, center, right = st.columns([1, 1.2, 1])
    with center:
        with st.form("admin_otp_form", clear_on_submit=False):
            st.markdown("#### Enter verification code")
            otp = st.text_input(
                "6-digit code",
                type="password",
                max_chars=6,
                placeholder="• • • • • •",
                help="Enter the six-digit administrator code configured on the server.",
                label_visibility="collapsed",
            )
            st.markdown(
                """
                <style>
                  div[data-testid="stTextInput"] input {
                    text-align:center;
                    letter-spacing:.65em;
                    font-size:24px;
                    font-weight:800;
                    padding:14px 12px;
                    border-radius:12px;
                    border:1px solid #cbd5e1;
                    background:#f8fafc;
                  }
                </style>
                """,
                unsafe_allow_html=True,
            )
            submitted = st.form_submit_button(
                "Verify & Login", type="primary", use_container_width=True
            )
            if submitted:
                if not ADMIN_ACCESS_KEY:
                    st.error(
                        "Admin verification is not configured. Set ADMIN_ACCESS_KEY in "
                        "Render → your service → Environment, then redeploy."
                    )
                elif not otp or not otp.isdigit() or len(otp) != 6:
                    st.error("Enter a valid 6-digit code.")
                elif otp == ADMIN_ACCESS_KEY:
                    st.session_state["mka_admin_authenticated"] = True
                    st.rerun()
                else:
                    st.error("Incorrect verification code. Please try again.")
        st.markdown(
            '<p class="small-muted" style="text-align:center;">'
            "Secure administrator access · Keep your code private"
            "</p>",
            unsafe_allow_html=True,
        )


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
    client = get_supabase_client()
    response = client.table(TABLE_NAME).select("*").order("created_at", desc=True).execute()
    records = getattr(response, "data", None) or []
    return [normalise_complaint(item) for item in records]


def update_complaint(row: dict[str, Any], new_status: str, notes: str) -> None:
    client = get_supabase_client()
    key_column = "id" if row.get("id") is not None else (
        "tracking_id" if row.get("tracking_id") is not None else "complaint_id"
    )
    key_value = row.get(key_column)
    if key_value is None:
        raise RuntimeError("Could not find an ID field for this complaint.")

    payload: dict[str, Any] = {"status": new_status}
    # Add notes only if your table supports this column. If not, status update is
    # retried without notes so status management can still work.
    if notes.strip():
        payload["resolution_notes"] = notes.strip()

    try:
        client.table(TABLE_NAME).update(payload).eq(key_column, key_value).execute()
    except Exception:
        if "resolution_notes" not in payload:
            raise
        payload.pop("resolution_notes", None)
        client.table(TABLE_NAME).update(payload).eq(key_column, key_value).execute()


def metric_card(label: str, value: int, note: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-label">{label}</div>
          <div class="metric-value">{value}</div>
          <div class="metric-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ----------------------------- Dashboard -------------------------------------
def show_dashboard():
    with st.sidebar:
        st.markdown(
            """
            <div style="padding:12px 2px 20px;">
              <div style="font-size:13px;letter-spacing:.1em;color:#93c5fd;font-weight:700;">MAKKAL KURAL AI</div>
              <div style="font-size:23px;font-weight:800;margin-top:7px;">Admin Console</div>
              <div style="font-size:12px;opacity:.75;margin-top:4px;">Complaint operations</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        page = st.radio("NAVIGATION", ["Overview & All Complaints", "Complaint Map"], label_visibility="visible")
        st.divider()
        st.caption("Signed in as administrator")
        if st.button("Log out", use_container_width=True):
            st.session_state["mka_admin_authenticated"] = False
            st.rerun()

    st.markdown(
        """
        <div class="brand">
          <div class="brand-icon">🏛️</div>
          <div>
            <div class="brand-name">Makkal Kural AI</div>
            <div class="brand-sub">Public complaint administration dashboard</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.title("Overview & All Complaints" if page == "Overview & All Complaints" else "Complaint Location Map")
    st.caption("Review incoming reports, track progress, and manage complaint status.")

    try:
        rows = fetch_complaints()
    except Exception as exc:
        st.error(f"Could not load complaints: {exc}")
        st.info(
            "Check that SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY), "
            "the table name, and database permissions are configured correctly."
        )
        st.stop()

    if not rows:
        st.info("No complaints found in the database yet.")
        if st.button("Refresh complaints"):
            st.rerun()
        return

    df = pd.DataFrame(rows)
    status_series = df["_status"].astype(str).str.lower()
    total = len(df)
    pending = int(status_series.isin(["pending", "new", "received"]).sum())
    in_progress = int(status_series.isin(["in progress", "in-progress", "processing", "under review"]).sum())
    resolved = int(status_series.isin(["resolved", "closed", "completed"]).sum())

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        metric_card("Total complaints", total, "All submitted reports")
    with m2:
        metric_card("Pending", pending, "Awaiting action")
    with m3:
        metric_card("In progress", in_progress, "Currently being handled")
    with m4:
        metric_card("Resolved", resolved, "Marked complete")

    st.write("")
    if page == "Complaint Map":
        show_map(rows)
        return

    st.markdown('<div class="section-heading">All Complaints</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-caption">Search by tracking ID, category, location, or complaint text. '
        "Use the filters to narrow the list.</div>",
        unsafe_allow_html=True,
    )

    f1, f2, f3 = st.columns([2, 1, 1])
    with f1:
        search_text = st.text_input("Search complaints", placeholder="Tracking ID, location, category, keywords…")
    with f2:
        categories = sorted({r["_category"] for r in rows if r["_category"]})
        category_filter = st.selectbox("Category", ["All categories"] + categories)
    with f3:
        status_values = sorted({r["_status"] for r in rows if r["_status"]})
        status_filter = st.selectbox("Status", ["All statuses"] + status_values)

    filtered = rows
    if search_text.strip():
        q = search_text.strip().lower()
        filtered = [
            r for r in filtered
            if q in " ".join([
                r["_tracking_id"], r["_category"], r["_description"], r["_location"], r["_status"]
            ]).lower()
        ]
    if category_filter != "All categories":
        filtered = [r for r in filtered if r["_category"] == category_filter]
    if status_filter != "All statuses":
        filtered = [r for r in filtered if r["_status"] == status_filter]

    st.caption(f"Showing {len(filtered)} of {len(rows)} complaints")

    display_rows = []
    for r in filtered:
        display_rows.append({
            "Tracking ID": r["_tracking_id"],
            "Category": r["_category"],
            "Location": r["_location"] or "Not provided",
            "Status": r["_status"],
            "Submitted": str(r["_created_at"] or "Unknown")[:19].replace("T", " "),
            "Map pin": "Available" if r["_latitude"] is not None and r["_longitude"] is not None else "No coordinates",
        })
    st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)

    st.markdown('<div class="section-heading">Update a complaint</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-caption">Select a complaint to change its status. '
        "A status update is saved to the database.</div>",
        unsafe_allow_html=True,
    )
    if filtered:
        labels = {
            f'{r["_tracking_id"]} · {r["_category"]} · {r["_status"]}': r
            for r in filtered
        }
        selected_label = st.selectbox("Select complaint", list(labels.keys()))
        selected = labels[selected_label]
        with st.form("update_complaint_form"):
            current_status = selected["_status"]
            status_options = STATUSES.copy()
            if current_status not in status_options:
                status_options.insert(0, current_status)
            default_index = status_options.index(current_status) if current_status in status_options else 0
            new_status = st.selectbox("New status", status_options, index=default_index)
            notes = st.text_area(
                "Resolution / admin notes (optional)",
                value=selected["_resolution_notes"],
                placeholder="Add a short update for the administration team…",
            )
            save = st.form_submit_button("Save complaint update", type="primary")
            if save:
                try:
                    update_complaint(selected, new_status, notes)
                    st.success("Complaint updated successfully.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not update complaint: {exc}")
                    st.caption(
                        "If the status column or ID column in your schema has a different name, "
                        "adjust update_complaint() to match your database."
                    )

    st.markdown('<div class="section-heading">Complaint locations</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-caption">Complaints with saved coordinates appear as pins on the map.</div>',
        unsafe_allow_html=True,
    )
    show_map(filtered)


def show_map(rows: list[dict[str, Any]]) -> None:
    mappable = [
        r for r in rows
        if r.get("_latitude") is not None and r.get("_longitude") is not None
    ]
    if folium is None or st_folium is None:
        st.warning("Map packages are not installed. Add folium and streamlit-folium to requirements.txt.")
        return
    if not mappable:
        st.info(
            "No complaint coordinates are saved yet. New complaints must store latitude and longitude "
            "in the database for their map pins to appear."
        )
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
        <div style="font-family:Arial;min-width:190px;">
          <b>{row["_tracking_id"]}</b><br>
          <b>Category:</b> {row["_category"]}<br>
          <b>Status:</b> {row["_status"]}<br>
          <b>Location:</b> {row["_location"] or "Not provided"}<br>
          <b>Complaint:</b> {row["_description"][:240]}
        </div>
        """
        folium.Marker(
            location=[row["_latitude"], row["_longitude"]],
            tooltip=f'{row["_tracking_id"]} · {row["_category"]}',
            popup=folium.Popup(popup_html, max_width=320),
            icon=folium.Icon(
                color="green" if row["_status"].lower() in ["resolved", "closed", "completed"]
                else "orange" if row["_status"].lower() in ["in progress", "in-progress", "processing"]
                else "red",
                icon="info-sign",
            ),
        ).add_to(complaint_map)

    st_folium(complaint_map, use_container_width=True, height=520, returned_objects=[])


# -------------------------------- Main ----------------------------------------
if not ADMIN_ACCESS_KEY:
    st.warning(
        "ADMIN_ACCESS_KEY is not configured. Add it in Render → your web service → "
        "Environment, then redeploy. Do not hard-code the secret in this file."
    )

if st.session_state.get("mka_admin_authenticated", False):
    show_dashboard()
else:
    show_login()
