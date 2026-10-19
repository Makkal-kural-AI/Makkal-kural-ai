
import whisper

print("Loading Whisper model...")
model = whisper.load_model("base")
print("Model loaded successfully!")

result = model.transcribe(
    "complaint.wav",
    fp16=False
)

print("Recognized text:", result["text"])
