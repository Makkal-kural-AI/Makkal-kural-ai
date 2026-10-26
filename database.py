
import os
import uuid
from datetime import datetime
from functools import lru_cache

from supabase import Client, create_client


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Create the server-side Supabase client from deployment secrets."""

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        raise RuntimeError(
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )

    return create_client(url, key)


def init_db():
    """Retained for compatibility; create tables with supabase/schema.sql."""
    get_supabase_client()


def save_complaint(
    complaint_text=None,
    category="Other",
    location="Not provided",
    source_id=None,
    *,
    name="",
    description=None,
    village=None,
    district=None,
    latitude=None,
    longitude=None,
):
    """Save a complaint and return (tracking_id, created_at)."""

    init_db()

    text = str(description or complaint_text or "").strip()

    if not text:
        raise ValueError("Complaint text cannot be empty.")

    category = str(category or "Other").strip() or "Other"
    name = str(name or "").strip()
    village = str(village or location or "Not provided").strip()
    district = str(district or "").strip()

    if not village:
        village = "Not provided"

    full_location = (
        f"{village}, {district}" if district else village
    )

    if source_id is not None:
        source_id = str(source_id).strip() or None

    client = get_supabase_client()

    if source_id:
        existing = (
            client.table("complaints")
            .select("tracking_id, created_at")
            .eq("source_id", source_id)
            .limit(1)
            .execute()
            .data
        )
        if existing:
            return existing[0]["tracking_id"], existing[0]["created_at"]

    tracking_id = "MKAI-" + uuid.uuid4().hex[:10].upper()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record = {
        "tracking_id": tracking_id,
        "complaint_text": text,
        "category": category,
        "location": full_location,
        "created_at": created_at,
        "status": "Submitted",
        "source_id": source_id,
        "name": name,
        "description": text,
        "village": village,
        "district": district,
        "latitude": latitude,
        "longitude": longitude,
    }

    try:
        client.table("complaints").insert(record).execute()
    except Exception:
        if source_id:
            existing = (
                client.table("complaints")
                .select("tracking_id, created_at")
                .eq("source_id", source_id)
                .limit(1)
                .execute()
                .data
            )
            if existing:
                return existing[0]["tracking_id"], existing[0]["created_at"]
        raise

    return tracking_id, created_at


def get_complaint(tracking_id):
    """Find one complaint using its tracking ID."""

    init_db()

    rows = (
        get_supabase_client()
        .table("complaints")
        .select("*")
        .eq("tracking_id", str(tracking_id).strip())
        .limit(1)
        .execute()
        .data
    )

    if not rows:
        return None

    complaint = rows[0]
    complaint["description"] = (
        complaint.get("description") or complaint.get("complaint_text") or ""
    )
    complaint["village"] = (
        complaint.get("village") or complaint.get("location") or "Not provided"
    )
    complaint["district"] = complaint.get("district") or ""
    return complaint


def get_complaint_by_tracking_id(tracking_id):
    """Alternative function name for tracking a complaint."""
    return get_complaint(tracking_id)


def get_all_complaints():
    """Return all complaints, newest first."""

    init_db()
    client = get_supabase_client()
    rows = []
    page_size = 1000
    start = 0

    while True:
        page = (
            client.table("complaints")
            .select("*")
            .order("id", desc=True)
            .range(start, start + page_size - 1)
            .execute()
            .data
        )
        rows.extend(page)
        if len(page) < page_size:
            break
        start += page_size

    results = []
    for row in rows:
        item = dict(row)
        item["description"] = (
            item.get("description") or item.get("complaint_text") or ""
        )
        item["village"] = item.get("village") or item.get("location") or "Not provided"
        item["district"] = item.get("district") or ""
        results.append(item)
    return results


def update_status(tracking_id, new_status):
    """Update a complaint's status."""

    allowed_statuses = {
        "Pending",
        "Submitted",
        "In Progress",
        "Resolved",
    }

    if new_status not in allowed_statuses:
        raise ValueError("Invalid complaint status.")

    init_db()

    rows = (
        get_supabase_client()
        .table("complaints")
        .update({"status": new_status})
        .eq("tracking_id", str(tracking_id).strip())
        .select("tracking_id")
        .execute()
        .data
    )
    return bool(rows)


if __name__ == "__main__":
    init_db()
    print("Supabase connection is ready!")
