"""
Makkal Kural AI — Database Layer (Supabase Integration)

Public helpers
--------------
get_supabase_client()            -> Supabase client or None
database_configured()            -> True when URL + key are available
init_db()                        -> True when the complaints table is reachable
save_complaint(payload)          -> bool
get_complaint(tracking_id)       -> list[dict]  (partial, case-insensitive match)
get_complaint_by_tracking_id(id) -> list[dict]  (exact match)
fetch_complaints()               -> (rows, error_message_or_None)
get_all_complaints()             -> list[dict]
update_status(id, status, note)  -> bool

Credentials are read from Streamlit secrets or environment variables on the
server only. They are never printed or sent to the browser.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import streamlit as st

try:
    from supabase import create_client
except ImportError:  # pragma: no cover - depends on the installed packages
    create_client = None


def get_setting(name: str, default: str = "") -> str:
    """Read Streamlit secrets first, then environment variables."""
    try:
        if hasattr(st, "secrets") and name in st.secrets:
            val = st.secrets.get(name, None)
            if val is not None and str(val).strip():
                return str(val).strip()
    except Exception:
        pass
    return os.getenv(name, default).strip()


SUPABASE_URL = get_setting("SUPABASE_URL")
SUPABASE_KEY = get_setting("SUPABASE_SERVICE_ROLE_KEY") or get_setting("SUPABASE_KEY")
TABLE_NAME = get_setting("SUPABASE_TABLE", "complaints")

# Supabase/PostgREST returns at most 1000 rows per request by default, so
# complaints are read in pages of this size.
PAGE_SIZE = 1000
MAX_ROWS = 20000

_client = None


def database_configured() -> bool:
    """True when the Supabase library and both credentials are available."""
    return bool(create_client is not None and SUPABASE_URL and SUPABASE_KEY)


def get_supabase_client():
    """Return a cached Supabase client, or None if it cannot be created."""
    global _client
    if _client is not None:
        return _client
    if not database_configured():
        return None
    try:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None
    return _client


# Backwards-compatible name used by earlier versions of this module.
_get_client = get_supabase_client


def _not_ready_message() -> str:
    if create_client is None:
        return "The Supabase client library is not installed. Check requirements.txt."
    if not SUPABASE_URL or not SUPABASE_KEY:
        return (
            "Database is not configured. Set SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY for the server."
        )
    return "Could not create the database client. Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."


def _require_client():
    client = get_supabase_client()
    if client is None:
        st.error(_not_ready_message())
    return client


def _clean(value, default: str = "") -> str:
    text = "" if value is None else str(value).strip()
    return text or default


def init_db() -> bool:
    """Check that the complaints table is reachable.

    The table itself is created by running supabase/schema.sql in the Supabase
    SQL editor; the client library cannot run DDL statements.
    """
    client = _require_client()
    if not client:
        return False
    try:
        client.table(TABLE_NAME).select("tracking_id").limit(1).execute()
        return True
    except Exception as e:
        st.error(
            f"Database table '{TABLE_NAME}' is not reachable. "
            f"Run supabase/schema.sql in the Supabase SQL editor. Details: {e}"
        )
        return False


def save_complaint(payload: dict) -> bool:
    """Saves a new complaint with generated tracking ID & coordinates to Supabase."""
    client = _require_client()
    if not client:
        return False
    try:
        description = _clean(payload.get("description") or payload.get("complaint_text"))
        db_payload = {
            "tracking_id": payload.get("tracking_id"),
            "category": _clean(payload.get("category"), "Other"),
            "description": description,
            "complaint_text": description,
            "location": _clean(payload.get("location"), "Not provided"),
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
            "status": _clean(payload.get("status"), "Submitted"),
            # schema.sql defines created_at as text with an empty default, so
            # the timestamp has to be supplied here or every row has no date.
            "created_at": _clean(payload.get("created_at"))
            or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        for optional in ("source_id", "name", "village", "district"):
            if payload.get(optional):
                db_payload[optional] = payload[optional]
        client.table(TABLE_NAME).insert(db_payload).execute()
        return True
    except Exception as e:
        st.error(f"Database error while saving: {e}")
        return False


def get_complaint(tracking_id: str) -> list[dict]:
    """Retrieves complaints whose tracking ID contains the given text (case-insensitive)."""
    client = _require_client()
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


def get_complaint_by_tracking_id(tracking_id: str) -> list[dict]:
    """Retrieves the complaint whose tracking ID matches exactly.

    The ID is tried as typed and then upper-cased, so "mkai-123456" finds
    "MKAI-123456" without exposing other people's complaints through partial
    matches.
    """
    tid = _clean(tracking_id)
    if not tid:
        return []
    client = _require_client()
    if not client:
        return []
    try:
        for candidate in dict.fromkeys([tid, tid.upper()]):
            res = (
                client.table(TABLE_NAME)
                .select("*")
                .eq("tracking_id", candidate)
                .execute()
            )
            rows = getattr(res, "data", []) or []
            if rows:
                return rows
        return []
    except Exception as e:
        st.error(f"Database error while searching: {e}")
        return []


def fetch_complaints() -> tuple[list[dict], str | None]:
    """Fetch every complaint, newest first.

    Returns (rows, error). `error` is None on success, so callers can tell an
    empty table apart from a failed query.
    """
    client = get_supabase_client()
    if client is None:
        return [], _not_ready_message()

    last_error = ""
    # `id` gives a stable order for paging; fall back if the column is absent.
    for order_col in ("id", "created_at", None):
        rows: list[dict] = []
        try:
            start = 0
            while start < MAX_ROWS:
                query = client.table(TABLE_NAME).select("*")
                if order_col:
                    query = query.order(order_col, desc=True)
                res = query.range(start, start + PAGE_SIZE - 1).execute()
                batch = getattr(res, "data", []) or []
                rows.extend(batch)
                if len(batch) < PAGE_SIZE:
                    break
                start += PAGE_SIZE
            return rows, None
        except Exception as e:
            last_error = str(e)
    return [], f"Database error while fetching complaints: {last_error}"


def get_all_complaints() -> list[dict]:
    """Fetches all registered complaints, newest first."""
    rows, error = fetch_complaints()
    if error:
        st.error(error)
    return rows


def update_status(tracking_id: str, new_status: str, notes: str) -> bool:
    """Updates the status and resolution note of one complaint.

    schema.sql names the note column `resolution_note`; `resolution_notes` is
    tried as a fallback for databases created with the other spelling.
    """
    client = _require_client()
    if not client:
        return False
    note = _clean(notes)
    status = _clean(new_status)
    if not tracking_id or not status:
        st.error("A tracking ID and a status are required.")
        return False

    def _run(values: dict):
        return client.table(TABLE_NAME).update(values).eq("tracking_id", tracking_id).execute()

    try:
        for column in ("resolution_note", "resolution_notes"):
            try:
                res = _run({"status": status, column: note})
            except Exception as e:
                if "resolution_note" in str(e):
                    continue  # this spelling does not exist; try the next one
                raise
            if not (getattr(res, "data", None) or []):
                st.error(f"No complaint was found with tracking ID {tracking_id}.")
                return False
            return True

        # Neither note column exists: still save the status.
        res = _run({"status": status})
        if not (getattr(res, "data", None) or []):
            st.error(f"No complaint was found with tracking ID {tracking_id}.")
            return False
        st.warning("Status saved, but the database has no resolution note column, so the note was not stored.")
        return True
    except Exception as e:
        st.error(f"Database error while updating status: {e}")
        return False
