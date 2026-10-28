"""Makkal Kural AI pages: complaint submission, tracking, public list, admin analytics."""
import hmac, os
import pandas as pd
import streamlit as st
from database import get_all_complaints, get_complaint, save_complaint, update_status
from classifier import classify_complaint

BG = "https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=1920&q=85"
STATUSES = ["Submitted", "Pending", "In Progress", "Resolved", "Rejected"]

def apply_app_style():
    st.markdown(f"""<style>
    .stApp {{background:linear-gradient(rgba(5,20,38,.72),rgba(5,20,38,.80)),url('{BG}');background-size:cover;background-position:center;background-attachment:fixed;}}
    [data-testid='stHeader']{{background:transparent}} [data-testid='stMainBlockContainer']{{max-width:1250px;padding-top:1.5rem}}
    h1,h2,h3,p,label,[data-testid='stMarkdownContainer']{{color:#fff}}
    [data-testid='stVerticalBlockBorderWrapper']{{background:rgba(10,31,52,.82);border:1px solid #ffffff33;border-radius:16px}}
    .stTextInput input,.stTextArea textarea{{background:#fff;color:#152033;border-radius:9px}}
    .stButton>button,.stFormSubmitButton>button{{background:#0759a6;color:white;border-radius:10px;border:1px solid #b7d7f5;min-height:42px;font-weight:700}}
    .stButton>button:hover,.stFormSubmitButton>button:hover{{background:#0877ce;color:white}}
    .metric-card{{padding:14px;border-radius:12px;background:#ffffff18;border:1px solid #ffffff30}}
    </style>""", unsafe_allow_html=True)

def page_heading(title, subtitle=""):
    st.title(title)
    if subtitle: st.caption(subtitle)

def _load_df():
    rows = get_all_complaints()
    df = pd.DataFrame(rows or [])
    if df.empty: return df
    aliases = {"submitted_at":"created_at", "complaint_text":"description"}
    for target, source in aliases.items():
        if target not in df.columns and source in df.columns: df[target] = df[source]
    return df

