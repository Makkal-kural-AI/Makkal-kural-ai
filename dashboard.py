    options = df
    if query:
        options = df[
            df["tracking_id"].astype(str).str.contains(query, case=False, na=False, regex=False)
            | df["location"].astype(str).str.contains(query, case=False, na=False, regex=False)
        ]
    if options.empty:
        st.warning("No complaint matches that search.")
        return

    tracking_id = st.selectbox(
        "Select complaint tracking ID", options["tracking_id"].tolist(), key="mk_upd_id"
    )
    complaint = df[df["tracking_id"] == tracking_id].iloc[0]

    st.subheader("Complaint Details")
    st.write(f"**Complaint:** {complaint['complaint_text']}")
    st.write(f"**Location:** {complaint['location']}")
    st.write(f"**Category:** {complaint['category']}")
    st.write(f"**Submitted:** {complaint['submitted_at']}")
    st.write(f"**Current status:** {complaint['status']}")

    current = complaint["status"]
    new_status = st.selectbox(
        "Choose new status",
        STATUSES,
        index=STATUSES.index(current) if current in STATUSES else 0,
        key=f"mk_upd_status_{tracking_id}",
    )

    if st.button("Save Status", type="primary", key="mk_save_status"):
        if not _is_admin():  # check again right before changing data
            st.error("Please log in as an admin first.")
            return
        try:
            updated = update_status(tracking_id, new_status)
        except Exception as error:
            _show_error("Could not update the status", error)
            return
        if updated:
            refresh_data()
            _flash("success", f"Status of {tracking_id} changed to {new_status}.")
            st.rerun()
        else:
            st.error("No complaint was updated. Please check the tracking ID.")


def _admin_page(title, show_title, body):
    """Shared wrapper: title, login gate, data loading, error handling."""
    if show_title:
        st.title(title)
    if not _require_admin():
        return
    _admin_bar()
    _show_flash()
    try:
        df = load_complaints()
    except Exception as error:
        _show_error("Could not load complaints", error)
        return
    body(df)


def render_admin_dashboard(show_title=True):
    _admin_page("📊 Admin Dashboard", show_title, _admin_overview)


def render_admin_complaints(show_title=True):
    _admin_page("📋 All Complaints (Admin)", show_title, _admin_complaints)


def render_admin_update_status(show_title=True):
    _admin_page("🔄 Update Complaint Status", show_title, _admin_update)


def render_admin(show_title=True):
    """All admin tools on one page (used by app.py's Admin Dashboard page)."""

    def body(df):
        overview, complaints, update, admin_map = st.tabs(
            ["Overview", "All Complaints", "Update Status", "Map"]
        )
        with overview:
            _admin_overview(df)
        with complaints:
            _admin_complaints(df)
        with update:
            _admin_update(df)
        with admin_map:
            _render_map(df)

    _admin_page("🛡️ Admin Dashboard", show_title, body)


# ==========================================================================
# Standalone app (python -m streamlit run dashboard.py)
# ==========================================================================
def main():
    st.sidebar.title("📢 Makkal Kural AI")
    st.sidebar.caption("Public Complaint Management")

    pages = {
        "Submit Complaint": render_submit,
        "Track Complaint": render_tracking,
        "Public Complaints & Map": render_public,
        "Admin Dashboard": render_admin_dashboard,
        "All Complaints": render_admin_complaints,
        "Update Status": render_admin_update_status,
    }
    page = st.sidebar.radio("Navigation", list(pages))

    st.sidebar.divider()
    st.sidebar.caption("Helping communities report local problems.")

    pages[page]()


if __name__ == "__main__":
    if sys.argv[1:2] == ["--make-hash"]:
        import getpass

        chosen = getpass.getpass("Type the new admin password: ")
        if not chosen:
            sys.exit("Password cannot be empty.")
        print("Copy this value into ADMIN_USERS:")
        print(make_password_hash(chosen))
    else:
        main()
