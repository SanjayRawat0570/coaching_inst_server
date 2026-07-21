FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
# whisper is OPTIONAL (offline transcription CLI only) — installing it here pulls in
# ffmpeg + a heavy legacy build that OOMs/times out Railway's builder. Left out of the
# deployed image on purpose; install it locally if you need rag/transcribe.py.
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# CRITICAL — HuggingFace Spaces REQUIRES /tmp for all model caches
# App will fail to start without these four lines
ENV TRANSFORMERS_CACHE=/tmp/transformers
ENV HF_HOME=/tmp/huggingface
ENV SENTENCE_TRANSFORMERS_HOME=/tmp/sentence_transformers
ENV TORCH_HOME=/tmp/torch

# Railway routes public traffic to the domain's Target Port (set to 8000 in the
# dashboard). Bind uvicorn to $PORT if Railway injects it, else fall back to 8000
# so the app always listens on the port Railway forwards to. Shell form so ${PORT}
# expands. (7860 was the old HuggingFace Spaces port — do NOT use it on Railway.)
EXPOSE 8000
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
