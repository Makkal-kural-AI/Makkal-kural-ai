"""
dashboard.py - Makkal Kural AI complaint pages and admin tools.

Two ways to use this file:
  * Standalone:   python -m streamlit run dashboard.py
  * From app.py:  app.py imports the render_* functions below and calls them
                  inside its own pages (the homepage design is not touched).

Public pages  : submit a complaint, track a complaint, public list + map.
Admin pages   : dashboard, all complaints (full details), update status.
                Everything admin-only sits behind the admin login.

Admin accounts are NEVER stored in this file. Put them in the ADMIN_USERS
environment variable (JSON) or in Streamlit secrets under [admins].
See the setup guide for the exact format.

Make a password hash:   python dashboard.py --make-hash
"""

import hashlib
import hmac
import html
import json
import os
import sys
import time

import pandas as pd
import streamlit as st

from classifier import COMPLAINT_CATEGORIES, classify_complaint
from database import (
    get_all_complaints,
    get_complaint_by_tracking_id,
    init_db,
    save_complaint as save_to_database,
    update_status,
)

# Categories come from classifier.py so the two files can never disagree.
CATEGORIES = list(COMPLAINT_CATEGORIES.keys())
STATUSES = ["Pending", "In Progress", "Resolved"]
STATUS_COLORS = {"Pending": "red", "In Progress": "orange", "Resolved": "green"}
STATUS_ICONS = {"Pending": "🔴", "In Progress": "🟠", "Resolved": "🟢"}

MAX_ADMINS = 4
MAX_LOGIN_FAILURES = 5
LOCKOUT_SECONDS = 60
DATA_TTL_SECONDS = 15           # how long loaded complaints are reused
DUPLICATE_SUBMIT_SECONDS = 30   # same complaint twice in a row = one record
HASH_PREFIX = "pbkdf2_sha256"
HASH_ROUNDS = 200_000

DATA_COLUMNS = [
    "tracking_id",
    "complaint_text",
    "location",
    "category",
    "status",
    "submitted_at",
    "latitude",
    "longitude",
]


# ==========================================================================
# Small helpers
# ==========================================================================
def _log(message):
    """Log to the server console. Never pass secrets or raw exceptions."""
    print(f"[dashboard] {message}", file=sys.stderr)


def _show_error(action, error):
    """Show a friendly error without leaking connection details."""
    if isinstance(error, (RuntimeError, ValueError)):
        # These are our own readable messages, e.g. "Set SUPABASE_URL ...".
        st.error(f"{action}: {error}")
    else:
        st.error(
            f"{action}. Please check the database settings "
            "(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY) and try again."
        )
    _log(f"{action} ({type(error).__name__})")


def _flash(kind, message):
    """Keep a message alive across st.rerun()."""
    st.session_state["mk_flash"] = (kind, message)


def _show_flash():
    item = st.session_state.pop("mk_flash", None)
    if item:
        kind, message = item
        getattr(st, kind)(message)


# ==========================================================================
# Data loading (uses the existing database.py functions)
# ==========================================================================
@st.cache_resource(show_spinner=False)
def _ensure_database():
    init_db()
    return True


@st.cache_data(ttl=DATA_TTL_SECONDS, show_spinner=False)
def _load_rows():
    _ensure_database()
    return get_all_complaints()


def refresh_data():
    """Forget cached complaints so the next page load reads the database."""
    _load_rows.clear()


