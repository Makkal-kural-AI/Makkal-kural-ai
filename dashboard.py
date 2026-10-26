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

