
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

# Store the database in this project's folder
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "complaints.db"


def get_connection():
    """Connect to the SQLite database."""
    return sqlite3.connect(str(DB_PATH))


def init_db():
    """Create the complaints table if it does not exist."""
    conn = get_connection()

    try:
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

        conn.commit()
    finally:
        conn.close()


def save_complaint(
    complaint_text,
    category="Other",
    location="Not provided"
):
    """Save a complaint and return its tracking ID."""

    complaint_text = str(complaint_text).strip()

    if not complaint_text:
        raise ValueError("Complaint text cannot be empty.")

    category = str(category or "Other").strip() or "Other"
    location = str(location or "Not provided").strip()
    location = location or "Not provided"

    tracking_id = "MK-" + uuid.uuid4().hex[:8].upper()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()

    try:
        conn.execute("""
            INSERT INTO complaints (
                tracking_id,
                complaint_text,
                category,
                location,
                created_at,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            tracking_id,
            complaint_text,
            category,
            location,
            created_at,
            "Pending"
        ))

        conn.commit()
        return tracking_id

    finally:
        conn.close()


def get_all_complaints():
    """Return all complaints, newest first."""

    conn = get_connection()

    try:
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

    finally:
        conn.close()


def get_complaint_by_tracking_id(tracking_id):
    """Find one complaint using its tracking ID."""

    conn = get_connection()

    try:
        conn.row_factory = sqlite3.Row

        row = conn.execute("""
            SELECT *
            FROM complaints
            WHERE tracking_id = ?
        """, (tracking_id.strip(),)).fetchone()

        return dict(row) if row else None

    finally:
        conn.close()


def update_status(tracking_id, new_status):
    """Update a complaint's status."""

    allowed_statuses = {
        "Pending",
        "In Progress",
        "Resolved"
    }

    if new_status not in allowed_statuses:
        raise ValueError("Invalid complaint status.")

    conn = get_connection()

    try:
        cursor = conn.execute("""
            UPDATE complaints
            SET status = ?
            WHERE tracking_id = ?
        """, (new_status, tracking_id.strip()))

        conn.commit()
        return cursor.rowcount > 0

    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("Makkal Kural AI database is ready!")
    print("Database location:", DB_PATH)
