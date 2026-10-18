import os

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import time
import speech_recognition as sr
import whisper
import pygame
from gtts import gTTS


def speak_confirmation(text, lang="ta"):
    filename = "confirmation.mp3"

    try:
        tts = gTTS(text=text, lang=lang)
        tts.save(filename)

        pygame.mixer.init()
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

    except Exception:
        pass

    finally:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            pygame.mixer.quit()

        if os.path.exists(filename):
            try:
                os.remove(filename)
            except OSError:
                pass


def capture_and_process_complaint(model):
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 2.5
    audio_filename = "complaint.wav"

    print("Speak now / இப்போது பேசுங்கள்")

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(
                source, duration=1
            )
            audio = recognizer.listen(
                source,
                timeout=12,
                phrase_time_limit=45
            )

        with open(audio_filename, "wb") as file:
            file.write(audio.get_wav_data())

        result = model.transcribe(
            audio_filename,
            task="transcribe",
            fp16=False,
            temperature=0,
            condition_on_previous_text=False
        )

        complaint_text = result["text"].strip()
        language = result.get("language", "unknown")

        if language not in ("ta", "en") or len(complaint_text) < 3:
            return None, None

        if language == "ta":
            translated = model.transcribe(
                audio_filename,
                task="translate",
                fp16=False,
                temperature=0
            )
            english_text = translated["text"].strip()
        else:
            english_text = complaint_text
        print("-----------------------------------------------")
        print("\nYour Complaint / உங்கள் புகார்:")
        print(complaint_text)
        print("-----------------------------------------------")


        if language == "ta":
            speak_confirmation(
                "உங்கள் புகார் பதிவு செய்யப்பட்டது",
                lang="ta"
            )
        else:
            speak_confirmation(
                "Your complaint has been registered",
                lang="en"
            )

        return english_text, language

    except (sr.WaitTimeoutError, sr.UnknownValueError):
        return None, None

    except Exception:
        return None, None

    finally:
        if os.path.exists(audio_filename):
            try:
                os.remove(audio_filename)
            except OSError:
                pass


if __name__ == "__main__":
    model = whisper.load_model("small")
    capture_and_process_complaint(model)