def _normalise(df):
    """Make every page see the same column names, whatever the table uses."""
    if df.empty:
        return pd.DataFrame(columns=DATA_COLUMNS)

    df = df.copy()

    # The Supabase table calls the date column created_at.
    if "submitted_at" not in df.columns:
        df["submitted_at"] = df["created_at"] if "created_at" in df.columns else ""
    if "complaint_text" not in df.columns:
        df["complaint_text"] = df["description"] if "description" in df.columns else ""
    for column in DATA_COLUMNS:
        if column not in df.columns:
            df[column] = None

    df["complaint_text"] = df["complaint_text"].fillna("")
    df["location"] = df["location"].fillna("Not provided")
    df["category"] = df["category"].fillna("Other")
    # database.py first saves new rows as "Submitted"; that means Pending.
    df["status"] = (
        df["status"].fillna("Pending").replace({"Submitted": "Pending", "": "Pending"})
    )

    # Only keep coordinates that are real numbers in the valid range.
    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")
    valid = (
        lat.between(-90, 90)
        & lon.between(-180, 180)
        & ~((lat == 0) & (lon == 0))   # (0, 0) is an "empty" placeholder
    )
    df["latitude"] = lat.where(valid)
    df["longitude"] = lon.where(valid)

    return df[DATA_COLUMNS].reset_index(drop=True)


def load_complaints():
    return _normalise(pd.DataFrame(_load_rows()))


# ==========================================================================
# Admin login (accounts come from environment variables / Streamlit secrets)
# ==========================================================================
def make_password_hash(password, rounds=HASH_ROUNDS):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"{HASH_PREFIX}${rounds}${salt.hex()}${digest.hex()}"


def _password_matches(stored, supplied):
    """stored is either a pbkdf2 hash (recommended) or a plain password."""
    if stored.startswith(HASH_PREFIX + "$"):
        try:
            _, rounds, salt_hex, hash_hex = stored.split("$")
            candidate = hashlib.pbkdf2_hmac(
                "sha256",
                supplied.encode("utf-8"),
                bytes.fromhex(salt_hex),
                int(rounds),
            )
            return hmac.compare_digest(candidate.hex(), hash_hex)
        except ValueError:
            return False
    return hmac.compare_digest(stored.encode("utf-8"), supplied.encode("utf-8"))


