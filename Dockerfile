# Backend image for Railway (railway.json -> builder DOCKERFILE). Two stages:
#   build   — installs the Python packages into /opt/venv and downloads the
#             MiniLM model into /opt/models
#   runtime — python:3.11-slim plus those two folders and the backend code
#             (no pip cache, no build leftovers)

# ── build ─────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/models/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/opt/models/sentence_transformers

RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

# CPU-only torch FIRST: the default PyPI torch on Linux pulls ~2.4 GB of CUDA
# libraries this CPU-only service never uses (torch 2.14.1: ~2,990 MB download
# vs ~207 MB for the +cpu build). sentence-transformers then finds torch already
# installed and keeps it.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY backend/requirements.txt .
# whisper is OPTIONAL (offline transcription CLI only) — installing it here pulls in
# ffmpeg + a heavy legacy build that OOMs/times out Railway's builder. Left out of the
# deployed image on purpose; install it locally if you need rag/transcribe.py.
RUN pip install -r requirements.txt

# Bake the embedding model into the image, so a new container never downloads it
# (~35 s on first use before). rag/embedder.py loads it from the same folder.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# ── runtime ───────────────────────────────────────────────────────────────────
FROM python:3.11-slim

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/opt/models/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/opt/models/sentence_transformers \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TORCH_HOME=/tmp/torch

COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/models /opt/models

WORKDIR /app
COPY backend/ .

# Railway routes public traffic to the domain's Target Port (set to 8000 in the
# dashboard). Bind uvicorn to $PORT if Railway injects it, else fall back to 8000
# so the app always listens on the port Railway forwards to. Shell form so ${PORT}
# expands. One worker: the scheduler and caches are per process (see DEPLOYMENT.md
# before raising --workers).
EXPOSE 8000
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
