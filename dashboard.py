"""
database.py - Supabase PostgreSQL layer for Makkal Kural AI.

This file only does database work. It never draws any UI.

Needs:
  * psycopg[binary]>=3.1   (add to requirements.txt)
  * DATABASE_URL           (environment variable, never hardcode it)

Optional environment variables:
  * COMPLAINTS_TABLE  (default: complaints)
  * DB_SCHEMA         (default: public)
"""

import logging
import math
import os
import re
import secrets
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg
from psycopg import sql
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

logger = logging.getLogger("makkal_kural.database")

# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
TABLE_NAME = os.environ.get("COMPLAINTS_TABLE", "complaints")
SCHEMA_NAME = os.environ.get("DB_SCHEMA", "public")

VALID_STATUSES = ("Pending", "In Progress", "Resolved")

REQUIRED_COLUMNS = (
    "tracking_id",
    "complaint_text",
    "location",
    "category",
    "status",
    "submitted_at",
)
OPTIONAL_COLUMNS = ("latitude", "longitude")

CONNECT_RETRIES = 3          # only used for connecting, never for inserting
CONNECT_TIMEOUT_SECONDS = 10
DUPLICATE_WINDOW_SECONDS = 60

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_IST = timezone(timedelta(hours=5, minutes=30))
# No 0/O/1/I so tracking IDs are easy to read out loud.
_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_TIMESTAMP_TYPES = ("timestamp with time zone", "timestamp without time zone")


class DatabaseError(Exception):
    """A safe, readable database error. It never contains the DATABASE_URL."""


# --------------------------------------------------------------------------
# Connection helpers
# --------------------------------------------------------------------------
def _table_ref():
    if not _IDENTIFIER.match(TABLE_NAME) or not _IDENTIFIER.match(SCHEMA_NAME):
        raise DatabaseError(
            "COMPLAINTS_TABLE and DB_SCHEMA may only contain letters, "
            "numbers and underscores."
        )
    return sql.SQL("{}.{}").format(
        sql.Identifier(SCHEMA_NAME), sql.Identifier(TABLE_NAME)
    )


@contextmanager
def _connect():
    """Open a connection, commit on success, roll back on error, always close."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise DatabaseError(
            "DATABASE_URL is not set. Add it as an environment variable "
            "(Render dashboard) or in your local terminal."
        )

    kwargs = {
        "connect_timeout": CONNECT_TIMEOUT_SECONDS,
        "row_factory": dict_row,
        # Needed for Supabase's transaction pooler (port 6543). Harmless elsewhere.
        "prepare_threshold": None,
    }
    if "sslmode" not in url:
        kwargs["sslmode"] = "require"

    conn = None
    for attempt in range(1, CONNECT_RETRIES + 1):
        try:
            conn = psycopg.connect(url, **kwargs)
            break
        except psycopg.OperationalError:
            if attempt == CONNECT_RETRIES:
                logger.error("Could not connect to the database.")
                raise DatabaseError(
                    "Could not connect to the database. Check DATABASE_URL "
                    "(host, port, user, password) and that the Supabase "
                    "project is running."
                ) from None
            time.sleep(1.5 * attempt)
        except psycopg.Error:
            raise DatabaseError(
                "DATABASE_URL looks invalid. Copy the connection string "
                "again from Supabase."
            ) from None

    try:
        yield conn
        conn.commit()
    except DatabaseError:
        conn.rollback()
        raise
    except psycopg.Error as exc:
        conn.rollback()
        # Log only the error class, never the message (it could contain details).
        logger.error("Database error: %s", type(exc).__name__)
        raise DatabaseError(
            "A database error occurred (%s). Check the table name and columns."
            % type(exc).__name__
        ) from None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _table_columns(cur):
    """Return {column_name: {data_type, nullable, default}} for the table."""
    cur.execute(
        """
        SELECT column_name, data_type, is_nullable, column_default, is_identity
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        """,
        (SCHEMA_NAME, TABLE_NAME),
    )
    return {
        r["column_name"]: {
            "data_type": r["data_type"],
            "nullable": r["is_nullable"] == "YES",
            "has_default": r["column_default"] is not None
            or r["is_identity"] == "YES",
        }
        for r in cur.fetchall()
    }


def _require_schema(cols):
    if not cols:
        raise DatabaseError(
            "Table '%s.%s' was not found. Check its name in the Supabase "
            "Table Editor, or set COMPLAINTS_TABLE." % (SCHEMA_NAME, TABLE_NAME)
        )
    missing = [c for c in REQUIRED_COLUMNS if c not in cols]
    if missing:
        raise DatabaseError(
            "The complaints table is missing column(s): %s. See the schema "
            "notes in the setup guide." % ", ".join(missing)
        )


# --------------------------------------------------------------------------
# Value helpers
# --------------------------------------------------------------------------
def _valid_coordinate(value, low, high):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < low or number > high:
        return None
    return number


def _format_time(value):
    """Show timestamps as 'YYYY-MM-DD HH:MM:SS' in Indian Standard Time."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(_IST).strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _clean_row(row):
    out = {}
    for key, value in row.items():
        if key == "submitted_at":
            out[key] = _format_time(value)
        elif isinstance(value, Decimal):
            out[key] = float(value)
        else:
            out[key] = value

    if "latitude" in out or "longitude" in out:
        lat = _valid_coordinate(out.get("latitude"), -90.0, 90.0)
        lon = _valid_coordinate(out.get("longitude"), -180.0, 180.0)
        # (0, 0) is a common "empty" placeholder, so it is not a real location.
        if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
            lat, lon = None, None
        out["latitude"], out["longitude"] = lat, lon
    return out