def _load_admins():
    """Return ({username: password_or_hash}, problem_message_or_None)."""
    admins = {}
    problem = None

    try:
        secret_admins = st.secrets.get("admins")
        if secret_admins:
            admins.update({str(k): str(v) for k, v in dict(secret_admins).items()})
    except Exception:
        pass  # no secrets file on this server, which is normal on Render

    raw = os.environ.get("ADMIN_USERS", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("not an object")
            admins.update({str(k): str(v) for k, v in parsed.items()})
        except ValueError:
            problem = (
                "ADMIN_USERS is not valid JSON. Example: "
                '{"name1": "password1", "name2": "password2"}'
            )

    admins = {k.strip(): v for k, v in admins.items() if k.strip() and v}
    if len(admins) > MAX_ADMINS:
        problem = f"Only the first {MAX_ADMINS} admin accounts are used."
        admins = dict(list(admins.items())[:MAX_ADMINS])
    return admins, problem


def _is_admin():
    return bool(st.session_state.get("mk_admin_user"))


def _require_admin():
    """Show the login form unless an admin is logged in. True = allowed in."""
    if _is_admin():
        return True

    st.subheader("🔐 Admin login")
    st.caption("Only authorised team members can open the admin pages.")

    admins, problem = _load_admins()
    if problem:
        st.warning(problem)
    if not admins:
        st.error(
            "Admin login is not set up on this server yet. The project owner "
            "must add the ADMIN_USERS setting (see the setup guide)."
        )
        return False

    wait = int(st.session_state.get("mk_locked_until", 0) - time.time())
    if wait > 0:
        st.error(f"Too many failed attempts. Please try again in {wait} seconds.")

    with st.form("mk_login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        clicked = st.form_submit_button("Log in")

    if clicked and wait <= 0:
        stored = admins.get(username.strip())
        # Always do one hash check so the time taken does not reveal
        # whether the username exists.
        reference = stored if stored else make_password_hash("not-a-real-account")
        matches = _password_matches(reference, password)

        if stored and matches:
            st.session_state["mk_admin_user"] = username.strip()
            st.session_state["mk_login_failures"] = 0
            st.rerun()
        else:
            failures = st.session_state.get("mk_login_failures", 0) + 1
            st.session_state["mk_login_failures"] = failures
            if failures >= MAX_LOGIN_FAILURES:
                st.session_state["mk_locked_until"] = time.time() + LOCKOUT_SECONDS
                st.session_state["mk_login_failures"] = 0
            st.error("Incorrect username or password.")
    return False


def _admin_bar():
    left, right = st.columns([4, 1])
    left.caption(f"Logged in as **{st.session_state.get('mk_admin_user')}**")
    if right.button("Log out", key="mk_logout"):
        for key in ("mk_admin_user", "mk_flash"):
            st.session_state.pop(key, None)
        st.rerun()


# ==========================================================================
# Public page: submit a complaint
# ==========================================================================
def _capture_voice():
    """Use the existing get_voice_complaint() and report problems politely."""
    try:
        from voice_ai import get_voice_complaint
    except Exception as error:
        _log(f"voice module unavailable ({type(error).__name__})")
        st.session_state["mk_voice_message"] = (
            "Voice input is not available on this server. "
            "Please type your complaint."
        )
        return

    try:
        with st.spinner("Listening... Please speak in Tamil or English."):
            voice_text = get_voice_complaint()
    except Exception as error:
        _log(f"voice capture failed ({type(error).__name__})")
        st.session_state["mk_voice_message"] = (
            "The microphone or speech model could not be used. "
            "Please type your complaint."
        )
        return

    if voice_text:
        st.session_state["mk_complaint_text"] = voice_text
        st.session_state["mk_voice_message"] = "Voice complaint captured successfully."
        st.rerun()
    else:
        st.session_state["mk_voice_message"] = (
            "Voice was not detected. Please try again or type your complaint."
        )


def _save_new_complaint(text, location):
    """Classify and save. The same complaint twice in a row is saved once."""
    signature = (text, location.lower())
    recent = st.session_state.get("mk_recent")
    if (
        recent
        and recent["signature"] == signature
        and time.time() - recent["time"] < DUPLICATE_SUBMIT_SECONDS
    ):
        return recent["tracking_id"], recent["category"]

    _ensure_database()
    category = classify_complaint(text)
    tracking_id, _ = save_to_database(text, category, location)

    try:
        update_status(tracking_id, "Pending")
    except Exception as error:  # the page still shows Pending either way
        _log(f"could not set Pending ({type(error).__name__})")

    refresh_data()
    st.session_state["mk_recent"] = {
        "signature": signature,
        "time": time.time(),
        "tracking_id": tracking_id,
        "category": category,
    }
    return tracking_id, category


def render_submit(show_title=True):
    if show_title:
        st.title("Submit a Complaint")
    st.write("Report a public issue in your village or local area.")

    st.session_state.setdefault("mk_complaint_text", "")
    st.session_state.setdefault("mk_location", "")
    st.session_state.setdefault("mk_voice_message", "")

    saved = st.session_state.get("mk_last_saved")
    if saved:
        st.success("Complaint saved successfully!")
        st.subheader("Your Complaint Details")
        st.write(f"**Tracking ID:** {saved['tracking_id']}")
        st.write(f"**Category:** {saved['category']}")
        st.write("**Status:** Pending")
        st.info("Please save your tracking ID to check your complaint later.")
        if st.button("Submit another complaint", key="mk_new_complaint"):
            st.session_state["mk_complaint_text"] = ""
            st.session_state["mk_location"] = ""
            st.session_state["mk_voice_message"] = ""
            st.session_state.pop("mk_last_saved", None)
            st.rerun()
        return

    st.subheader("1. Enter your complaint")

    if st.button("🎤 Speak Your Complaint", key="mk_voice_button"):
        _capture_voice()

    if st.session_state["mk_voice_message"]:
        st.info(st.session_state["mk_voice_message"])

    complaint_text = st.text_area(
        "Complaint details",
        key="mk_complaint_text",
        placeholder=(
            "Example: Garbage has not been collected "
            "in our village for three days."
        ),
        height=130,
    )

    if complaint_text.strip():
        st.success(f"Detected category: {classify_complaint(complaint_text)}")

    st.subheader("2. Enter your location")
    location = st.text_input(
        "Village / Area",
        key="mk_location",
        placeholder="Example: Kovilpatti Village",
    )

    if st.button("Submit Complaint", type="primary", key="mk_submit"):
        if not complaint_text.strip():
            st.error("Please enter or speak your complaint.")
        elif not location.strip():
            st.error("Please enter your village or location.")
        else:
            try:
                tracking_id, category = _save_new_complaint(
                    complaint_text.strip(), location.strip()
                )
            except Exception as error:
                _show_error("Could not save your complaint", error)
            else:
                st.session_state["mk_last_saved"] = {
                    "tracking_id": tracking_id,
                    "category": category,
                }
                st.session_state["mk_voice_message"] = ""
                st.rerun()


# ==========================================================================
# Public page: track one complaint with its tracking ID
# ==========================================================================
def render_tracking(show_title=True):
    if show_title:
        st.title("🔎 Track Your Complaint")
    st.write("Enter the tracking ID you received when you submitted your complaint.")

    with st.form("mk_track_form"):
        tracking_id = st.text_input("Tracking ID", placeholder="Example: MKAI-1A2B3C4D5E")
        clicked = st.form_submit_button("Check status")

    if not clicked:
        return
    if not tracking_id.strip():
        st.error("Please enter your tracking ID.")
        return

    try:
        _ensure_database()
        complaint = get_complaint_by_tracking_id(tracking_id.strip())
    except Exception as error:
        _show_error("Could not look up your complaint", error)
        return

    if not complaint:
        st.error("No complaint was found with that tracking ID. Please check it and try again.")
        return

    status = complaint.get("status") or "Pending"
    if status == "Submitted":
        status = "Pending"
    text = complaint.get("complaint_text") or complaint.get("description") or ""
    submitted = complaint.get("submitted_at") or complaint.get("created_at") or ""

    st.success("Complaint found.")
    st.write(f"**Tracking ID:** {complaint.get('tracking_id')}")
    st.write(f"**Status:** {STATUS_ICONS.get(status, '')} {status}")
    st.write(f"**Category:** {complaint.get('category') or 'Other'}")
    st.write(f"**Location:** {complaint.get('location') or 'Not provided'}")
    st.write(f"**Submitted:** {submitted}")
    st.write(f"**Your complaint:** {text}")


# ==========================================================================
# Public page: other people's complaints (no private details) + map
# ==========================================================================
def _public_view(df):
    """Only safe columns: no complaint text, no full tracking ID."""
    view = pd.DataFrame(
        {
            "Reference": "…" + df["tracking_id"].astype(str).str[-4:],
            "Category": df["category"],
            "Location": df["location"],
            "Status": df["status"],
            "Date": df["submitted_at"].astype(str).str[:10],
        }
    )
    return view


def _render_map(df):
    points = df.dropna(subset=["latitude", "longitude"])

    if points.empty:
        st.info(
            "The map shows a complaint once it has a verified latitude and "
            "longitude. No complaint has coordinates yet, so there is nothing "
            "to plot. Complaints are still listed by location name."
        )
        return

    st.caption("🔴 Pending   🟠 In Progress   🟢 Resolved")

    try:
        import folium
        from streamlit_folium import st_folium

        centre = [points["latitude"].mean(), points["longitude"].mean()]
        fmap = folium.Map(location=centre, zoom_start=12)

        for row in points.itertuples():
            color = STATUS_COLORS.get(row.status, "blue")
            # Public popup: category, status and place name only.
            popup = (
                f"{html.escape(str(row.category))} - {html.escape(str(row.status))}"
                f"<br>{html.escape(str(row.location))}"
            )
            folium.CircleMarker(
                location=[row.latitude, row.longitude],
                radius=8,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.8,
                tooltip=str(row.status),
                popup=folium.Popup(popup, max_width=250),
            ).add_to(fmap)

        if len(points) > 1:
            fmap.fit_bounds(
                [
                    [points["latitude"].min(), points["longitude"].min()],
                    [points["latitude"].max(), points["longitude"].max()],
                ]
            )

        try:
            st_folium(fmap, height=480, use_container_width=True,
                      returned_objects=[], key="mk_public_map")
        except TypeError:
            st_folium(fmap, height=480, returned_objects=[], key="mk_public_map")
    except Exception as error:
        _log(f"folium map unavailable ({type(error).__name__})")
        st.map(
            points.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]]
        )
        st.caption("Basic map shown (colours need the folium package).")


