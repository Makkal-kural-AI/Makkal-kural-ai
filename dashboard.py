"""
Makkal Kural AI — UI Dashboard Modules
Exports: render_submit(), render_tracking(), render_public(), render_admin(),
         render_notifications_banner()

This module only defines functions. Importing it never renders anything and it
never calls st.set_page_config() — app.py owns the page configuration.

Voice input (no paid API, no API key):
1. Primary  — browser speech recognition via streamlit-mic-recorder
                (Web Speech API, Tamil ta-IN / English en-IN).
2. Backup   — local Whisper (openai-whisper package) running on this server
                with st.audio_input(). No OpenAI API is ever called.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import math
import os
import secrets
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen

import streamlit as st
from custom_otp_component import otp_input
from database import (
    database_configured,
    fetch_complaints,
    get_complaint_by_tracking_id,
    get_setting,
    save_complaint,
    update_status,
)

try:
    import folium
    from streamlit_folium import st_folium
except ImportError:
    folium = None
    st_folium = None

try:
    from streamlit_mic_recorder import speech_to_text
except ImportError:
    speech_to_text = None

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

STATUSES = ["Submitted", "Pending", "In Progress", "Resolved"]
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 60
IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_MAP_CENTER = (13.0827, 80.2707)  # Chennai
MAX_MAP_MARKERS = 1000
PUBLIC_TABLE_ROWS = 60

# Voice input languages: browser recognition code and Whisper language code.
VOICE_LANGUAGES = {
    "தமிழ் (Tamil)": {"browser": "ta-IN", "whisper": "ta"},
    "English": {"browser": "en-IN", "whisper": "en"},
}
# Local Whisper model. "tiny" is the smallest multilingual model. It can be
# changed with the optional WHISPER_MODEL setting (tiny, base or small).
WHISPER_MODELS = ("tiny", "base", "small")
MAX_AUDIO_BYTES = 15 * 1024 * 1024
_WHISPER_LOCK = threading.Lock()  # the shared model is used by one request at a time

COMPLAINT_CATEGORIES = ["Water Supply", "Garbage", "Road Damage", "Drainage", "Electricity", "Other"]

# Citizens may write names or phone numbers in the free-text description, so it
# is hidden on the public page and its map. Admins always see it.
PUBLIC_SHOW_DESCRIPTION = False

_PENDING = {"pending", "new", "submitted", "open", "registered"}
_PROGRESS = {"in progress", "in-progress", "inprogress", "ongoing"}
_RESOLVED = {"resolved", "closed", "completed"}

BUCKET_COLORS = {
    "Pending": "red",
    "In Progress": "orange",
    "Resolved": "green",
    "Other": "gray",
}
CHART_COLORS = ["#2563eb", "#38bdf8", "#16a34a", "#f59e0b", "#8b5cf6", "#ef4444", "#64748b"]

# Fast instant coordinates for common localities (case-insensitive keys)
KNOWN_LOCATIONS: dict[str, tuple[float, float]] = {
    "chennai": (13.0827, 80.2707),
    "saidapet": (13.0231, 80.2206),
    "guindy": (13.0067, 80.2206),
    "kodambakkam": (13.0524, 80.2255),
    "t nagar": (13.0418, 80.2341),
    "t. nagar": (13.0418, 80.2341),
    "adyar": (13.0012, 80.2565),
    "mylapore": (13.0339, 80.2676),
    "velachery": (12.9815, 80.2180),
    "anna nagar": (13.0850, 80.2101),
    "tambaram": (12.9249, 80.1000),
    "chromepet": (12.9516, 80.1462),
    "porur": (13.0382, 80.1566),
    "madurai": (9.9252, 78.1198),
    "coimbatore": (11.0168, 76.9558),
    "trichy": (10.7905, 78.7047),
    "salem": (11.6643, 78.1460),
    "tirunelveli": (8.7139, 77.7567),
}


# --------------------------------------------------------------------------
# Data & Geocoding helpers
# --------------------------------------------------------------------------


def _text(value, default: str = "") -> str:
    """Convert a database value to clean text; None / NaN become `default`."""
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    text = str(value).strip()
    return text or default


def _coord(value, low: float, high: float):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number) or not (low <= number <= high):
        return None
    return number


def _first_coord(row: dict, names: tuple, low: float, high: float):
    for name in names:
        number = _coord(row.get(name), low, high)
        if number is not None:
            return number
    return None


def _nominatim_lookup(query_text: str) -> tuple[float | None, float | None]:
    try:
        query = quote(query_text)
        url = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1"
        req = Request(url, headers={"User-Agent": "MakkalKuralAI/1.0 (contact@makkalkural.ai)"})
        with urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data:
                lat = _coord(data[0].get("lat"), -90, 90)
                lon = _coord(data[0].get("lon"), -180, 180)
                if lat is not None and lon is not None:
                    return lat, lon
    except Exception:
        pass
    return None, None


@st.cache_data(ttl=86400, show_spinner=False)
def resolve_coordinates(place_name: str) -> tuple[float | None, float | None]:
    """Resolve latitude and longitude from any village/area/town/city name."""
    cleaned = " ".join(_text(place_name).split())
    if not cleaned or cleaned.lower() in {"not provided", "unspecified", "none", "na", "n/a"}:
        return None, None

    key = cleaned.casefold()
    if key in KNOWN_LOCATIONS:
        return KNOWN_LOCATIONS[key]

    for known_key, coords in KNOWN_LOCATIONS.items():
        if known_key in key or key in known_key:
            return coords

    lat, lon = _nominatim_lookup(f"{cleaned}, Tamil Nadu, India")
    if lat is not None and lon is not None:
        return lat, lon

    lat, lon = _nominatim_lookup(f"{cleaned}, India")
    if lat is not None and lon is not None:
        return lat, lon

    return _nominatim_lookup(cleaned)


def _parse_dt(value):
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(IST)


def status_bucket(status: str) -> str:
    key = _text(status).lower()
    if key in _PENDING:
        return "Pending"
    if key in _PROGRESS:
        return "In Progress"
    if key in _RESOLVED:
        return "Resolved"
    return "Other"


def normalise_record(row: dict) -> dict:
    """Normalises field names so tables, filters and maps never see None/NaN."""
    lat = _first_coord(row, ("latitude", "lat"), -90, 90)
    lon = _first_coord(row, ("longitude", "lng", "lon"), -180, 180)
    if lat is None or lon is None or (lat == 0 and lon == 0):
        lat, lon = None, None

    location = _text(row.get("location"), "Not provided")
    district = _text(row.get("district"))
    village = _text(row.get("village"))
    region = district or village or (location if location != "Not provided" else "")

    if lat is None or lon is None:
        lookup_place = village or location or district
        auto_lat, auto_lon = resolve_coordinates(lookup_place)
        if auto_lat is not None and auto_lon is not None:
            lat, lon = auto_lat, auto_lon

    status = _text(row.get("status"), "Pending")
    created = _parse_dt(row.get("created_at"))

    return {
        **row,
        "_tracking_id": _text(row.get("tracking_id"), _text(row.get("id"), "N/A")),
        "_category": _text(row.get("category"), "Uncategorized"),
        "_description": _text(row.get("description"), _text(row.get("complaint_text"))),
        "_status": status,
        "_bucket": status_bucket(status),
        "_location": location,
        "_region": " ".join(region.split()) or "Unspecified",
        "_latitude": lat,
        "_longitude": lon,
        "_created_at": created,
        "_resolution_notes": _text(row.get("resolution_note"), _text(row.get("resolution_notes"))),
    }


def _date_label(record: dict, with_time: bool = False) -> str:
    created = record.get("_created_at")
    if created is None:
        return "—"
    return created.strftime("%d %b %Y, %H:%M" if with_time else "%d %b %Y")


def _load_records() -> list[dict] | None:
    """Load and normalise complaints; shows an error and returns None on failure."""
    if not database_configured():
        st.warning(
            "The database is not configured. Set SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY on the server to load complaints."
        )
        return None
    rows, error = fetch_complaints()
    if error:
        st.error(error)
        return None
    return [normalise_record(item) for item in rows]


def _group_counts(values: list[str]) -> list[tuple[str, int]]:
    """Count values ignoring case, most common first."""
    labels: dict[str, str] = {}
    counts: Counter = Counter()
    for value in values:
        key = value.casefold()
        labels.setdefault(key, value)
        counts[key] += 1
    return [(labels[key], n) for key, n in counts.most_common()]


def _region_options(records: list[dict]) -> list[str]:
    return [label for label, _ in _group_counts([r["_region"] for r in records])][:60]


def _matches(record: dict, needle: str, include_description: bool) -> bool:
    if not needle:
        return True
    parts = [record["_tracking_id"], record["_category"], record["_location"]]
    if include_description:
        parts.append(record["_description"])
    return needle in " ".join(parts).casefold()


# --------------------------------------------------------------------------
# HTML / SVG building blocks (all dynamic text is escaped)
# --------------------------------------------------------------------------


def _esc(value) -> str:
    return html.escape(str(value)).replace("$", "&#36;")


def _shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _pill(record: dict) -> str:
    bucket = record["_bucket"]
    css = {"Pending": "pending", "In Progress": "progress", "Resolved": "resolved"}.get(bucket, "other")
    return f'<span class="mka-pill {css}">{_esc(record["_status"])}</span>'


def _axis(max_value: int) -> tuple[int, int]:
    """Return (step, top) for a y-axis with about four intervals."""
    raw = max(max_value, 1) / 4
    magnitude = 10 ** math.floor(math.log10(raw))
    step = magnitude
    for factor in (1, 2, 5, 10):
        step = factor * magnitude
        if raw <= step:
            break
    step = int(max(1, step))
    return step, step * math.ceil(max(max_value, 1) / step)


def _chart_frame(top: int, step: int, width: int, height: int, left: int, right: int, ptop: int, bottom: int) -> str:
    parts = []
    plot_h = height - ptop - bottom
    for tick in range(0, top + 1, step):
        y = ptop + plot_h - plot_h * tick / top
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#e5eaf2" stroke-width="1"/>'
            f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="#64748b">{tick}</text>'
        )
    return "".join(parts)


def _bar_chart_svg(items: list[tuple[str, int]]) -> str:
    if not items:
        return '<div class="mka-empty-chart">No data yet</div>'
    width, height, left, right, ptop, bottom = 420, 230, 38, 10, 16, 40
    step, top = _axis(max(v for _, v in items))
    plot_h = height - ptop - bottom
    slot = (width - left - right) / len(items)
    bar_w = min(48, slot * 0.58)
    parts = [_chart_frame(top, step, width, height, left, right, ptop, bottom)]
    for i, (label, value) in enumerate(items):
        x = left + slot * i + (slot - bar_w) / 2
        h = plot_h * value / top
        y = ptop + plot_h - h
        color = CHART_COLORS[i % len(CHART_COLORS)]
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" rx="3" fill="{color}"/>'
            f'<text x="{x + bar_w / 2:.1f}" y="{y - 4:.1f}" text-anchor="middle" font-size="11" font-weight="700" fill="#0f172a">{value}</text>'
            f'<text x="{x + bar_w / 2:.1f}" y="{height - bottom + 16}" text-anchor="middle" font-size="11" fill="#475569">{_esc(_shorten(label, 12))}</text>'
        )
    return f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Complaints by category" style="width:100%;height:auto">{"".join(parts)}</svg>'


def _line_chart_svg(points: list[tuple[str, int]]) -> str:
    if not points or not any(v for _, v in points):
        return '<div class="mka-empty-chart">No dated reports in this period</div>'
    width, height, left, right, ptop, bottom = 420, 230, 38, 26, 16, 40
    step, top = _axis(max(v for _, v in points))
    plot_h = height - ptop - bottom
    plot_w = width - left - right
    n = len(points)
    coords = []
    for i, (_, value) in enumerate(points):
        x = left + (plot_w * i / (n - 1) if n > 1 else plot_w / 2)
        y = ptop + plot_h - plot_h * value / top
        coords.append((x, y))
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    base = ptop + plot_h
    area = f"{coords[0][0]:.1f},{base} {line} {coords[-1][0]:.1f},{base}"
    parts = [
        _chart_frame(top, step, width, height, left, right, ptop, bottom),
        f'<polygon points="{area}" fill="rgba(37,99,235,.14)"/>',
        f'<polyline points="{line}" fill="none" stroke="#2563eb" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>',
    ]
    for (label, value), (x, y) in zip(points, coords):
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#fff" stroke="#2563eb" stroke-width="2"/>'
            f'<text x="{x:.1f}" y="{height - bottom + 16}" text-anchor="middle" font-size="11" fill="#475569">{_esc(label)}</text>'
        )
    return f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Reports received per day" style="width:100%;height:auto">{"".join(parts)}</svg>'


def _donut_svg(percent: int) -> str:
    radius = 34
    circumference = 2 * math.pi * radius
    arc = ""
    if percent > 0:
        arc = (
            f'<circle cx="42" cy="42" r="{radius}" fill="none" stroke="#16a34a" stroke-width="9" '
            f'stroke-linecap="round" stroke-dasharray="{circumference * percent / 100:.2f} {circumference:.2f}" '
            f'transform="rotate(-90 42 42)"/>'
        )
    return (
        '<svg viewBox="0 0 84 84" width="84" height="84" role="img" aria-label="Completion rate">'
        f'<circle cx="42" cy="42" r="{radius}" fill="none" stroke="#e2e8f0" stroke-width="9"/>{arc}'
        '<circle cx="42" cy="42" r="17" fill="#16a34a"/>'
        '<path d="M34 42l6 6 11-12" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    )


def _kpi_html(total: int, pending: int, progress: int, resolved: int, rate: int) -> str:
    return (
        '<div class="mka-kpis">'
        f'<div class="mka-kpi"><span>Total Reports</span><b>{total}</b></div>'
        f'<div class="mka-kpi pending"><span>Pending</span><b>{pending}</b></div>'
        f'<div class="mka-kpi progress"><span>In Progress</span><b>{progress}</b></div>'
        f'<div class="mka-kpi resolved"><span>Resolved</span><b>{resolved}</b></div>'
        f'<div class="mka-kpi donut">{_donut_svg(rate)}<div><b>{rate}%</b><span>Completion<br>Rate</span></div></div>'
        "</div>"
    )


def _trend_points(records: list[dict], days: int = 7) -> tuple[list[tuple[str, int]], int]:
    today = datetime.now(IST).date()
    counts: Counter = Counter(r["_created_at"].date() for r in records if r["_created_at"] is not None)
    points = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        points.append((day.strftime("%d %b"), counts.get(day, 0)))
    undated = sum(1 for r in records if r["_created_at"] is None)
    return points, undated


def _panel_title(icon: str, title: str, badge: str = "", badge_class: str = "") -> str:
    badge_html = f'<span class="mka-badge {badge_class}"><i></i>{_esc(badge)}</span>' if badge else ""
    return f'<div class="mka-panel-title"><span>{icon} {_esc(title)}</span>{badge_html}</div>'


# --------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------

_BASE_CSS = """
<style>
.mka-panel-title{display:flex;align-items:center;justify-content:space-between;gap:12px;color:#fff;
  font-size:clamp(21px,2.6vw,30px);font-weight:800;margin:4px 0 12px;text-shadow:0 2px 8px rgba(0,0,0,.6)}
