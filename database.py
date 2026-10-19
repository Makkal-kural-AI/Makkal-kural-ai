
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from contextlib import closing

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "complaints.db"


def get_connection():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db():
    """Create the database and add missing columns safely."""

    with closing(get_connection()) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS complaints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tracking_id TEXT UNIQUE NOT NULL,
                    complaint_text TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT 'Other',
                    location TEXT NOT NULL DEFAULT 'Not provided',
                    created_at TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'Pending'
                )
            """)

            columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(complaints)"
                ).fetchall()
            }

            # Add columns that may be missing in older versions.
            additions = {
                "tracking_id": "TEXT",
                "complaint_text": "TEXT NOT NULL DEFAULT ''",
                "category": "TEXT NOT NULL DEFAULT 'Other'",
                "location": "TEXT NOT NULL DEFAULT 'Not provided'",
                "created_at": "TEXT NOT NULL DEFAULT ''",
                "status": "TEXT NOT NULL DEFAULT 'Pending'",
                "source_id": "TEXT",
                "name": "TEXT",
                "description": "TEXT",
                "village": "TEXT",
                "district": "TEXT",
                "latitude": "REAL",
                "longitude": "REAL",
            }

            for column, column_type in additions.items():
                if column not in columns:
                    conn.execute(
                        f"ALTER TABLE complaints "
                        f"ADD COLUMN {column} {column_type}"
                    )

            columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(complaints)"
                ).fetchall()
            }

            # Copy data from older column names where possible.
            if "description" in columns:
                conn.execute("""
                    UPDATE complaints
                    SET complaint_text = description
                    WHERE (complaint_text IS NULL OR complaint_text = '')
                      AND description IS NOT NULL
                """)

            if "village" in columns:
                conn.execute("""
                    UPDATE complaints
                    SET location = village
                    WHERE (location IS NULL OR location = '')
                      AND village IS NOT NULL
                """)

            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS
                idx_complaints_source_id
                ON complaints(source_id)
                WHERE source_id IS NOT NULL
            """)


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

    with closing(get_connection()) as conn:
        with conn:
            conn.execute("BEGIN IMMEDIATE")

            # Avoid duplicate records when the same source is retried.
            if source_id:
                existing = conn.execute("""
                    SELECT tracking_id, created_at
                    FROM complaints
                    WHERE source_id = ?
                """, (source_id,)).fetchone()

                if existing:
                    return existing["tracking_id"], existing["created_at"]

            tracking_id = "MKAI-" + uuid.uuid4().hex[:10].upper()
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            conn.execute("""
                INSERT INTO complaints (
                    tracking_id,
                    complaint_text,
                    category,
                    location,
                    created_at,
                    status,
                    source_id,
                    name,
                    description,
                    village,
                    district,
                    latitude,
                    longitude
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tracking_id,
                text,
                category,
                full_location,
                created_at,
                "Submitted",
                source_id,
                name,
                text,
                village,
                district,
                latitude,
                longitude,
            ))

            return tracking_id, created_at


def get_complaint(tracking_id):
    """Find one complaint using its tracking ID."""

    init_db()

    with closing(get_connection()) as conn:
        row = conn.execute("""
            SELECT *
            FROM complaints
            WHERE tracking_id = ?
        """, (str(tracking_id).strip(),)).fetchone()

        if not row:
            return None

        complaint = dict(row)
        complaint["description"] = (
            complaint.get("description")
            or complaint.get("complaint_text")
            or ""
        )
        complaint["village"] = (
            complaint.get("village")
            or complaint.get("location")
            or "Not provided"
        )
        complaint["district"] = complaint.get("district") or ""

        return complaint


def get_complaint_by_tracking_id(tracking_id):
    """Alternative function name for tracking a complaint."""
    return get_complaint(tracking_id)


def get_all_complaints():
    """Return all complaints, newest first."""

    init_db()

    with closing(get_connection()) as conn:
        rows = conn.execute("""
            SELECT *
            FROM complaints
            ORDER BY id DESC
        """).fetchall()

        results = []

        for row in rows:
            item = dict(row)
            item["description"] = (
                item.get("description")
                or item.get("complaint_text")
                or ""
            )
            item["village"] = (
                item.get("village")
                or item.get("location")
                or "Not provided"
            )
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