def render_public(show_title=True):
    if show_title:
        st.title("📋 Public Complaints")
    st.caption("Complaint details are private. Only category, place and status are shown here.")

    try:
        df = load_complaints()
    except Exception as error:
        _show_error("Could not load complaints", error)
        return

    if df.empty:
        st.info("No complaints have been submitted yet.")
        return

    list_tab, map_tab = st.tabs(["Complaints list", "Map"])

    with list_tab:
        col1, col2 = st.columns(2)
        extra = sorted(set(df["category"]) - set(CATEGORIES))
        category = col1.selectbox("Filter by category", ["All"] + CATEGORIES + extra, key="mk_pub_cat")
        status = col2.selectbox("Filter by status", ["All"] + STATUSES, key="mk_pub_status")

        shown = df
        if category != "All":
            shown = shown[shown["category"] == category]
        if status != "All":
            shown = shown[shown["status"] == status]

        st.write(f"Complaints found: {len(shown)}")
        st.dataframe(_public_view(shown), hide_index=True)

    with map_tab:
        _render_map(df)


# ==========================================================================
# Admin pages
# ==========================================================================
def _filter_controls(df, prefix):
    col1, col2 = st.columns(2)
    extra = sorted(set(df["category"]) - set(CATEGORIES))
    category = col1.selectbox(
        "Filter by category", ["All"] + CATEGORIES + extra, key=f"mk_{prefix}_cat"
    )
    status = col2.selectbox(
        "Filter by status", ["All"] + STATUSES, key=f"mk_{prefix}_status"
    )
    query = st.text_input(
        "Search by tracking ID, location or complaint text", key=f"mk_{prefix}_search"
    ).strip()

    shown = df
    if category != "All":
        shown = shown[shown["category"] == category]
    if status != "All":
        shown = shown[shown["status"] == status]
    if query:
        match = (
            shown["tracking_id"].astype(str).str.contains(query, case=False, na=False, regex=False)
            | shown["location"].astype(str).str.contains(query, case=False, na=False, regex=False)
            | shown["complaint_text"].astype(str).str.contains(query, case=False, na=False, regex=False)
        )
        shown = shown[match]
    return shown


