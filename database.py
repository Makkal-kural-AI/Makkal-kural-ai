import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from supabase import Client, create_client

@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in deployment environment variables.")
    return create_client(url, key)

def init_db():
    """Validate that the Supabase client is configured. Apply schema.sql in Supabase SQL Editor."""
    get_supabase_client()

def save_complaint(complaint_text=None, category="Other", location="Not provided", source_id=None, *, name="", description=None, village=None, district=None, latitude=None, longitude=None):
    """Insert a complaint and return (tracking_id, created_at). Idempotent when source_id is reused."""
    text = str(description or complaint_text or "").strip()
    if not text:
        raise ValueError("Complaint text cannot be empty.")
    category = str(category or "Other").strip() or "Other"
    village = str(village or location or "Not provided").strip() or "Not provided"
    district = str(district or "").strip()
    full_location = f"{village}, {district}" if district else village
    source_id = str(source_id).strip() or None if source_id is not None else None
    client = get_supabase_client()

    if source_id:
        existing = client.table("complaints").select("tracking_id, created_at").eq("source_id", source_id).limit(1).execute().data
        if existing:
            return existing[0]["tracking_id"], existing[0]["created_at"]

    tracking_id = "MKAI-" + uuid.uuid4().hex[:10].upper()
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record = {
        "tracking_id": tracking_id, "complaint_text": text, "description": text,
        "category": category, "location": full_location, "created_at": created_at,
        "status": "Submitted", "source_id": source_id, "name": str(name or "").strip(),
        "village": village, "district": district, "latitude": latitude, "longitude": longitude,
    }
    try:
        client.table("complaints").insert(record).execute()
    except Exception:
        # If an idempotent retry raced with an earlier insert, return the existing row.
        if source_id:
            existing = client.table("complaints").select("tracking_id, created_at").eq("source_id", source_id).limit(1).execute().data
            if existing:
                return existing[0]["tracking_id"], existing[0]["created_at"]
        raise
    return tracking_id, created_at

def get_complaint(tracking_id):
    init_db()
    rows = get_supabase_client().table("complaints").select("*").eq("tracking_id", str(tracking_id).strip()).limit(1).execute().data
    if not rows:
        return None
    item = dict(rows[0])
    item["description"] = item.get("description") or item.get("complaint_text") or ""
    item["village"] = item.get("village") or item.get("location") or "Not provided"
    item["district"] = item.get("district") or ""
    return item

def get_complaint_by_tracking_id(tracking_id):
    return get_complaint(tracking_id)

def get_all_complaints():
    init_db()
    client = get_supabase_client()
    results, start, page_size = [], 0, 500
    while True:
        page = client.table("complaints").select("*").order("id", desc=True).range(start, start + page_size - 1).execute().data or []
        results.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    for item in results:
        item["description"] = item.get("description") or item.get("complaint_text") or ""
        item["village"] = item.get("village") or item.get("location") or "Not provided"
        item["district"] = item.get("district") or ""
    return results

def update_status(tracking_id, new_status, resolution_note=None):
    allowed = {"Submitted", "Pending", "In Progress", "Resolved", "Rejected"}
    if new_status not in allowed:
        raise ValueError("Invalid complaint status.")
    payload = {"status": new_status}
    # Keep this field optional for existing database schemas.
    if resolution_note is not None:
        payload["resolution_note"] = str(resolution_note).strip()
    rows = get_supabase_client().table("complaints").update(payload).eq("tracking_id", str(tracking_id).strip()).select("tracking_id").execute().data
    return bool(rows)
