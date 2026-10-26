"""Makkal Kural AI: Tamil/English Whisper transcription.

Browser recordings are handled by transcribe_audio_bytes().
Local microphone testing is available through get_voice_complaint().
No success message is spoken until the dashboard confirms database saving.
"""
import os
import tempfile
from functools import lru_cache


@lru_cache(maxsize=1)
def _get_model():
    import whisper
    # Set WHISPER_MODEL=small if accuracy requires it and hosting has enough RAM.
    return whisper.load_model(os.getenv("WHISPER_MODEL", "base"))


def _transcribe_file(filename):
    model = _get_model()
    result = model.transcribe(
        filename,
        task="transcribe",
        fp16=False,
        temperature=0,
        condition_on_previous_text=False,
    )
    original = str(result.get("text", "")).strip()
    language = result.get("language", "unknown")
    if language not in ("ta", "en") or len(original) < 3:
        return None
    if language == "ta":
        translated = model.transcribe(
            filename,
            task="translate",
            fp16=False,
            temperature=0,
            condition_on_previous_text=False,
        )
        return str(translated.get("text", "")).strip() or original
    return original


def transcribe_audio_bytes(audio_bytes):
    """Return English complaint text from a browser WAV recording, or None."""
    if not audio_bytes:
        return None
    filename = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
            audio_file.write(audio_bytes)
            filename = audio_file.name
        return _transcribe_file(filename)
    finally:
        if filename and os.path.exists(filename):
            os.remove(filename)


def get_voice_complaint():
    """Local-only microphone test; do not use on Render for website visitors."""
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 2.5
    print("Speak now / இப்போது பேசுங்கள்")
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)
        try:
            audio = recognizer.listen(source, timeout=12, phrase_time_limit=45)
        except sr.WaitTimeoutError:
            print("No speech detected.")
            return None
    text = transcribe_audio_bytes(audio.get_wav_data())
    if text:
        print("Your Complaint / உங்கள் புகார்:")
        print(text)
    return text


if __name__ == "__main__":
    print(get_voice_complaint() or "No complaint recognized.")
