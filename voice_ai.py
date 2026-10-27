"""Makkal Kural AI browser voice processing and confirmation."""
import io
import os
import tempfile
from functools import lru_cache

@lru_cache(maxsize=1)
def _get_model():
    import whisper
    return whisper.load_model(os.getenv('WHISPER_MODEL', 'base'))

def process_complaint_audio(audio_bytes):
    """Return {'original', 'english', 'language'} or None."""
    if not audio_bytes:
        return None
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(audio_bytes)
            path = f.name
        model = _get_model()
        result = model.transcribe(path, task='transcribe', fp16=False,
                                  temperature=0, condition_on_previous_text=False)
        original = str(result.get('text') or '').strip()
        language = result.get('language', 'unknown')
        if not original or language not in ('ta', 'en'):
            return None
        if language == 'ta':
            translation = model.transcribe(path, task='translate', fp16=False,
                                           temperature=0, condition_on_previous_text=False)
            english = str(translation.get('text') or '').strip()
        else:
            english = original
        if not english:
            return None
        return {'original': original, 'english': english, 'language': language}
    finally:
        if path and os.path.exists(path):
            os.remove(path)

def transcribe_audio_bytes(audio_bytes):
    result = process_complaint_audio(audio_bytes)
    return result['english'] if result else None

def confirmation_audio(language='en'):
    """Generate MP3 only after the database confirms saving."""
    from gtts import gTTS
    tamil = language == 'ta'
    message = ('உங்கள் புகார் பதிவு செய்யப்பட்டது' if tamil
               else 'Your complaint has been registered')
    output = io.BytesIO()
    gTTS(text=message, lang='ta' if tamil else 'en').write_to_fp(output)
    return output.getvalue()
