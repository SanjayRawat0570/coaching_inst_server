FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
# whisper is OPTIONAL (offline transcription CLI only) — installing it here pulls in
# ffmpeg + a heavy legacy build that OOMs/times out the image build. Left out of the
# deployed image on purpose; install it locally if you need rag/transcribe.py.
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# CRITICAL — HuggingFace Spaces REQUIRES /tmp for all model caches
# App will fail to start without these four lines
ENV TRANSFORMERS_CACHE=/tmp/transformers
ENV HF_HOME=/tmp/huggingface
ENV SENTENCE_TRANSFORMERS_HOME=/tmp/sentence_transformers
ENV TORCH_HOME=/tmp/torch

# Hosted free on Hugging Face Spaces (Docker SDK). The Space forwards traffic to
# app_port, set to 8000 in the root README.md front matter. $PORT is honoured if a
# host injects one. Shell form so ${PORT} expands.
EXPOSE 8000
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
