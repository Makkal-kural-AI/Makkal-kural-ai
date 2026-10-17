import speech_recognition as sr
import whisper

def initialize_voice_engine(model_size="small"):
    """Loads the Whisper model silently without extra console prints."""
    return whisper.load_model(model_size)

def capture_complaint(model):
    recognizer = sr.Recognizer()
    
    # Pause threshold: allows a 2.5-second break mid-speech without cutting off
    recognizer.pause_threshold = 2.5
    recognizer.dynamic_energy_threshold = True

    print("\nSpeak now / இப்போது பேசுங்கள்...")

    try:
        with sr.Microphone() as source:
            # Calibrate ambient noise quietly
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

        # Transcribe audio with anti-hallucination & vocabulary context
        result = model.transcribe(
            audio_filename,
            task="transcribe",
            fp16=False,
            temperature=0,
            no_speech_threshold=0.6,
            condition_on_previous_text=False,
            initial_prompt=(
                "Civic public complaints in Tamil, English, and Tanglish: "
                "street light, drainage problem, water leakage, garbage collection, "
                "தெருவிளக்கு எரியவில்லை, சாக்கடை அடைப்பு, தண்ணீர் கசிவு, குப்பை அல்லவில்லை, "
                "enga street la street light eriyala, water leak aaguthu."
            )
        )

        complaint_text = result["text"].strip()
        detected_language = result.get("language", "unknown")

        # Reject noise or invalid short inputs
        if not complaint_text or len(complaint_text) < 3:
            print("\n[Error] Could not understand clearly. Please try again.")
            return None, None

        # Display result dynamically based on detected language
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
    # Load Whisper silently
    model = initialize_voice_engine("small")
    
    # Run complaint audio capture
    capture_complaint(model)