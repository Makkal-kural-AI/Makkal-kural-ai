import streamlit as st

st.set_page_config(
    page_title="Makkal Kural AI",
    page_icon="📢",
    layout="wide"
)

st.title("📢 Makkal Kural AI")
st.subheader("Your Voice, Your Village.")

st.write(
    "Report local issues easily through our "
    "community complaint management system."
)

st.divider()

st.header("Submit a Complaint")

name = st.text_input("Your Name (Optional)")
location = st.text_input("Village / Location")

complaint = st.text_area(
    "Describe Your Complaint",
    placeholder="Example: Streetlights are not working..."
)

if st.button("Submit Complaint"):
    if location.strip() and complaint.strip():
        st.success("Your complaint form is completed!")
    else:
        st.warning(
            "Please enter your village and complaint."
        )

st.divider()
st.caption("Makkal Kural AI | Your voice matters 💙")
