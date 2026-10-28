"""Tamil/English speech processing using Whisper. Audio bytes are supplied by Streamlit."""
import io, os, tempfile
from functools import lru_cache

@lru_cache(maxsize=1)
def _get_model():
    import whisper
    return whisper.load_model(os.getenv("WHISPER_MODEL", "base"))

def process_complaint_audio(audio_bytes):
    """Return original transcript, English translation, and detected language.

    Whisper's translate task produces English. We preserve the original transcript so
    Tamil complaints are not accidentally replaced with English before submission.
    """
    if not audio_bytes:
        return None
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            path = tmp.name
        model = _get_model()
        result = model.transcribe(path, task="transcribe", fp16=False, temperature=0, condition_on_previous_text=False)
        original = str(result.get("text") or "").strip()
        language = str(result.get("language") or "unknown").lower()
        if not original:
            return None
        english = original
        if language == "ta":
            translated = model.transcribe(path, task="translate", fp16=False, temperature=0, condition_on_previous_text=False)
            english = str(translated.get("text") or "").strip()
        return {"original": original, "english": english or original, "language": language}
    finally:
        if path and os.path.exists(path):
            os.remove(path)

def transcribe_audio_bytes(audio_bytes):
    result = process_complaint_audio(audio_bytes)
    return result["original"] if result else None

def confirmation_audio(language="en"):
    from gtts import gTTS
    tamil = str(language).lower().startswith("ta")
    message = "உங்கள் புகார் பதிவு செய்யப்பட்டது" if tamil else "Your complaint has been registered"
    output = io.BytesIO()
    gTTS(text=message, lang="ta" if tamil else "en").write_to_fp(output)
    return output.getvalue()
