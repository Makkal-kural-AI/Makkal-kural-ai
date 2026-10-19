
import speech_recognition as sr

try:
    recognizer = sr.Recognizer()

    with sr.Microphone() as source:
        print("Adjusting microphone...")
        recognizer.adjust_for_ambient_noise(source, duration=1)

        print("Speak a full sentence now...")
        audio = recognizer.listen(
            source,
            timeout=10,
            phrase_time_limit=15
        )

    with open("test_audio.wav", "wb") as file:
        file.write(audio.get_wav_data())

    print("Recording saved as test_audio.wav")

except Exception as error:
    print("Recording failed:", repr(error))