def _generate_tracking_id():
    today = datetime.now(_IST).strftime("%Y%m%d")
    suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(6))
    return "MK-%s-%s" % (today, suffix)


def _select(wanted, where=None, params=(), limit=None):
    """Run a SELECT on the available columns and return a list of dicts."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cols = _table_columns(cur)
            _require_schema(cols)
            use = [c for c in wanted if c in cols]
            query = sql.SQL("SELECT {fields} FROM {table}").format(
                fields=sql.SQL(", ").join(sql.Identifier(c) for c in use),
                table=_table_ref(),
            )
            if where is not None:
                query = query + sql.SQL(" WHERE ") + where
            if "submitted_at" in cols:
                query = query + sql.SQL(" ORDER BY {} DESC NULLS LAST").format(
                    sql.Identifier("submitted_at")
                )
            if limit:
                query = query + sql.SQL(" LIMIT {}").format(sql.Literal(int(limit)))
            cur.execute(query, params)
            rows = cur.fetchall()
    return [_clean_row(r) for r in rows]


# --------------------------------------------------------------------------
# A. init_db
# --------------------------------------------------------------------------
def init_db():
    """
    Check the connection and the existing table. NON-destructive: it never
    creates, drops, deletes or alters anything.

    Returns True when everything is fine. Raises DatabaseError with a clear
    message when the table or a required column is missing.
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cols = _table_columns(cur)
            _require_schema(cols)

    for name in OPTIONAL_COLUMNS:
        if name not in cols:
            logger.warning(
                "Optional column '%s' is missing. The map will show no "
                "coordinates until you add it.", name
            )

    # Columns we do not fill in ourselves must be nullable or have a default,
    # otherwise inserting a complaint would fail.
    known = set(REQUIRED_COLUMNS) | set(OPTIONAL_COLUMNS)
    blocking = [
        n for n, info in cols.items()
        if n not in known and not info["nullable"] and not info["has_default"]
    ]
    if blocking:
        raise DatabaseError(
            "These columns are NOT NULL with no default, so new complaints "
            "cannot be saved: %s" % ", ".join(blocking)
        )
    return True


# --------------------------------------------------------------------------
# B. save_complaint
# --------------------------------------------------------------------------
def save_complaint(complaint_text, category, location):
    """
    Save one complaint with status 'Pending'.
    Returns (tracking_id, submitted_at_text).
    """
    text = (complaint_text or "").strip()
    category = (category or "").strip()
    location = (location or "").strip()
    if not text:
        raise ValueError("complaint_text cannot be empty.")

    now_utc = datetime.now(timezone.utc)

    for _ in range(5):  # only repeats if a generated ID already exists
        tracking_id = _generate_tracking_id()
        collided = False

        with _connect() as conn:
            with conn.cursor() as cur:
                cols = _table_columns(cur)
                _require_schema(cols)

                time_type = cols["submitted_at"]["data_type"]
                is_timestamp = time_type in _TIMESTAMP_TYPES
                if time_type == "timestamp without time zone":
                    stamp = now_utc.replace(tzinfo=None)
                elif is_timestamp:
                    stamp = now_utc
                else:  # text column
                    stamp = _format_time(now_utc)

                # Protect against double clicks / retries: same complaint
                # within the last minute returns the existing tracking ID.
                if is_timestamp:
                    cutoff = stamp - timedelta(seconds=DUPLICATE_WINDOW_SECONDS)
                    cur.execute(
                        sql.SQL(
                            "SELECT tracking_id, submitted_at FROM {t} "
                            "WHERE complaint_text = %s AND category = %s "
                            "AND location = %s AND submitted_at >= %s "
                            "ORDER BY submitted_at DESC LIMIT 1"
                        ).format(t=_table_ref()),
                        (text, category, location, cutoff),
                    )
                    existing = cur.fetchone()
                    if existing:
                        return (
                            existing["tracking_id"],
                            _format_time(existing["submitted_at"]),
                        )

                try:
                    cur.execute(
                        sql.SQL(
                            "INSERT INTO {t} (tracking_id, complaint_text, "
                            "location, category, status, submitted_at) "
                            "VALUES (%s, %s, %s, %s, %s, %s)"
                        ).format(t=_table_ref()),
                        (tracking_id, text, location, category, "Pending", stamp),
                    )
                except UniqueViolation:
                    conn.rollback()
                    collided = True

        if not collided:
            return tracking_id, _format_time(now_utc)

    raise DatabaseError("Could not create a unique tracking ID. Please try again.")


