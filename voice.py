
import os
import speech_recognition as sr
import whisper

_model = None


def get_voice_complaint():
    global _model

    audio_filename = "complaint.wav"

    try:
        # Load Whisper model only once
        if _model is None:
            print("Loading Whisper base model...")
            _model = whisper.load_model("base")

        recognizer = sr.Recognizer()
        recognizer.pause_threshold = 2.0

        print("Speak now...")

        # Record voice from microphone
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(
                source, duration=1
            )
            audio = recognizer.listen(
                source,
                timeout=10,
                phrase_time_limit=45
            )

        # Save recorded audio temporarily
        with open(audio_filename, "wb") as file:
            file.write(audio.get_wav_data())

        # Convert speech to text
        result = _model.transcribe(
            audio_filename,
            task="transcribe",
            fp16=False,
            temperature=0
        )

        complaint_text = result["text"].strip()
        language = result.get("language", "unknown")

        if len(complaint_text) < 3:
            print("No clear speech detected.")
            return None

        # Translate Tamil speech into English
        if language == "ta":
            translated = _model.transcribe(
                audio_filename,
                task="translate",
                fp16=False,
                temperature=0
            )
            return translated["text"].strip()

        # Return English speech directly
        if language == "en":
            return complaint_text

        print("Unsupported language:", language)
        return None

    except sr.WaitTimeoutError:
        print("No speech detected before timeout.")
        return None

    except sr.UnknownValueError:
        print("Speech could not be understood.")
        return None

    except Exception as error:
        print("Voice error:", repr(error))
        return None

    finally:
        # Remove temporary audio file
        if os.path.exists(audio_filename):
            try:
                os.remove(audio_filename)
            except OSError:
                pass
