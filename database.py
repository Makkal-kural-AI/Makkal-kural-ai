"""
Makkal Kural AI — Database Layer (Supabase Integration)
Provides: save_complaint(), get_complaint(), get_all_complaints(), update_status()
"""

import os
import streamlit as st

try:
    from supabase import create_client
except ImportError:
    create_client = None


def get_setting(name: str, default: str = "") -> str:
    try:
        val = st.secrets.get(name, None)
        if val is not None and str(val).strip():
            return str(val).strip()
    except Exception:
        pass
    return os.getenv(name, default).strip()


SUPABASE_URL = get_setting("SUPABASE_URL")
SUPABASE_KEY = get_setting("SUPABASE_SERVICE_ROLE_KEY") or get_setting("SUPABASE_KEY")
TABLE_NAME = get_setting("SUPABASE_TABLE", "complaints")


def _get_client():
    if create_client is None or not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


def save_complaint(payload: dict) -> bool:
    """Saves a new complaint with generated tracking ID & coordinates to Supabase."""
    client = _get_client()
    if not client:
        return False
    try:
        client.table(TABLE_NAME).insert(payload).execute()
        return True
    except Exception as e:
        st.error(f"Database error while saving: {e}")
        return False


def get_complaint(tracking_id: str) -> list[dict]:
    """Retrieves complaint details matching the given tracking ID."""
    client = _get_client()
    if not client:
        return []
    try:
        res = (
            client.table(TABLE_NAME)
            .select("*")
            .ilike("tracking_id", f"%{tracking_id}%")
            .execute()
        )
        return getattr(res, "data", []) or []
    except Exception as e:
        st.error(f"Database error while searching: {e}")
        return []


def get_all_complaints() -> list[dict]:
    """Fetches all registered complaints ordered by creation time."""
    client = _get_client()
    if not client:
        return []
    try:
        res = (
            client.table(TABLE_NAME)
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return getattr(res, "data", []) or []
    except Exception as e:
        st.error(f"Database error while fetching complaints: {e}")
        return []


def update_status(tracking_id: str, new_status: str, notes: str) -> bool:
    """Updates the status and resolution notes of a complaint in Supabase."""
    client = _get_client()
    if not client:
        return False
    try:
        payload = {"status": new_status, "resolution_notes": notes.strip()}
        client.table(TABLE_NAME).update(payload).eq(
            "tracking_id", tracking_id
        ).execute()
        return True
    except Exception as e:
        st.error(f"Database error while updating status: {e}")
        return False
