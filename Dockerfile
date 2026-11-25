FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        portaudio19-dev \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# CPU-only PyTorch (much smaller and lighter than the default CUDA build).
# openai-whisper in requirements.txt then reuses it instead of downloading GPU libraries.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Pre-download the free multilingual Whisper "tiny" model at build time so the
# first voice request does not have to download it. No API key is involved.
ARG WHISPER_MODEL=tiny
RUN python -c "import whisper; whisper.load_model('${WHISPER_MODEL}', device='cpu')"

COPY . .

EXPOSE 8501

CMD ["sh", "-c", "streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0"]