def _admin_table(shown):
    columns = ["tracking_id", "complaint_text", "location", "category", "submitted_at", "status"]
    st.dataframe(shown[columns], hide_index=True)


def _admin_overview(df):
    if st.button("🔄 Refresh data", key="mk_refresh"):
        refresh_data()
        st.rerun()

    if df.empty:
        st.info("No complaints submitted yet. New complaints will appear here.")
        return

    total = len(df)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Complaints", total)
    col2.metric("Pending", int((df["status"] == "Pending").sum()))
    col3.metric("In Progress", int((df["status"] == "In Progress").sum()))
    col4.metric("Resolved", int((df["status"] == "Resolved").sum()))

    st.divider()
    left, right = st.columns(2)
    with left:
        st.subheader("Complaints by Category")
        st.bar_chart(df["category"].value_counts())
    with right:
        st.subheader("Complaints by Status")
        st.bar_chart(df["status"].value_counts().reindex(STATUSES, fill_value=0))

    st.subheader("Recent Complaints")
    shown = _filter_controls(df, "ov")
    _admin_table(shown.head(10))
    if len(shown) > 10:
        st.caption(f"Showing the newest 10 of {len(shown)}. Open All Complaints to see everything.")


def _admin_complaints(df):
    if df.empty:
        st.info("No complaints available.")
        return
    shown = _filter_controls(df, "all")
    st.write(f"Complaints found: {len(shown)}")
    _admin_table(shown)