def render_submit(show_title=True):
    apply_app_style()
    if show_title: page_heading("Submit a Complaint", "Describe the issue and keep the tracking ID shown after saving.")
    with st.container(border=True):
        st.subheader("Complaint details")
        if "voice_result" not in st.session_state: st.session_state.voice_result = None
        try:
            audio = st.audio_input("Record your complaint in Tamil or English")
        except Exception:
            audio = None
            st.info("Audio input is not available in this Streamlit version. You can type the complaint below.")
        if audio is not None:
            audio_bytes = audio.getvalue()
            import hashlib
            audio_hash = hashlib.sha256(audio_bytes).hexdigest()
            if st.session_state.get("voice_hash") != audio_hash:
                try:
                    from voice_ai import process_complaint_audio
                    with st.spinner("Recognizing speech… first run may download the Whisper model."):
                        result = process_complaint_audio(audio_bytes)
                    if result:
                        st.session_state.voice_result = result
                        st.session_state.voice_hash = audio_hash
                        st.session_state["complaint_text_entry"] = result.get("original", "")
                        st.success(f"Detected language: {result['language']}. Check the transcript before submitting.")
                    else: st.warning("Speech was not recognized. Please try again or type your complaint.")
                except Exception as exc: st.error(f"Voice recognition failed: {exc}")
        voice = st.session_state.get("voice_result") or {}
        if voice:
            st.markdown("**Recognized original speech**")
            st.write(voice.get("original", ""))
            if voice.get("language") == "ta" and voice.get("english"):
                with st.expander("English translation (for review)"):
                    st.write(voice["english"])
        initial_text = voice.get("original", "")
        description = st.text_area("Complaint description (Tamil or English)", value=initial_text, height=130, key="complaint_text_entry", placeholder="Type your complaint here…")
        categories = ["Auto-detect", "Garbage", "Drainage", "Water Supply", "Water Leakage", "Road Damage", "Street Light", "Electricity", "Public Safety", "Public Toilets", "Stray Animals", "Mosquitoes and Pests", "Other"]
        category_choice = st.selectbox("Category", categories, index=0)
        location = st.text_input("Village / street / landmark", placeholder="e.g. Anna Nagar, Chennai")
        col1, col2 = st.columns(2)
        with col1: lat_text = st.text_input("Latitude (optional)", placeholder="Needed only for map pin")
        with col2: lon_text = st.text_input("Longitude (optional)", placeholder="Needed only for map pin")
        if st.button("Submit complaint", type="primary", use_container_width=True, key="submit_complaint"):
            if not description.strip(): st.error("Enter or record a complaint."); return
            if not location.strip(): st.error("Enter the complaint location."); return
            try:
                lat = float(lat_text) if lat_text.strip() else None
                lon = float(lon_text) if lon_text.strip() else None
                if lat is not None and not -90 <= lat <= 90: st.error("Latitude must be between -90 and 90."); return
                if lon is not None and not -180 <= lon <= 180: st.error("Longitude must be between -180 and 180."); return
            except ValueError:
                st.error("Latitude and longitude must be valid numbers."); return
            category = classify_complaint(description) if category_choice == "Auto-detect" else category_choice
            try:
                with st.spinner("Saving complaint…"):
                    tracking_id, created_at = save_complaint(description.strip(), category, location.strip(), latitude=lat, longitude=lon)
                st.session_state.last_tracking_id = tracking_id
                st.success("Complaint submitted successfully!")
                st.code(tracking_id, language=None)
                st.caption(f"Submitted at: {created_at}. Save this tracking ID to check progress.")
                language = (voice.get("language") or "en")
                try:
                    from voice_ai import confirmation_audio
                    st.audio(confirmation_audio(language), format="audio/mp3")
                except Exception: pass
                st.session_state.voice_result = None
                st.session_state.voice_hash = None
            except Exception as exc:
                # Keep a local copy if the cloud database cannot be reached.
                try:
                    from offline_storage import save_offline_complaint
                    local_id = save_offline_complaint(description.strip(), category, location.strip())
                    st.warning("The cloud database is unavailable. Your complaint is saved in this server's local offline queue, but it has not yet received a tracking ID.")
                    st.caption(f"Offline reference: {local_id}. An administrator must sync it when connectivity returns.")
                except Exception as offline_exc:
                    st.error(f"We could not confirm that the complaint was saved online or offline. Online error: {exc}. Offline error: {offline_exc}")

def render_tracking(show_title=True):
    apply_app_style()
    if show_title: page_heading("Track your complaint", "Use the tracking ID shown after submission.")
    with st.form("tracking_form"):
        tracking_id = st.text_input("Tracking ID", value=st.session_state.get("last_tracking_id", ""), placeholder="MKAI-XXXXXXXXXX")
        submitted = st.form_submit_button("Check status", use_container_width=True)
    if submitted:
        if not tracking_id.strip(): st.warning("Enter a tracking ID."); return
        try: complaint = get_complaint(tracking_id)
        except Exception as exc: st.error(f"Could not check status: {exc}"); return
        if not complaint: st.warning("No complaint found for that tracking ID."); return
        st.success(f"Current status: {complaint.get('status', 'Unknown')}")
        for label, key in [("Tracking ID","tracking_id"),("Complaint","description"),("Category","category"),("Location","location"),("Submitted","created_at"),("Resolution note","resolution_note")]:
            value = complaint.get(key)
            if value: st.write(f"**{label}:** {value}")
        if complaint.get("status") == "Resolved": st.toast("Your complaint has been marked resolved.", icon="✅")

