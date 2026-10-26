# Makkal Kural AI

**Your Voice • Our Priority**

## About

Makkal Kural AI is an AI-powered complaint management system designed to help rural communities report local issues easily through text or voice. The system categorizes complaints, stores them in a database, and provides an admin dashboard to monitor and manage complaints efficiently.

## Problem Statement

Rural communities may face difficulties reporting local issues such as water leakage, blocked drainage, garbage accumulation, damaged roads, and non-working streetlights. A simple and accessible complaint reporting system can help residents communicate these issues more easily.

## Proposed Solution

Makkal Kural AI aims to provide a user-friendly system that accepts text and voice complaints, identifies complaint categories, stores complaint details, and allows administrators to monitor and manage reports.

## Key Features

- Voice-based complaint input
- Text-based complaint reporting
- Tamil and English speech recognition
- Complaint categorization
- Database storage
- Admin dashboard for complaint management

## Supabase Setup

The application stores complaints and queued submissions in Supabase. Create a Supabase project, then run [`supabase/schema.sql`](supabase/schema.sql) in the project SQL Editor.

Set these environment variables for the server running Streamlit:

```text
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
```

Keep the service role key server-side and never expose it in browser code.

## Render Deployment

The repository includes a Render Blueprint and Dockerfile. In Render, create a new Blueprint from this repository and provide `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` when prompted. Run the SQL setup above before deploying. The container installs FFmpeg for Whisper and starts the existing UI with Streamlit; the service listens on Render's assigned port.

Live app: [Makkal Kural AI](https://makkal-kural-ai.onrender.com)

Whisper downloads its model the first time voice transcription is used. Allow enough memory for the model and Torch runtime, and note that ephemeral instances may need to download the model again after a restart.

## Voice AI Module

The Voice AI module uses Python, SpeechRecognition, PyAudio, and OpenAI Whisper to capture speech and convert it into text.

### Technologies Used

- Python
- OpenAI Whisper
- SpeechRecognition
- PyAudio
- Indic Transliteration

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/Makkal-kural-AI/Makkal-kural-ai.git
   ```

2. Open the project directory:

   ```bash
   cd Makkal-kural-ai
   ```

3. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   ```

   Windows:

   ```bash
   .venv\Scripts\activate
   ```

4. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

5. Ensure FFmpeg is installed and available in your system PATH.

6. Run the voice module:

   ```bash
   python voice_ai.py
   ```

## Team

Developed by the Makkal Kural AI team for a social impact innovation project.

## Repository

[GitHub Repository](https://github.com/Makkal-kural-AI/Makkal-kural-ai)