.mka-badge{display:inline-flex;align-items:center;gap:7px;background:rgba(255,255,255,.14);color:#fff;
  border:1px solid rgba(255,255,255,.25);border-radius:999px;padding:5px 13px;font-size:13px;font-weight:600;text-shadow:none}
.mka-badge i{width:9px;height:9px;border-radius:50%;background:#f5a524;display:inline-block}
.mka-badge.locked i{background:#ef4444}
.mka-sheet{background:#f4f7fb;color:#0f172a;border-radius:16px;padding:16px;box-shadow:0 12px 34px rgba(0,0,0,.35);margin-bottom:16px}
.mka-kpis{display:grid;grid-template-columns:repeat(4,1fr) 1.45fr;gap:12px;margin-bottom:14px}
.mka-kpi{background:#fff;border-radius:14px;padding:14px 16px;box-shadow:0 2px 8px rgba(15,23,42,.08);display:flex;flex-direction:column;gap:4px}
.mka-kpi span{font-size:13px;color:#475569}
.mka-kpi b{font-size:34px;line-height:1.1;color:#0f172a}
.mka-kpi.pending{background:#fde4e4}.mka-kpi.progress{background:#fdf0cf}.mka-kpi.resolved{background:#dcf3e1}
.mka-kpi.donut{flex-direction:row;align-items:center;gap:12px}
.mka-kpi.donut div{display:flex;flex-direction:column}
.mka-kpi.donut b{font-size:28px}
.mka-grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.mka-card{background:#fff;color:#0f172a;border-radius:14px;padding:14px 16px;box-shadow:0 2px 8px rgba(15,23,42,.08)}
.mka-card-head{display:flex;align-items:center;justify-content:space-between;font-weight:700;font-size:15px;margin-bottom:6px;color:#0f172a}
.mka-card-head small{font-weight:600;font-size:11px;color:#475569;background:#eef2f7;border-radius:6px;padding:3px 8px}
.mka-empty-chart{height:200px;display:flex;align-items:center;justify-content:center;color:#64748b;font-size:14px}
.mka-note{color:#64748b;font-size:12px;margin-top:8px}
.mka-tablewrap{overflow:auto;max-height:520px;border-radius:12px;background:#fff;box-shadow:0 2px 8px rgba(15,23,42,.1)}
.mka-table{width:100%;border-collapse:collapse;font-size:13px;color:#0f172a;margin:0}
.mka-table th{position:sticky;top:0;background:#f1f5f9;text-align:left;padding:9px 10px;font-weight:700;color:#334155;white-space:nowrap;border:0}
.mka-table td{padding:9px 10px;border:0;border-top:1px solid #eef2f7;vertical-align:top;background:#fff;color:#0f172a}
.mka-table td.id{font-weight:700;white-space:nowrap}
.mka-table td.muted,.mka-table small{color:#64748b}
.mka-table small{display:block;font-size:11px;font-weight:400}
.mka-pill{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:700;white-space:nowrap}
.mka-pill.pending{background:#fee2e2;color:#b91c1c}.mka-pill.progress{background:#fef3c7;color:#b45309}
.mka-pill.resolved{background:#dcfce7;color:#15803d}.mka-pill.other{background:#e2e8f0;color:#475569}
.mka-legend{display:flex;flex-wrap:wrap;gap:14px;color:#e6eefb;font-size:13px;margin:4px 0 8px}
.mka-legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}
.mka-section{color:#fff;font-size:20px;font-weight:800;margin:18px 0 8px;text-shadow:0 2px 8px rgba(0,0,0,.6)}
.mka-hero-noti{background:rgba(17,24,39,0.86);border:2px solid #86efac;box-shadow:0 0 22px rgba(134,239,172,0.35),0 12px 28px rgba(0,0,0,0.45);border-radius:20px;padding:18px 20px;margin:14px auto 10px auto;max-width:680px;color:#ffffff}
.mka-hero-noti-title{font-size:20px;font-weight:800;margin-bottom:8px;display:flex;align-items:center;gap:8px}
.mka-hero-noti-sub{font-size:15px;color:#e2e8f0;margin-bottom:10px}
.mka-hero-track{width:100%;height:12px;background:#e5e7eb;border-radius:999px;overflow:hidden;margin-bottom:12px}
.mka-hero-fill{height:100%;background:#4ade80;border-radius:999px}

/* High-contrast page headers, location banner, text & labels */
.mka-page-header h1{color:#ffffff !important;-webkit-text-fill-color:#ffffff !important;font-weight:900 !important;text-shadow:0 2px 10px rgba(0,0,0,0.9) !important;margin-bottom:4px !important;}
.mka-page-sub{color:#f8fafc !important;-webkit-text-fill-color:#f8fafc !important;font-size:15px !important;font-weight:600 !important;text-shadow:0 1px 6px rgba(0,0,0,0.9) !important;margin-bottom:14px !important;}
.mka-loc-banner{display:flex;align-items:center;gap:8px;background:#09192f !important;border:1px solid #4ade80 !important;border-left:5px solid #4ade80 !important;border-radius:12px !important;padding:11px 16px !important;margin:10px 0 14px 0 !important;color:#ffffff !important;-webkit-text-fill-color:#ffffff !important;font-size:15px !important;font-weight:700 !important;box-shadow:0 6px 18px rgba(0,0,0,0.4) !important;opacity:1 !important;}
.mka-loc-banner .mka-loc-place{color:#86efac !important;-webkit-text-fill-color:#86efac !important;font-weight:800 !important;}
.mka-loc-banner .mka-loc-coords{color:#f8fafc !important;-webkit-text-fill-color:#f8fafc !important;font-weight:600 !important;}
.mka-loc-banner.info{border-color:#60a5fa !important;border-left-color:#60a5fa !important;}
.mka-track-card{background:#09192f !important;border:1px solid rgba(197,228,255,0.55) !important;border-radius:16px !important;padding:18px 20px !important;margin-top:14px !important;color:#ffffff !important;box-shadow:0 8px 24px rgba(0,0,0,0.45) !important;}
.mka-track-row{font-size:15px;line-height:1.6;margin:6px 0;color:#ffffff !important;-webkit-text-fill-color:#ffffff !important;}
.mka-track-row b{color:#93c5fd !important;-webkit-text-fill-color:#93c5fd !important;}
.mka-track-notes{margin-top:10px;padding:10px 14px;border-radius:10px;background:#153258 !important;border-left:4px solid #60a5fa !important;color:#ffffff !important;-webkit-text-fill-color:#ffffff !important;font-size:14px;}

/* Solid dark card for voice block & crisp text even without selection */
.stVerticalBlockBorderWrapper,
[data-testid="stVerticalBlockBorderWrapper"],
.stVerticalBlockBorderWrapper > div,
[data-testid="stVerticalBlockBorderWrapper"] > div {
    background-color: #09192f !important;
    border-radius: 16px !important;
    border-color: rgba(197, 228, 255, 0.55) !important;
    opacity: 1 !important;
}

.stVerticalBlockBorderWrapper :is(h1, h2, h3, h4, p, span, label, div, small, a),
[data-testid="stVerticalBlockBorderWrapper"] :is(h1, h2, h3, h4, p, span, label, div, small, a),
[data-testid="stExpander"] :is(h1, h2, h3, h4, p, span, label, div, small, a, summary) {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    opacity: 1 !important;
    mix-blend-mode: normal !important;
}

.stVerticalBlockBorderWrapper [data-testid="stCaptionContainer"] *,
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCaptionContainer"] *,
[data-testid="stCaptionContainer"] *,
.stCaption * {
    color: #e2e8f0 !important;
    -webkit-text-fill-color: #e2e8f0 !important;
    opacity: 1 !important;
    text-shadow: 0 1px 4px rgba(0, 0, 0, 0.85) !important;
}

/* Radio buttons & labels */
div[role="radiogroup"] label,
div[role="radiogroup"] label *,
[data-testid="stRadio"] label,
[data-testid="stRadio"] label * {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    opacity: 1 !important;
    font-weight: 600 !important;
}

/* Expander container */
[data-testid="stExpander"],
[data-testid="stExpander"] details,
[data-testid="stExpander"] summary,
[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
    background-color: #0e2442 !important;
    border-color: rgba(197, 228, 255, 0.4) !important;
    opacity: 1 !important;
}

/* Form field labels & markdown text */
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] *,
.stWidgetLabel,
.stWidgetLabel * {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    opacity: 1 !important;
    font-weight: 600 !important;
    text-shadow: 0 1px 5px rgba(0, 0, 0, 0.85) !important;
}
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] span {
    color: #f8fafc;
}
@media (max-width:900px){.mka-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.mka-kpi.donut{grid-column:1/-1}.mka-grid2{grid-template-columns:1fr}}
</style>
"""

_LOGIN_CSS = """
<style>

/* Sunset background area */
.st-key-mka_login_scene {
    background:
        linear-gradient(
            rgba(8, 27, 48, 0.10),
            rgba(8, 27, 48, 0.20)
        ),
        url("https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=1800&q=85");

    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;

    border: 1px solid rgba(255,255,255,0.35);
    border-radius: 16px;

    padding: 34px 16px;
    min-height: 420px;

    display: flex;
    align-items: center;
    justify-content: center;
}

/* Admin heading */
.mka-panel-title {
    background: linear-gradient(
        100deg,
        #092b49,
        #173b5c
    );

    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 12px;

    padding: 15px 24px;
    margin: 0 0 14px;
    min-height: 58px;
}

/* Responsive */
@media(max-width: 600px) {

    .st-key-mka_login_scene {
        padding: 20px 8px;
        min-height: 380px;
    }

}

</style>
"""


def _inject(*css: str) -> None:
    st.markdown("".join(css), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Completed Work banner (Home page)
# --------------------------------------------------------------------------


def render_notifications_banner() -> None:
    """Renders the Completed Work card above the proverb."""
    _inject(_BASE_CSS)
    raw_rows, _ = fetch_complaints() if database_configured() else ([], None)
    records = [normalise_record(r) for r in (raw_rows or [])]
    total = len(records)
    resolved_rows = [r for r in records if r["_bucket"] == "Resolved"]
    resolved_count = len(resolved_rows)
    pct = int(round((resolved_count / total) * 100)) if total > 0 else 0

    if resolved_rows:
        lines_html = "".join(
            f"<div style='font-size:14px;line-height:1.45;margin:6px 0;color:#f1f5f9;'>"
            f"- <b>Resolved:</b> {_esc(r['_category'])} ({_esc(r['_location'])}) - "
            f"{_esc(_shorten(r['_resolution_notes'] or r['_description'] or 'Completed', 65))} "
            f"- Updated {_esc(_date_label(r))}</div>"
            for r in resolved_rows[:2]
        )
    else:
        lines_html = (
            "<div style='font-size:14px;line-height:1.45;margin:6px 0;color:#cbd5e1;'>"
            "- No completed work updates recorded yet.</div>"
        )

    st.markdown(
        f"""
        <div class="mka-hero-noti">
            <div class="mka-hero-noti-title">✅ Completed Work</div>
            <div class="mka-hero-noti-sub">Progress: {resolved_count} of {total} resolved ({pct}% complete)</div>
            <div class="mka-hero-track"><div class="mka-hero-fill" style="width:{pct}%;"></div></div>
            {lines_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Maps
# --------------------------------------------------------------------------


def _popup_html(record: dict, show_description: bool) -> str:
    lines = [
        f'<div style="font-family:Arial,sans-serif;font-size:13px;min-width:170px">'
        f'<b>{_esc(record["_tracking_id"])}</b><br>'
        f'{_esc(record["_category"])} | {_esc(record["_location"])}<br>'
        f'<span style="font-weight:700">{_esc(record["_status"])}</span> · {_esc(_date_label(record))}'
    ]
    if show_description and record["_description"]:
        lines.append(f'<br><span style="color:#475569">{_esc(_shorten(record["_description"], 140))}</span>')
    lines.append("</div>")
    return "".join(lines)


def show_map(rows: list[dict], height: int = 450, key: str = "complaint_map", show_description: bool = True) -> None:
    """Folium map with one pin per complaint that has valid or resolved coordinates."""
    mappable = [r for r in rows if r.get("_latitude") is not None and r.get("_longitude") is not None]
    missing = len(rows) - len(mappable)

    if folium is None or st_folium is None:
        st.info("The map library is not installed, so the map cannot be displayed.")
        return
    if not mappable:
        st.info("No complaint coordinates available to display on the map.")
        return

    shown = mappable[:MAX_MAP_MARKERS]
    complaint_map = folium.Map(location=list(DEFAULT_MAP_CENTER), zoom_start=11)
    for r in shown:
        folium.Marker(
            location=[r["_latitude"], r["_longitude"]],
            tooltip=f'{r["_tracking_id"]} · {r["_category"]} ({r["_location"]})',
            popup=folium.Popup(_popup_html(r, show_description), max_width=280),
            icon=folium.Icon(color=BUCKET_COLORS.get(r["_bucket"], "gray"), icon="info-sign"),
        ).add_to(complaint_map)

    lats = [r["_latitude"] for r in shown]
    lons = [r["_longitude"] for r in shown]
    complaint_map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], padding=(30, 30), max_zoom=15)

    st_folium(
        complaint_map,
        use_container_width=True,
        height=height,
        returned_objects=[],
        key=key,
    )
    notes = []
    if len(mappable) > len(shown):
        notes.append(f"Showing the {len(shown)} most recent of {len(mappable)} located complaints.")
    if missing:
        notes.append(f"{missing} complaint(s) have no saved location and are not shown on the map.")
    if notes:
        st.caption(" ".join(notes))


def _legend_html() -> str:
    return (
        '<div class="mka-legend">'
        '<span><i style="background:#d33d2a"></i>Pending</span>'
        '<span><i style="background:#f69730"></i>In Progress</span>'
        '<span><i style="background:#72ad26"></i>Resolved</span>'
        '<span><i style="background:#7b7b7b"></i>Other</span></div>'
    )


# --------------------------------------------------------------------------
# Voice input (free: browser recognition + local Whisper, no API key)
# --------------------------------------------------------------------------


def _append_description(text: str) -> None:
    """Add recognised speech to the description without replacing existing text."""
    spoken = " ".join(_text(text).split())
    if not spoken:
        return
    existing = _text(st.session_state.get("mka_description"))
    st.session_state["mka_description"] = f"{existing} {spoken}" if existing else spoken


def _whisper_model_name() -> str:
    name = get_setting("WHISPER_MODEL", "tiny").lower()
    return name if name in WHISPER_MODELS else "tiny"


@st.cache_resource(show_spinner=False)
def _load_whisper_model(name: str):
    """Load the local Whisper model once per server process (CPU only)."""
    import whisper

    return whisper.load_model(name, device="cpu")


def _transcribe_local_whisper(audio_file, whisper_lang: str) -> str | None:
    """Transcribe a recording with Whisper run
