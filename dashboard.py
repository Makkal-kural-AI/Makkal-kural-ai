            {summary_html}
            <div style="font-size:12px;font-weight:700;color:#94a3b8;margin:12px 0 4px;">LATEST ACTIVITY</div>
            {recent_items}
        </div>
        """,
        unsafe_allow_html=True,
    )


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
        if selected["_latitude"] is not None and selected["_longitude"] is not None
        else "not saved"
    )
    st.markdown(
        '<div class="mka-card">'
        f'<div class="mka-card-head"><span>{_esc(tid)} · {_esc(selected["_category"])}</span>{_pill(selected)}</div>'
        f'<div style="font-size:13px;color:#334155"><b>Location:</b> {_esc(selected["_location"])} '
        f"&nbsp;·&nbsp; <b>Coordinates:</b> {_esc(coords)} &nbsp;·&nbsp; <b>Reported:</b> {_esc(_date_label(selected, True))}</div>"
        f'<div style="font-size:14px;margin-top:8px;color:#0f172a">{_esc(selected["_description"]) or "No description provided."}</div>'
        "</div>",
        unsafe_allow_html=True,
    )

    options = list(STATUSES)
    if selected["_status"] not in options:
        options.append(selected["_status"])
    with st.form(f"mka_update_{tid}"):
        new_status = st.selectbox("New status", options, index=options.index(selected["_status"]))
        notes = st.text_area("Resolution notes", value=selected["_resolution_notes"])
        if st.form_submit_button("Save update", type="primary"):
            if update_status(tid, new_status, notes):
                st.success("Status updated.")
                st.rerun()


def render_admin() -> None:
    _init_admin_state()
    if not st.session_state["mka_admin_authenticated"]:
        _render_admin_login()
        return

    _inject(_BASE_CSS)
    top_l, top_r = st.columns([6, 1])
    with top_l:
        st.markdown(_panel_title("🛡️", "Admin Dashboard"), unsafe_allow_html=True)
    with top_r:
        if st.button("Log out", use_container_width=True, key="mka_admin_logout"):
            st.session_state["mka_admin_authenticated"] = False
            st.rerun()

    records = _load_records()
    if records is None:
        return

    _render_admin_notifications(records)

    total = len(records)
    pending = sum(1 for r in records if r["_bucket"] == "Pending")
    in_progress = sum(1 for r in records if r["_bucket"] == "In Progress")
    resolved = sum(1 for r in records if r["_bucket"] == "Resolved")
    pct = int(round((resolved / total) * 100)) if total > 0 else 0

    cat_items = _group_counts([r["_category"] for r in records])
    trend_pts, undated_count = _trend_points(records, days=7)
    undated_note = (
        f"<div class='mka-note'>{undated_count} record(s) have no timestamp and are excluded from the daily trend.</div>"
        if undated_count
        else ""
    )

    st.markdown(
        f"""
        <style>
        .mka-sheet [data-testid="stMarkdownContainer"]:empty {{ display: none; }}
        </style>
        <div class="mka-sheet">
            {_kpi_html(total, pending, in_progress, resolved, pct)}
            <div class="mka-grid2">
                <div class="mka-card">
                    <div class="mka-card-head">Complaints by Category <small>{len(cat_items)} categories</small></div>
                    {_bar_chart_svg(cat_items)}
                </div>
                <div class="mka-card">
                    <div class="mka-card-head">Reports Received (7 Days) <small>IST</small></div>
                    {_line_chart_svg(trend_pts)}
                    {undated_note}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="mka-section">📋 All Registered Complaints</div>', unsafe_allow_html=True)
    if records:
        st.markdown(_admin_table_html(records), unsafe_allow_html=True)
        st.markdown('<div class="mka-section">✏️ Update Complaint Status</div>', unsafe_allow_html=True)
        options_map = {
            f"{r['_tracking_id']} · {r['_category']} · {r['_location']} ({r['_status']})": r
            for r in records
        }
        chosen_label = st.selectbox("Select a complaint", list(options_map.keys()), key="mka_admin_select")
        _render_update_form(options_map[chosen_label])
    else:
        st.info("No complaints found.")

    st.markdown('<div class="mka-section">🗺️ Complaint Map</div>', unsafe_allow_html=True)
    st.markdown(_legend_html(), unsafe_allow_html=True)
    show_map(records, height=450, key="admin_map", show_description=True)
