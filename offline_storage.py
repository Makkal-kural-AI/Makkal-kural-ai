"""Local SQLite queue for complaints created while Supabase is unreachable."""
import os, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from database import save_complaint

DB_PATH = os.getenv("OFFLINE_DB_PATH", str(Path(__file__).with_name("offline_queue.sqlite3")))

def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS offline_queue (
        local_id TEXT PRIMARY KEY, complaint_text TEXT NOT NULL, category TEXT NOT NULL,
        location TEXT NOT NULL, created_at TEXT NOT NULL, synced INTEGER NOT NULL DEFAULT 0,
        tracking_id TEXT, last_error TEXT
    )""")
    conn.commit()
    return conn

def save_offline_complaint(complaint_text, category="Other", location="Not provided"):
    text = str(complaint_text or "").strip()
    if not text:
        raise ValueError("Complaint text cannot be empty.")
    local_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute("INSERT INTO offline_queue(local_id,complaint_text,category,location,created_at) VALUES(?,?,?,?,?)", (local_id, text, str(category or "Other"), str(location or "Not provided"), created_at))
    return local_id

def get_pending_complaints():
    with _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM offline_queue WHERE synced=0 ORDER BY created_at")]

def sync_pending_complaints():
    """Retry queued items; local_id as source_id prevents duplicate cloud rows."""
    count = 0
    for row in get_pending_complaints():
        try:
            tracking_id, _ = save_complaint(row["complaint_text"], row["category"], row["location"], source_id=row["local_id"])
            with _connect() as conn:
                conn.execute("UPDATE offline_queue SET synced=1, tracking_id=?, last_error=NULL WHERE local_id=?", (tracking_id, row["local_id"]))
            count += 1
        except Exception as exc:
            with _connect() as conn:
                conn.execute("UPDATE offline_queue SET last_error=? WHERE local_id=?", (str(exc)[:500], row["local_id"]))
    return count

def get_all_offline_complaints():
    with _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM offline_queue ORDER BY created_at DESC")]
