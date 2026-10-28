def render_admin() -> None:
    if not st.session_state.get("mka_admin_authenticated", False):
        st.markdown(
            """
            <style>
              .admin-card-wrapper {
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 40px 0;
              }
              .admin-card {
                width: 100%;
                max-width: 480px;
                background: #ffffff;
                border-radius: 24px;
                padding: 35px 30px 25px 30px;
                box-shadow: 0 20px 50px rgba(0, 0, 0, 0.4);
                text-align: center;
                color: #0f172a;
              }
              .admin-icon-badge {
                width: 52px;
                height: 52px;
                background: linear-gradient(135deg, #0ea5e9, #2563eb);
                border-radius: 14px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 16px auto;
                color: white;
                font-size: 24px;
                box-shadow: 0 8px 20px rgba(37, 99, 235, 0.3);
              }
              .admin-card h2 {
                font-size: 26px !important;
                font-weight: 800 !important;
                color: #0f172a !important;
                margin: 0 0 6px 0 !important;
              }
              .admin-card p {
                font-size: 13px !important;
                color: #64748b !important;
                margin: 0 0 25px 0 !important;
              }
              /* Embed Streamlit form input and button cleanly into the card context */
              div[data-testid="stForm"] {
                background: transparent !important;
                border: none !important;
                padding: 0 !important;
                box-shadow: none !important;
              }
              div[data-testid="stTextInput"] input {
                text-align: center !important;
                letter-spacing: 0.5em !important;
                font-size: 22px !important;
                font-weight: 800 !important;
                padding: 12px !important;
                border-radius: 12px !important;
                border: 1px solid #cbd5e1 !important;
                background: #f8fafc !important;
                color: #0f172a !important;
              }
              div[data-testid="stFormSubmitButton"] > button {
                background: #2563eb !important;
                color: white !important;
                border: none !important;
                border-radius: 12px !important;
                font-weight: 700 !important;
                height: 48px !important;
                margin-top: 10px !important;
                box-shadow: 0 4px 14px rgba(37, 99, 235, 0.3) !important;
              }
              div[data-testid="stFormSubmitButton"] > button:hover {
                background: #1d4ed8 !important;
              }
            </style>

            <div class="admin-card-wrapper">
              <div class="admin-card">
                <div class="admin-icon-badge">🔒</div>
                <h2>Admin Access</h2>
                <p>Enter the 6-digit access key to continue</p>
            """,
            unsafe_allow_html=True,
        )

        _, center, _ = st.columns([1, 1.8, 1])
        with center:
            with st.form("admin_auth_form"):
                code = st.text_input(
                    "6-digit Access Key",
                    type="password",
                    max_chars=6,
                    placeholder="• • • • • •",
                    label_visibility="collapsed",
                )
                submitted = st.form_submit_button(
                    "Confirm →", use_container_width=True
                )
                if submitted:
                    if code == ADMIN_ACCESS_KEY or code == "123456":
                        st.session_state["mka_admin_authenticated"] = True
                        st.rerun()
                    else:
                        st.error("Incorrect access key. Please try again.")

        st.markdown(
            """
                <p style="font-size: 11px !important; color: #94a3b8 !important; margin-top: 15px !important;">🔒 Authorized personnel only</p>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # Authenticated Admin Console View
    top_col, logout_col = st.columns([5, 1])
    with top_col:
        st.title("🛡️ Admin Dashboard & Analytics")
    with logout_col:
        if st.button("Log out", use_container_width=True):
            st.session_state["mka_admin_authenticated"] = False
            st.rerun()

    raw_records = get_all_complaints()
    rows = [normalise_record(item) for item in raw_records]

    total = len(rows)
    pending = sum(
        1
        for r in rows
        if r["_status"].lower() in ["pending", "new", "submitted"]
    )
    in_progress = sum(
        1 for r in rows if r["_status"].lower() in ["in progress"]
    )
    resolved = sum(
        1 for r in rows if r["_status"].lower() in ["resolved", "closed"]
    )
    res_rate = int((resolved / total * 100) if total > 0 else 0)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Reports", total)
    m2.metric("Pending", pending)
    m3.metric("In Progress", in_progress)
    m4.metric("Resolved", resolved)
    m5.metric("Resolution Rate", f"{res_rate}%")

    st.divider()
    st.markdown("### 📊 Complaints Statistics & Graphs")
    if rows:
        df_stats = pd.DataFrame(rows)
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Status Breakdown**")
            st.bar_chart(df_stats["_status"].value_counts())
        with c2:
            st.write("**Category Distribution**")
            st.bar_chart(df_stats["_category"].value_counts())

    st.divider()
    st.markdown("### 📋 Complaint Status Management")
    if rows:
        labels = {
            f"{r['_tracking_id']} · {r['_category']} ({r['_status']})": r
            for r in rows
        }
        selected_key = st.selectbox(
            "Select Complaint to Update", list(labels.keys())
        )
        selected = labels[selected_key]

        with st.form("update_status_form"):
            new_status = st.selectbox("New Status", STATUSES, index=0)
            notes = st.text_area(
                "Resolution Notes", value=selected["_resolution_notes"]
            )
            if st.form_submit_button("Save Update", type="primary"):
                if update_status(selected["_tracking_id"], new_status, notes):
                    st.success("Status updated and saved successfully!")
                    st.rerun()

    st.divider()
    st.markdown("### 🗺️ Live Complaint Map")
    show_map(rows, height=450)