def render_public(show_title=True):
    apply_app_style()
    if show_title: page_heading("Complaint status board", "Public summary of submitted complaints. Sensitive personal details are not displayed.")
    try: df = _load_df()
    except Exception as exc: st.error(f"Could not load complaints: {exc}"); return
    if df.empty: st.info("No complaints have been submitted yet."); return
    for col in ["tracking_id","description","location","category","status","created_at","latitude","longitude"]:
        if col not in df.columns: df[col] = None
    c1,c2,c3 = st.columns(3)
    with c1: search = st.text_input("Search tracking ID or location")
    with c2: category = st.selectbox("Category", ["All"]+sorted(df.category.fillna("Other").astype(str).unique().tolist()))
    with c3: status = st.selectbox("Status", ["All"]+sorted(df.status.fillna("Submitted").astype(str).unique().tolist()))
    filtered=df.copy()
    if search.strip(): filtered=filtered[filtered.apply(lambda r: search.casefold() in f"{r.get('tracking_id','')} {r.get('location','')}".casefold(),axis=1)]
    if category != "All": filtered=filtered[filtered.category.astype(str)==category]
    if status != "All": filtered=filtered[filtered.status.astype(str)==status]
    st.caption(f"{len(filtered)} complaint(s)")
    display=filtered[["tracking_id","category","location","status","created_at"]].rename(columns={"tracking_id":"Tracking ID","category":"Category","location":"Location","status":"Status","created_at":"Submitted"})
    st.dataframe(display, use_container_width=True, hide_index=True)
    valid=filtered.copy()
    valid["latitude"]=pd.to_numeric(valid.latitude,errors="coerce"); valid["longitude"]=pd.to_numeric(valid.longitude,errors="coerce")
    valid=valid.dropna(subset=["latitude","longitude"])
    st.subheader("Complaint map")
    if not valid.empty:
        try:
            import folium
            from streamlit_folium import st_folium
            center=[float(valid.latitude.mean()),float(valid.longitude.mean())]
            m=folium.Map(location=center,zoom_start=11,control_scale=True)
            for _,r in valid.iterrows():
                popup=f"{r.get('tracking_id','')} | {r.get('category','')} | {r.get('status','')}"
                folium.Marker([r.latitude,r.longitude],popup=popup,tooltip=str(r.get("location","Complaint"))).add_to(m)
            st_folium(m, use_container_width=True, height=380, returned_objects=[])
        except Exception as exc: st.info(f"Map could not load: {exc}")
    else: st.info("Map pins appear when a complaint is submitted with coordinates. A place name alone cannot reliably determine a map pin; add geocoding in a later step.")

def _verify_admin_key(key):
    expected=os.getenv("ADMIN_ACCESS_KEY", "").strip()
    return bool(expected) and hmac.compare_digest(str(key), expected)

def _admin_login():
    apply_app_style()
    st.markdown("<div style='text-align:center'><h2>🔐 ADMIN ACCESS</h2><p>Enter your six-digit access key</p></div>", unsafe_allow_html=True)
    if not os.getenv("ADMIN_ACCESS_KEY", "").strip():
        st.error("Admin access is not configured. Set ADMIN_ACCESS_KEY in your hosting environment.")
        return False
    with st.form("admin_key_form"):
        boxes=st.columns(6, gap="small")
        digits=[]
        for i,col in enumerate(boxes):
            with col:
                digits.append(st.text_input(f"Digit {i+1}", max_chars=1, type="password", key=f"admin_digit_{i}", label_visibility="collapsed", placeholder="•"))
        st.markdown("<style>div[data-testid='stTextInput'] input{text-align:center;font-size:1.4rem;font-weight:800;min-height:52px;padding:0;border:2px solid #83b5e8;border-radius:9px}</style>", unsafe_allow_html=True)
        submit=st.form_submit_button("CONFIRM", use_container_width=True)
    if submit:
        attempt=int(st.session_state.get("admin_attempts",0))
        entered="".join(digits)
        if attempt >= 5:
            st.error("Too many failed attempts in this session. Refreshing will not clear server-side protections; contact the administrator if locked out.")
        elif len(entered)!=6 or not entered.isdigit():
            st.error("Enter all six digits.")
        elif _verify_admin_key(entered):
            st.session_state.admin_authenticated=True
            st.session_state.admin_attempts=0
            st.rerun()
        else:
            st.session_state.admin_attempts=attempt+1
            st.error("Incorrect access key.")
    return bool(st.session_state.get("admin_authenticated",False))

