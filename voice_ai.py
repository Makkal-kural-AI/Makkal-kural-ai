import speech_recognition as sr
import whisper
import os
os.environ["PATH"] += os.pathsep + r"C:\Users\egyan\AppData\Local\Microsoft\WinGet\Packages"

def capture_and_press_complaint(model):
    recognizer = sr.Recognizer()
    
    # 2.5-second pause threshold for natural pauses
    recognizer.pause_threshold = 2.5
    recognizer.dynamic_energy_threshold = True

    print("\nSpeak now / இப்போது பேசுங்கள்...")

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
            audio = recognizer.listen(
                source,
                timeout=12,
                phrase_time_limit=45
            )

        # Save audio file temporarily for Whisper processing
        audio_filename = "complaint.wav"
        with open(audio_filename, "wb") as file:
            file.write(audio.get_wav_data())

        # Transcribe with hallucination suppression
        result = model.transcribe(
            audio_filename,
            task="transcribe",
            fp16=False,
            temperature=0,
            no_speech_threshold=0.6,
            condition_on_previous_text=False,
            initial_prompt=(
                "கிராமத்து மற்றும் பழங்குடி மக்களின் தமிழ் புகார்கள். "
                "ரோடு குழி குழியா இருக்கு, ரோடு சரியில்ல, ரோடு போதக்குழி இருக்கு, "
                "தண்ணி வரல, குடிநீர் வராம இருக்கு, குழாய் உடைஞ்சு போச்சு, "
                "சாக்கடை அடைச்சுக்குச்சு, தன்னி தேங்கி நிக்குது, "
                "குப்பை அள்ளல, தெருவிளக்கு எரியல, கரண்ட் இல்ல. "
                "Road-ula pothakuli irukku, kunnu kuliyuma irukku road."
            )
        )

        complaint_text = result["text"].strip()
        detected_language = result.get("language", "unknown")

        # Reject hallucinated non-target languages (like Sinhala, Malayalam, etc.)
        if detected_language not in ["ta", "en"]:
            print("\n[Error] Unclear audio detected. Please speak your complaint clearly.")
            return None, None

        # Filter repetitive hallucinated characters
        if len(complaint_text) > 10 and len(set(complaint_text)) < 5:
            print("\n[Error] Unclear audio detected. Please try again.")
            return None, None

        if not complaint_text or len(complaint_text) < 3:
            print("\n[Error] Could not understand clearly. Please try again.")
            return None, None

        # Clean output matching language
        print("\n---------------------------------------------")
        if detected_language == "ta":
            print("உங்கள் புகார்:")
        elif detected_language == "en":
            print("Your complaint:")
        else:
            print("Your complaint / உங்கள் புகார்:")

        print(f'"{complaint_text}"')
        print("---------------------------------------------\n")

        return complaint_text, detected_language

    except sr.WaitTimeoutError:
        print("\n[Error] No speech detected. Please try again.")
        return None, None

    except Exception as error:
        print(f"\n[Error] An error occurred: {error}")
        return None, None

if __name__ == "__main__":
    # Silently load the model
    model = whisper.load_model("small")
    
    # Run voice capture
    capture_and_press_complaint(model)