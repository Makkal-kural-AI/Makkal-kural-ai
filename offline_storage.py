
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from contextlib import closing

from database import save_complaint, init_db

BASE_DIR = Path(__file__).resolve().parent
QUEUE_DB = BASE_DIR / "offline_queue.db"


def get_queue_connection():
    conn = sqlite3.connect(str(QUEUE_DB), timeout=10)
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_offline_storage():
    """Create local storage for complaints waiting to sync."""

    with closing(get_queue_connection()) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS offline_queue (
                    local_id TEXT PRIMARY KEY,
                    complaint_text TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Other',
                    location TEXT NOT NULL DEFAULT 'Not provided',
                    created_at TEXT NOT NULL,
                    synced INTEGER NOT NULL DEFAULT 0,
                    tracking_id TEXT UNIQUE
                )
            """)


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

    with closing(get_queue_connection()) as conn:
        with conn:
            conn.execute("""
                INSERT INTO offline_queue (
                    local_id,
                    complaint_text,
                    category,
                    location,
                    created_at,
                    synced,
                    tracking_id
                )
                VALUES (?, ?, ?, ?, ?, 0, NULL)
            """, (
                local_id,
                complaint_text,
                category,
                location,
                created_at
            ))

    return local_id


def get_pending_complaints():
    """Return complaints that still need synchronization."""

    init_offline_storage()

    with closing(get_queue_connection()) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT *
            FROM offline_queue
            WHERE synced = 0
            ORDER BY created_at, local_id
        """).fetchall()

        return [dict(row) for row in rows]


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
        tracking_id = save_complaint(
            complaint["complaint_text"],
            complaint["category"],
            complaint["location"],
            source_id=local_id
        )

        # If the program stopped before this update, a retry
        # returns the existing tracking ID from the main database.
        with closing(get_queue_connection()) as conn:
            with conn:
                cursor = conn.execute("""
                    UPDATE offline_queue
                    SET synced = 1, tracking_id = ?
                    WHERE local_id = ? AND synced = 0
                """, (tracking_id, local_id))

                if cursor.rowcount > 0:
                    synced_count += 1

    return synced_count


def get_all_offline_complaints():
    """Retrieve all queued complaints, including synced ones."""

    init_offline_storage()

    with closing(get_queue_connection()) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT *
            FROM offline_queue
            ORDER BY created_at DESC
        """).fetchall()

        return [dict(row) for row in rows]


if __name__ == "__main__":
    init_offline_storage()

    print("Offline storage is ready!")
    print("Pending complaints:", len(get_pending_complaints()))