def _admin_update(df):
    if df.empty:
        st.info("There are no complaints to update.")
        return

    query = st.text_input(
        "Find a complaint (tracking ID or location)", key="mk_upd_search"
    ).strip()
    options = df
    if query:
        options = df[
            df["tracking_id"].astype(str).str.contains(query, case=False, na=False, regex=False)
            | df["location"].astype(str).str.contains(query, case=False, na=False, regex=False)
        ]
    if options.empty:
        st.warning("No complaint matches that search.")
        return

    tracking_id = st.selectbox(
        "Select complaint tracking ID", options["tracking_id"].tolist(), key="mk_upd_id"
    )
    complaint = df[df["tracking_id"] == tracking_id].iloc[0]

    st.subheader("Complaint Details")
    st.write(f"**Complaint:** {complaint['complaint_text']}")
    st.write(f"**Location:** {complaint['location']}")
    st.write(f"**Category:** {complaint['category']}")
    st.write(f"**Submitted:** {complaint['submitted_at']}")
    st.write(f"**Current status:** {complaint['status']}")

    current = complaint["status"]
    new_status = st.selectbox(
        "Choose new status",
        STATUSES,
        index=STATUSES.index(current) if current in STATUSES else 0,
        key=f"mk_upd_status_{tracking_id}",
    )

    if st.button("Save Status", type="primary", key="mk_save_status"):
        if not _is_admin():  # check again right before changing data
            st.error("Please log in as an admin first.")
            return
        try:
            updated = update_status(tracking_id, new_status)
        except Exception as error:
            _show_error("Could not update the status", error)
            return
        if updated:
            refresh_data()
            _flash("success", f"Status of {tracking_id} changed to {new_status}.")
            st.rerun()
        else:
            st.error("No complaint was updated. Please check the tracking ID.")


def _admin_page(title, show_title, body):
    """Shared wrapper: title, login gate, data loading, error handling."""
    if show_title:
        st.title(title)
    if not _require_admin():
        return
    _admin_bar()
    _show_flash()
    try:
        df = load_complaints()
    except Exception as error:
        _show_error("Could not load complaints", error)
        return
    body(df)


def render_admin_dashboard(show_title=True):
    _admin_page("📊 Admin Dashboard", show_title, _admin_overview)


def render_admin_complaints(show_title=True):
    _admin_page("📋 All Complaints (Admin)", show_title, _admin_complaints)


def render_admin_update_status(show_title=True):
    _admin_page("🔄 Update Complaint Status", show_title, _admin_update)


def render_admin(show_title=True):
    """All admin tools on one page (used by app.py's Admin Dashboard page)."""

    def body(df):
        overview, complaints, update, admin_map = st.tabs(
            ["Overview", "All Complaints", "Update Status", "Map"]
        )
        with overview:
            _admin_overview(df)
        with complaints:
            _admin_complaints(df)
        with update:
            _admin_update(df)
        with admin_map:
            _render_map(df)

    _admin_page("🛡️ Admin Dashboard", show_title, body)


# ==========================================================================
# Standalone app (python -m streamlit run dashboard.py)
# ==========================================================================
def main():
    st.set_page_config(page_title="Makkal Kural AI", page_icon="📢", layout="wide")

    st.sidebar.title("📢 Makkal Kural AI")
    st.sidebar.caption("Public Complaint Management")

    pages = {
        "Submit Complaint": render_submit,
        "Track Complaint": render_tracking,
        "Public Complaints & Map": render_public,
        "Admin Dashboard": render_admin_dashboard,
        "All Complaints": render_admin_complaints,
        "Update Status": render_admin_update_status,
    }
    page = st.sidebar.radio("Navigation", list(pages))

    st.sidebar.divider()
    st.sidebar.caption("Helping communities report local problems.")

    pages[page]()


if __name__ == "__main__":
    if sys.argv[1:2] == ["--make-hash"]:
        import getpass

        chosen = getpass.getpass("Type the new admin password: ")
        if not chosen:
            sys.exit("Password cannot be empty.")
        print("Copy this value into ADMIN_USERS:")
        print(make_password_hash(chosen))
    else:
        main()