# --------------------------------------------------------------------------
# C. get_all_complaints  (admin dashboard: includes full complaint text)
# --------------------------------------------------------------------------
def get_all_complaints():
    """Return every complaint as a list of dicts (newest first)."""
    return _select(list(REQUIRED_COLUMNS) + list(OPTIONAL_COLUMNS))


# --------------------------------------------------------------------------
# D. update_status
# --------------------------------------------------------------------------
def update_status_detailed(tracking_id, new_status):
    """Returns (True/False, message). Never inserts a new complaint."""
    wanted = (new_status or "").strip().lower()
    status = next((s for s in VALID_STATUSES if s.lower() == wanted), None)
    if status is None:
        return False, "Invalid status. Use one of: %s." % ", ".join(VALID_STATUSES)

    tid = (tracking_id or "").strip()
    if not tid:
        return False, "Tracking ID is required."

    with _connect() as conn:
        with conn.cursor() as cur:
            cols = _table_columns(cur)
            _require_schema(cols)
            cur.execute(
                sql.SQL(
                    "UPDATE {t} SET status = %s WHERE tracking_id = %s "
                    "RETURNING tracking_id"
                ).format(t=_table_ref()),
                (status, tid),
            )
            updated = cur.fetchall()

    if not updated:
        return False, "No complaint found with tracking ID %s." % tid
    return True, "Status updated to '%s'." % status


def update_status(tracking_id, new_status):
    """True if the status was updated, False otherwise."""
    success, _message = update_status_detailed(tracking_id, new_status)
    return success


# --------------------------------------------------------------------------
# Extra helpers for the public pages (database only, no UI)
# --------------------------------------------------------------------------
def get_complaint_by_tracking_id(tracking_id):
    """Private tracking page: one complaint, or None if the ID is unknown."""
    tid = (tracking_id or "").strip()
    if not tid:
        return None
    rows = _select(
        list(REQUIRED_COLUMNS) + list(OPTIONAL_COLUMNS),
        where=sql.SQL("{} = %s").format(sql.Identifier("tracking_id")),
        params=(tid,),
        limit=1,
    )
    return rows[0] if rows else None


def get_public_complaints():
    """
    Public list/map data. Leaves out the complaint text and the full tracking
    ID, so nothing private is shown. 'reference' is only the last 4 characters.
    """
    rows = _select(
        ["tracking_id", "location", "category", "status", "submitted_at"]
        + list(OPTIONAL_COLUMNS)
    )
    public = []
    for row in rows:
        item = {
            "reference": "..." + str(row.get("tracking_id", ""))[-4:],
            "location": row.get("location"),
            "category": row.get("category"),
            "status": row.get("status"),
            "submitted_at": row.get("submitted_at"),
        }
        if "latitude" in row:
            item["latitude"] = row["latitude"]
            item["longitude"] = row["longitude"]
        public.append(item)
    return public


def get_map_points():
    """Public complaints that have valid coordinates (for the map only)."""
    return [
        c for c in get_public_complaints()
        if c.get("latitude") is not None and c.get("longitude") is not None
    ]


# --------------------------------------------------------------------------
# Self-test:  python database.py          (connection + schema check)
#             python database.py --full-test  (also saves ONE test complaint)
# --------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        init_db()
        print("OK: connected and the complaints table looks correct.")
        print("OK: get_all_complaints() returned %d row(s)." % len(get_all_complaints()))

        if "--full-test" in sys.argv:
            tid, when = save_complaint(
                "TEST complaint - safe to delete", "Test", "Test Village"
            )
            print("OK: saved %s at %s" % (tid, when))
            print("OK: bad status rejected ->", update_status(tid, "Banana") is False)
            print("OK: In Progress ->", update_status(tid, "In Progress"))
            print("OK: Resolved ->", update_status(tid, "Resolved"))
            print("OK: unknown ID rejected ->", update_status("NOPE", "Resolved") is False)
            print("OK: tracking lookup ->", bool(get_complaint_by_tracking_id(tid)))
            print("Delete the TEST row in the Supabase Table Editor when done.")
    except DatabaseError as err:
        print("FAILED:", err)
        sys.exit(1)
