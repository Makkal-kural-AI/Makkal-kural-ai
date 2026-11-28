"""HTTP API for the Makkal Kural ESP32 voice device.

The Streamlit app cannot receive raw POST requests, so this small Flask
service sits next to it and talks to the same Supabase table.

Flow:  ESP32 --(WAV, POST /upload_audio)--> Whisper -> classifier -> Supabase
       ESP32 <--(16 kHz mono 16-bit PCM spoken confirmation)-- this service

Environment variables
---------------------
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   same values as the Streamlit service
DEVICE_TOKEN                              shared secret; ESP32 sends it as X-Device-Token
WHISPER_MODEL                             tiny (default) / base / small
"""

import io
import logging
import math
import os
import secrets
import subprocess
import threading
import wave
from array import array
from datetime import datetime, timezone

from flask import Flask, Response, request

from classifier import classify_complaint
from voice_ai import _get_model, process_complaint_audio

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("device_api")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB is plenty for a few seconds

DEVICE_TOKEN = os.getenv("DEVICE_TOKEN", "").strip()
TABLE_NAME = os.getenv("SUPABASE_TABLE", "complaints")
MIN_RMS = 150  # below this the recording is treated as silence (int16 scale)

_client = None


def get_client():
    global _client
    if _client is None:
        from supabase import create_client

        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"],
        )
    return _client


def fail(status, message):
    """Short ASCII message in X-Message so the ESP32 can show it on the OLED."""
    log.warning("reply %s: %s", status, message)
    return Response(message, status=status, headers={"X-Message": message})


def tts_pcm(text, lang):
    """Spoken text -> raw 16 kHz mono signed 16-bit little-endian PCM."""
    from gtts import gTTS

    mp3 = io.BytesIO()
    gTTS(text=text, lang=lang).write_to_fp(mp3)
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", "pipe:0",
         "-f", "s16le", "-ar", "16000", "-ac", "1", "pipe:1"],
        input=mp3.getvalue(), capture_output=True, check=True, timeout=30,
    )
    return proc.stdout


def confirmation_text(tracking_id, language):
    digits = " ".join(tracking_id.split("-")[-1])
    if language == "ta":
        return (f"உங்கள் புகார் பதிவு செய்யப்பட்டது. "
                f"உங்கள் புகார் எண் {digits}"), "ta"
    return (f"Your complaint has been registered. "
            f"Your tracking number is {digits}."), "en"


def save_complaint(category, text, location):
    """Insert with a fresh tracking id (retry on the rare collision)."""
    for _ in range(3):
        tracking_id = f"MKAI-{secrets.randbelow(900000) + 100000}"
        try:
            get_client().table(TABLE_NAME).insert({
                "tracking_id": tracking_id,
                "category": category,
                "description": text,
                "complaint_text": text,
                "location": location or "Not provided",
                "status": "Submitted",
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }).execute()
            return tracking_id
        except Exception as exc:  # noqa: BLE001
            log.error("insert failed: %s", exc)
            if "duplicate" not in str(exc).lower():
                break
    return None


@app.get("/health")
def health():
    return "ok"


@app.post("/upload_audio")
def upload_audio():
    if DEVICE_TOKEN and request.headers.get("X-Device-Token") != DEVICE_TOKEN:
        return fail(401, "Bad device token")

    body = request.get_data(cache=False)
    try:
        with wave.open(io.BytesIO(body)) as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1:
                return fail(400, "Need 16-bit mono WAV")
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError):
        return fail(400, "Invalid WAV data")

    samples = array("h")
    samples.frombytes(frames[: len(frames) // 2 * 2])
    if not samples:
        return fail(400, "Empty audio")
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    log.info("received %d samples, rms=%.0f", len(samples), rms)
    if rms < MIN_RMS:
        return fail(422, "Heard nothing")

    result = process_complaint_audio(body)
    if not result:
        return fail(422, "Could not understand")

    category = classify_complaint(result["english"])
    location = request.headers.get("X-Location", "")
    tracking_id = save_complaint(category, result["english"], location)
    if not tracking_id:
        return fail(500, "Database error")
    log.info("saved %s [%s] %r", tracking_id, category, result["english"])

    try:
        text, lang = confirmation_text(tracking_id, result["language"])
        pcm = tts_pcm(text, lang)
    except Exception as exc:  # noqa: BLE001 - complaint is saved, audio is a bonus
        log.error("tts failed: %s", exc)
        pcm = b""

    return Response(
        pcm,
        mimetype="audio/L16",
        headers={"X-Tracking-Id": tracking_id, "X-Category": category},
    )


# Load Whisper in the background so the first real request is not slow.
threading.Thread(target=_get_model, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
