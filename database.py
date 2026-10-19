
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from contextlib import closing

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "complaints.db"


def get_connection():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db():
    """Create or update the complaints database."""

    with closing(get_connection()) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS complaints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tracking_id TEXT UNIQUE NOT NULL,
                    complaint_text TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Other',
                    location TEXT NOT NULL DEFAULT 'Not provided',
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Pending'
                )
            """)

            columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(complaints)"
                ).fetchall()
            }

            if "source_id" not in columns:
                conn.execute("""
                    ALTER TABLE complaints
                    ADD COLUMN source_id TEXT
                """)

            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS
                idx_complaints_source_id
                ON complaints(source_id)
                WHERE source_id IS NOT NULL
            """)


def save_complaint(
    complaint_text,
    category="Other",
    location="Not provided",
    source_id=None
):
    """Save a complaint and return its tracking ID.

    source_id identifies an offline submission so retries
    cannot create another record for the same submission.
    """

    init_db()

    complaint_text = str(complaint_text or "").strip()

    if not complaint_text:
        raise ValueError("Complaint text cannot be empty.")

    category = str(category or "Other").strip() or "Other"
    location = str(location or "Not provided").strip()
    location = location or "Not provided"

    if source_id is not None:
        source_id = str(source_id).strip()
        if not source_id:
            source_id = None

    with closing(get_connection()) as conn:
        with conn:
            # BEGIN IMMEDIATE serializes competing writers.
            conn.execute("BEGIN IMMEDIATE")

            if source_id:
                existing = conn.execute("""
                    SELECT tracking_id
                    FROM complaints
                    WHERE source_id = ?
                """, (source_id,)).fetchone()

                if existing:
                    return existing[0]

            tracking_id = "MK-" + uuid.uuid4().hex[:8].upper()
            created_at = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            conn.execute("""
                INSERT INTO complaints (
                    tracking_id,
                    complaint_text,
                    category,
                    location,
                    created_at,
                    status,
                    source_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                tracking_id,
                complaint_text,
                category,
                location,
                created_at,
                "Pending",
                source_id
            ))

            return tracking_id


def get_all_complaints():
    """Retrieve all complaints, newest first."""

    init_db()

    with closing(get_connection()) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT
                id,
                tracking_id,
                complaint_text,
                category,
                location,
                created_at,
                status
            FROM complaints
            ORDER BY id DESC
        """).fetchall()

        return [dict(row) for row in rows]


def get_complaint_by_tracking_id(tracking_id):
    """Retrieve a complaint using its tracking ID."""

    init_db()

    with closing(get_connection()) as conn:
        conn.row_factory = sqlite3.Row

        row = conn.execute("""
            SELECT *
            FROM complaints
            WHERE tracking_id = ?
        """, (str(tracking_id).strip(),)).fetchone()

        return dict(row) if row else None


def update_status(tracking_id, new_status):
    """Update the status of a complaint."""

    allowed_statuses = {
        "Pending",
        "In Progress",
        "Resolved"
    }

    if new_status not in allowed_statuses:
        raise ValueError("Invalid complaint status.")

    init_db()

    with closing(get_connection()) as conn:
        with conn:
            cursor = conn.execute("""
                UPDATE complaints
                SET status = ?
                WHERE tracking_id = ?
            """, (new_status, str(tracking_id).strip()))

            return cursor.rowcount > 0


if __name__ == "__main__":
    init_db()
    print("Makkal Kural AI database is ready!")
    print("Database location:", DB_PATH)
