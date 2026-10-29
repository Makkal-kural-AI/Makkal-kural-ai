"""
Makkal Kural AI — UI Dashboard Modules
Exports: render_submit(), render_tracking(), render_public(), render_admin()

This module only defines functions. Importing it never renders anything and it
never calls st.set_page_config() — app.py owns the page configuration.
"""

from __future__ import annotations

import hmac
import html
import math
import secrets
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

import streamlit as st

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


# --------------------------------------------------------------------------
# Data helpers
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

# The <style> block only exists while the page that emitted it is rendered, so
# these rules cannot leak onto the Home, Submit or Tracking pages.
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
[data-testid="stWidgetLabel"] p{color:#e6eefb !important}
@media (max-width:900px){.mka-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.mka-kpi.donut{grid-column:1/-1}.mka-grid2{grid-template-columns:1fr}}
</style>
"""

_LOGIN_CSS = """
<style>
.st-key-mka_login_scene{
  background:linear-gradient(180deg,#f7c777 0%,#f29a52 28%,#c9695b 52%,#5b5a86 72%,#2b3a5c 100%);
  border:1px solid rgba(255,255,255,.35);border-radius:16px;padding:34px 12px}
div[data-testid="stForm"]{background:#fff;border:0;border-radius:14px;padding:22px 24px 16px;
  box-shadow:0 18px 44px rgba(0,0,0,.35);color:#0f172a}
.mka-login-head{text-align:center;color:#0f172a;background:#fff;border-radius:10px;padding:4px 0;margin-bottom:6px}
.mka-login-head .shield{font-size:34px;line-height:1}
.mka-login-head .t{font-size:20px;font-weight:800;margin-top:4px}
.mka-login-head .s{font-size:12px;color:#64748b;margin-top:2px}
.mka-login-foot{text-align:center;color:#64748b;background:#fff;border-radius:8px;font-size:11px;margin-top:6px}
div[data-testid="stForm"] [data-testid="stTextInput"] input{text-align:center;letter-spacing:.7em;font-size:24px;font-weight:800;
  border-radius:10px;background:#f8fafc;color:#0f172a;border:1px solid #cbd5e1}
div[data-testid="stForm"] button[kind="secondaryFormSubmit"],div[data-testid="stForm"] button[kind="primaryFormSubmit"],
div[data-testid="stFormSubmitButton"] button{background:#2563eb !important;color:#fff !important;border:0 !important;
  border-radius:10px !important;font-weight:700 !important;min-height:46px}
div[data-testid="stFormSubmitButton"] button:hover{background:#1d4ed8 !important}
</style>
"""


def _inject(*css: str) -> None:
    st.markdown("".join(css), unsafe_allow_html=True)


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
    """Folium map with one pin per complaint that has valid saved coordinates."""
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
            tooltip=f'{r["_tracking_id"]} · {r["_category"]}',
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
# Citizen pages (unchanged behaviour, with verified bug fixes only)
# --------------------------------------------------------------------------


def render_submit() -> None:
    st.title("📝 Submit a Complaint")
    st.caption("Select your location on the map and fill in the issue details.")

    default_lat, default_lon = DEFAULT_MAP_CENTER
    selected_lat, selected_lon = None, None

    if folium is not None and st_folium is not None:
        m = folium.Map(location=[default_lat, default_lon], zoom_start=12)
        m.add_child(folium.LatLngPopup())
        map_data = st_folium(m, height=320, use_container_width=True, key="submit_map")
        if map_data and map_data.get("last_clicked"):
            selected_lat = map_data["last_clicked"]["lat"]
            selected_lon = map_data["last_clicked"]["lng"]
            st.success(f"Selected Coordinates: Lat {selected_lat:.5f}, Lon {selected_lon:.5f}")

    with st.form("submit_form"):
        category = st.selectbox(
            "Category",
            ["Water Supply", "Garbage", "Road Damage", "Drainage", "Electricity", "Other"],
        )
        location_name = st.text_input("Village / Area Name")
        description = st.text_area("Complaint Details")
        if st.form_submit_button("Submit Complaint", type="primary", use_container_width=True):
            if not description.strip():
                st.error("Please provide complaint details.")
            else:
                trk_id = f"MKAI-{secrets.randbelow(900000) + 100000}"
                payload = {
                    "tracking_id": trk_id,
                    "category": category,
                    "description": description.strip(),
                    "location": location_name.strip(),
                    "latitude": selected_lat,
                    "longitude": selected_lon,
                    "status": "Submitted",
                }
                if save_complaint(payload):
                    st.success(f"Complaint registered successfully! Tracking ID: **{trk_id}**")


def render_tracking() -> None:
    st.title("🔎 Track Complaint Status")
    tracking_id = st.text_input("Enter your Tracking ID").strip()
    if tracking_id:
        records = get_complaint_by_tracking_id(tracking_id)
        if records:
            for item in records:
                r = normalise_record(item)
                st.success(f"Tracking ID: {r['_tracking_id']}")
                st.write(f"**Status:** {r['_status']}")
                st.write(f"**Category:** {r['_category']}")
                st.write(f"**Location:** {r['_location']}")
                st.write(f"**Description:** {r['_description']}")
                if r["_resolution_notes"]:
                    st.info(f"**Resolution Notes:** {r['_resolution_notes']}")
        else:
            st.warning("No complaint found matching that Tracking ID.")


# --------------------------------------------------------------------------
# All Complaints page
# --------------------------------------------------------------------------


def _public_table_html(records: list[dict]) -> str:
    head = "<tr><th>ID</th><th>Category</th><th>Location</th><th>Status</th></tr>"
    body = []
    for r in records[:PUBLIC_TABLE_ROWS]:
        extra = ""
        if PUBLIC_SHOW_DESCRIPTION and r["_description"]:
            extra = f'<small>{_esc(_shorten(r["_description"], 70))}</small>'
        body.append(
            f'<tr><td class="id">{_esc(r["_tracking_id"])}<small>{_esc(_date_label(r))}</small></td>'
            f'<td>{_esc(r["_category"])}{extra}</td><td>{_esc(r["_location"])}</td><td>{_pill(r)}</td></tr>'
        )
    return f'<div class="mka-tablewrap"><table class="mka-table"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


def render_public() -> None:
    _inject(_BASE_CSS)
    st.markdown(_panel_title("📋", "Public Complaints & Interactive Map"), unsafe_allow_html=True)

    records = _load_records()
    if records is None:
        return
    if not records:
        st.info("No complaints have been submitted yet.")
        return

    f1, f2, f3 = st.columns([3, 2, 2])
    search = f1.text_input("Search", placeholder="Search by ID, category or area", key="pub_search")
    status_choice = f2.selectbox("Status", ["All", "Pending", "In Progress", "Resolved"], key="pub_status")
    categories = ["All"] + [label for label, _ in _group_counts([r["_category"] for r in records])]
    category_choice = f3.selectbox("Category", categories, key="pub_category")

    needle = search.strip().casefold()
    filtered = [
        r
        for r in records
        if _matches(r, needle, PUBLIC_SHOW_DESCRIPTION)
        and (status_choice == "All" or r["_bucket"] == status_choice)
        and (category_choice == "All" or r["_category"].casefold() == category_choice.casefold())
    ]

    left, right = st.columns([5, 7])
    with left:
        st.markdown(
            '<div class="mka-card-head" style="color:#fff">Recent Complaints Table</div>',
            unsafe_allow_html=True,
        )
        if filtered:
            st.markdown(_public_table_html(filtered), unsafe_allow_html=True)
            if len(filtered) > PUBLIC_TABLE_ROWS:
                st.caption(f"Showing the latest {PUBLIC_TABLE_ROWS} of {len(filtered)} matching complaints. Use search to narrow the list.")
            else:
                st.caption(f"{len(filtered)} complaint(s).")
        else:
            st.info("No complaints match your search or filters.")
    with right:
        st.markdown(_legend_html(), unsafe_allow_html=True)
        show_map(filtered, height=520, key="public_map", show_description=PUBLIC_SHOW_DESCRIPTION)


# --------------------------------------------------------------------------
# Admin login
# --------------------------------------------------------------------------


def _init_admin_state() -> None:
    st.session_state.setdefault("mka_failed_attempts", 0)
    st.session_state.setdefault("mka_lockout_until", 0.0)
    st.session_state.setdefault("mka_admin_authenticated", False)


def _keys_match(supplied: str, expected: str) -> bool:
    return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


def _render_admin_login() -> None:
    _inject(_BASE_CSS, _LOGIN_CSS)

    now = time.time()
    if st.session_state["mka_lockout_until"] and now >= st.session_state["mka_lockout_until"]:
        st.session_state["mka_lockout_until"] = 0.0
        st.session_state["mka_failed_attempts"] = 0
    locked = now < st.session_state["mka_lockout_until"]
    remaining = int(math.ceil(st.session_state["mka_lockout_until"] - now)) if locked else 0

    # Read at request time from secrets / environment; never hard-coded.
    expected = get_setting("ADMIN_ACCESS_KEY")
    configured = len(expected) == 6 and expected.isdigit()
    disabled = locked or not configured

    badge = "Locked" if locked else ("Not configured" if not configured else "Awaiting Key")
    st.markdown(
        _panel_title("🔒", "Admin Verification", badge, "locked" if disabled else ""),
        unsafe_allow_html=True,
    )

    with st.container(key="mka_login_scene"):
        _, middle, _ = st.columns([1, 2, 1])
        with middle:
            with st.form("admin_auth_form", clear_on_submit=True):
                st.markdown(
                    '<div class="mka-login-head"><div class="shield">🛡️</div>'
                    '<div class="t">Admin Access</div>'
                    '<div class="s">Enter the 6-digit access key to continue</div></div>',
                    unsafe_allow_html=True,
                )
                code = st.text_input(
                    "Access Key",
                    type="password",
                    max_chars=6,
                    placeholder="••••••",
                    label_visibility="collapsed",
                    disabled=disabled,
                )
                submitted = st.form_submit_button("Confirm →", use_container_width=True, disabled=disabled)
                st.markdown('<div class="mka-login-foot">🔒 Authorized personnel only</div>', unsafe_allow_html=True)

    if not configured:
        st.error(
            "Admin access is not configured. Set ADMIN_ACCESS_KEY to a six-digit number "
            "in the server environment or Streamlit secrets."
        )
        return
    if locked:
        st.error(f"Too many incorrect attempts. Try again in {remaining} seconds.")
        return
    if not submitted:
        return

    code = (code or "").strip()
    if len(code) != 6 or not code.isdigit():
        st.warning("Enter all 6 digits of the access key.")
    elif _keys_match(code, expected):
        st.session_state["mka_admin_authenticated"] = True
        st.session_state["mka_failed_attempts"] = 0
        st.session_state["mka_lockout_until"] = 0.0
        st.rerun()
    else:
        st.session_state["mka_failed_attempts"] += 1
        attempts = st.session_state["mka_failed_attempts"]
        if attempts >= MAX_FAILED_ATTEMPTS:
            st.session_state["mka_lockout_until"] = time.time() + LOCKOUT_SECONDS
            st.error(f"Maximum attempts exceeded. Locked for {LOCKOUT_SECONDS} seconds.")
        else:
            st.error(f"Incorrect access key. ({attempts}/{MAX_FAILED_ATTEMPTS} failed attempts)")


# --------------------------------------------------------------------------
# Admin dashboard
# --------------------------------------------------------------------------


def _admin_table_html(records: list[dict]) -> str:
    head = "<tr><th>ID</th><th>Category</th><th>Description</th><th>Location</th><th>Status</th><th>Reported</th></tr>"
    body = []
    for r in records:
        description = r["_description"]
        body.append(
            f'<tr><td class="id">{_esc(r["_tracking_id"])}</td><td>{_esc(r["_category"])}</td>'
            f'<td title="{_esc(" ".join(description.split()))}">{_esc(_shorten(description, 80)) or "—"}</td>'
            f'<td>{_esc(r["_location"])}</td><td>{_pill(r)}</td><td class="muted">{_esc(_date_label(r, True))}</td></tr>'
        )
    return f'<div class="mka-tablewrap"><table class="mka-table"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


def _render_update_form(selected: dict) -> None:
    tid = selected["_tracking_id"]
    coords = (
        f'{selected["_latitude"]:.5f}, {selected["_longitude"]:.5f}'
        if selected["_latitude"] is not None
        else "not saved"
    )
    st.markdown(
        '<div class="mka-card">'
        f'<div class="mka-card-head"><span>{_esc(tid)} · {_esc(selected["_category"])}</span>{_pill(selected)}</div>'
        f'<div style="font-size:13px;color:#334155"><b>Location:</b> {_esc(selected["_location"])} '
        f'&nbsp;·&nbsp; <b>Coordinates:</b> {_esc(coords)} &nbsp;·&nbsp; <b>Reported:</b> {_esc(_date_label(selected, True))}</div>'
        f'<div style="font-size:14px;margin-top:8px;color:#0f172a">{_esc(selected["_description"]) or "No description provided."}</div>'
        "</div>",
        unsafe_allow_html=True,
    )

    options = list(STATUSES)
    if selected["_status"] not in options:
        options.append(selected["_status"])
    with st.form(f"mka_update_{tid}"):
        new_status = st.selectbox("New status", options, index=options.index(selected["_status"]))
        notes = st.text_area("Resolution notes (optional)", value=selected["_resolution_notes"])
        if st.form_submit_button("Save update", type="primary"):
            if update_status(tid, new_status, notes):
                st.session_state["mka_flash"] = f"{tid} updated to {new_status}."
                st.rerun()


def _render_admin_dashboard() -> None:
    _inject(_BASE_CSS)

    title_col, logout_col = st.columns([5, 1], vertical_alignment="center")
    with title_col:
        st.markdown(_panel_title("📊", "Admin Dashboard & Analytics"), unsafe_allow_html=True)
    with logout_col:
        if st.button("Log out", use_container_width=True, key="mka_logout"):
            st.session_state["mka_admin_authenticated"] = False
            st.session_state.pop("mka_flash", None)
            st.rerun()

    flash = st.session_state.pop("mka_flash", None)
    if flash:
        st.success(flash)

    all_records = _load_records()
    if all_records is None:
        return
    if not all_records:
        st.info("No complaints have been submitted yet. Statistics will appear after the first report.")
        return

    # ---- Region filter + statistics -------------------------------------
    regions = ["All regions"] + _region_options(all_records)
    region_choice = st.selectbox("Region", regions, key="mka_region")
    records = (
        all_records
        if region_choice == "All regions"
        else [r for r in all_records if r["_region"].casefold() == region_choice.casefold()]
    )

    total = len(records)
    pending = sum(1 for r in records if r["_bucket"] == "Pending")
    progress = sum(1 for r in records if r["_bucket"] == "In Progress")
    resolved = sum(1 for r in records if r["_bucket"] == "Resolved")
    other = total - pending - progress - resolved
    rate = round(resolved / total * 100) if total else 0

    categories = _group_counts([r["_category"] for r in records])
    chart_items = categories[:6]
    if len(categories) > 6:
        chart_items.append(("Others", sum(n for _, n in categories[6:])))
    points, undated = _trend_points(records)

    notes = []
    if other:
        notes.append(f"{other} complaint(s) use a custom status and are counted only in Total Reports.")
    if undated:
        notes.append(f"{undated} complaint(s) have no recorded date and are not in the trend.")
    note_html = f'<div class="mka-note">{_esc(" ".join(notes))}</div>' if notes else ""

    st.markdown(
        '<div class="mka-sheet">'
        + _kpi_html(total, pending, progress, resolved, rate)
        + '<div class="mka-grid2">'
        f'<div class="mka-card"><div class="mka-card-head"><span>Complaints by Category</span></div>{_bar_chart_svg(chart_items)}</div>'
        '<div class="mka-card"><div class="mka-card-head"><span>Progress Trend · reports received</span><small>Last 7 days</small></div>'
        f"{_line_chart_svg(points)}</div></div>{note_html}</div>",
        unsafe_allow_html=True,
    )

    # ---- Complaint status management ------------------------------------
    st.markdown('<div class="mka-section">Complaint Status Management</div>', unsafe_allow_html=True)
    f1, f2, f3, f4 = st.columns([3, 2, 2, 1])
    search = f1.text_input("Search", placeholder="Search by ID, category, area or description", key="mka_search")
    status_choice = f2.selectbox("Status", ["All", "Pending", "In Progress", "Resolved", "Other"], key="mka_status_filter")
    category_choice = f3.selectbox("Category", ["All"] + [label for label, _ in categories], key="mka_category_filter")
    page_size = f4.selectbox("Rows", [10, 25, 50, 100], index=1, key="mka_page_size")

    needle = search.strip().casefold()
    filtered = [
        r
        for r in records
        if _matches(r, needle, True)
        and (status_choice == "All" or r["_bucket"] == status_choice)
        and (category_choice == "All" or r["_category"].casefold() == category_choice.casefold())
    ]

    if not filtered:
        st.info("No complaints match your search or filters.")
    else:
        pages = max(1, math.ceil(len(filtered) / page_size))
        page = 1
        if pages > 1:
            page = int(st.number_input("Page", min_value=1, max_value=pages, value=1, step=1, key="mka_page"))
        start = (page - 1) * page_size
        st.markdown(_admin_table_html(filtered[start : start + page_size]), unsafe_allow_html=True)
        st.caption(f"Showing {start + 1}–{min(start + page_size, len(filtered))} of {len(filtered)} complaint(s).")

        st.markdown('<div class="mka-section">Update a Complaint</div>', unsafe_allow_html=True)
        by_id = {r["_tracking_id"]: r for r in filtered}
        selected_id = st.selectbox(
            "Select complaint",
            list(by_id.keys()),
            format_func=lambda tid: f'{tid} · {by_id[tid]["_category"]} ({by_id[tid]["_status"]})',
            key="mka_selected",
        )
        _render_update_form(by_id[selected_id])

    # ---- Map -------------------------------------------------------------
    st.markdown('<div class="mka-section">Live Complaint Map</div>', unsafe_allow_html=True)
    st.markdown(_legend_html(), unsafe_allow_html=True)
    show_map(filtered, height=450, key="admin_map", show_description=True)


def render_admin() -> None:
    _init_admin_state()
    if not st.session_state["mka_admin_authenticated"]:
        _render_admin_login()
        return
    _render_admin_dashboard()
