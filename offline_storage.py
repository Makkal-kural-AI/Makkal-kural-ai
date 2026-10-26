
import uuid
from datetime import datetime

from database import get_supabase_client, save_complaint, init_db


def init_offline_storage():
    """Check the Supabase connection; create the table with schema.sql."""
    get_supabase_client()


def save_offline_complaint(
    complaint_text,
    category="Other",
    location="Not provided"
):
    """Save a complaint locally for later synchronization."""

    init_offline_storage()

    complaint_text = str(complaint_text or "").strip()

    if not complaint_text:
        raise ValueError("Complaint text cannot be empty.")

    category = str(category or "Other").strip() or "Other"
    location = str(location or "Not provided").strip()
    location = location or "Not provided"

    local_id = str(uuid.uuid4())
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    get_supabase_client().table("offline_queue").insert({
        "local_id": local_id,
        "complaint_text": complaint_text,
        "category": category,
        "location": location,
        "created_at": created_at,
        "synced": False,
        "tracking_id": None,
    }).execute()

    return local_id


def get_pending_complaints():
    """Return complaints that still need synchronization."""

    init_offline_storage()

    return (
        get_supabase_client()
        .table("offline_queue")
        .select("*")
        .eq("synced", False)
        .order("created_at")
        .order("local_id")
        .execute()
        .data
    )


def sync_pending_complaints():
    """Synchronize pending complaints to the main database.

    Reusing local_id as source_id prevents duplicate main
    database records if synchronization is retried.
    """

    init_offline_storage()
    init_db()

    synced_count = 0

    for complaint in get_pending_complaints():
        local_id = complaint["local_id"]

        # The main database recognizes this submission by local_id.
        tracking_id, _ = save_complaint(
            complaint["complaint_text"],
            complaint["category"],
            complaint["location"],
            source_id=local_id
        )

        # If the program stopped before this update, a retry
        # returns the existing tracking ID from the main database.
        updated = (
            get_supabase_client()
            .table("offline_queue")
            .update({"synced": True, "tracking_id": tracking_id})
            .eq("local_id", local_id)
            .eq("synced", False)
            .select("local_id")
            .execute()
            .data
        )
        if updated:
            synced_count += 1

    return synced_count


def get_all_offline_complaints():
    """Retrieve all queued complaints, including synced ones."""

    init_offline_storage()

    return (
        get_supabase_client()
        .table("offline_queue")
        .select("*")
        .order("created_at", desc=True)
        .execute()
        .data
    )


if __name__ == "__main__":
    init_offline_storage()

    print("Supabase queue storage is ready!")
    print("Pending complaints:", len(get_pending_complaints()))