def render_admin(show_title=True):
    apply_app_style()
    if not st.session_state.get("admin_authenticated",False):
        if not _admin_login(): return
    if show_title: page_heading("Admin Dashboard", "Review, update and monitor public complaints.")
    top_left, top_right = st.columns([4, 1])
    with top_right:
        if st.button("Log out", key="admin_logout"):
            st.session_state.admin_authenticated=False
            for i in range(6): st.session_state.pop(f"admin_digit_{i}",None)
            st.rerun()
    with top_left:
        if st.button("Sync offline queue", key="sync_offline_queue"):
            try:
                from offline_storage import sync_pending_complaints, get_pending_complaints
                pending_before = len(get_pending_complaints())
                synced = sync_pending_complaints()
                st.success(f"Synced {synced} complaint(s). {max(0, pending_before-synced)} item(s) may still need retrying.")
                st.rerun()
            except Exception as exc:
                st.error(f"Offline queue sync failed: {exc}")
    try: df=_load_df()
    except Exception as exc: st.error(f"Could not load admin data: {exc}"); return
    if df.empty: st.info("No complaints yet."); return
    for col in ["tracking_id","description","location","category","status","created_at","latitude","longitude"]:
        if col not in df.columns: df[col]=None
    total=len(df); resolved=int((df.status=="Resolved").sum()); progress=int((df.status=="In Progress").sum()); open_count=int((~df.status.isin(["Resolved","Rejected"])).sum())
    a,b,c,d=st.columns(4)
    a.metric("Total complaints",total); b.metric("Open",open_count); c.metric("In progress",progress); d.metric("Resolved",resolved)
    st.subheader("Complaint status graph")
    counts=df.status.fillna("Unknown").value_counts().rename_axis("Status").reset_index(name="Complaints")
    st.bar_chart(counts.set_index("Status"))
    st.subheader("Category graph")
    cats=df.category.fillna("Other").value_counts().rename_axis("Category").reset_index(name="Complaints")
    st.bar_chart(cats.set_index("Category"))
    st.subheader("Complaint records")
    search=st.text_input("Search by tracking ID, text, or location", key="admin_search")
    filtered=df.copy()
    if search.strip(): filtered=filtered[filtered.apply(lambda r: search.casefold() in f"{r.get('tracking_id','')} {r.get('description','')} {r.get('location','')}".casefold(),axis=1)]
    st.dataframe(filtered[[c for c in ["tracking_id","description","category","location","status","created_at"] if c in filtered.columns]],use_container_width=True,hide_index=True)
    st.subheader("Update a complaint")
    ids=filtered.tracking_id.dropna().astype(str).tolist()
    if not ids: st.info("No matching complaints to update."); return
    with st.form("admin_update_form"):
        chosen=st.selectbox("Tracking ID",ids)
        new_status=st.selectbox("New status",STATUSES)
        note=st.text_area("Resolution / admin note (optional)", max_chars=1000)
        update=st.form_submit_button("Save status")
    if update:
        try:
            # If the optional resolution_note column is not yet in the database, retry status only.
            try: ok=update_status(chosen,new_status,note if note.strip() else None)
            except Exception as exc:
                if note.strip():
                    ok=update_status(chosen,new_status,None)
                    st.warning("Status saved. Resolution notes need the optional resolution_note column in Supabase.")
                else: raise exc
            if ok: st.success("Complaint status updated."); st.rerun()
            else: st.error("No complaint was updated. Check the tracking ID.")
        except Exception as exc: st.error(f"Could not update status: {exc}")
