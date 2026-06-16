"""Lecture transcription — openai-whisper (local, free) -> chunks -> Qdrant.

Transcribes recorded video/audio lectures to text and indexes them into the RAG
store so the doubt agent can answer from what the teacher actually said in class.

Whisper is imported lazily and cached, so the rest of the backend boots even if
whisper isn't installed (it has a heavy/fragile build — see Dockerfile).

CLI:
    python -m rag.transcribe --media data/lectures/rotational_motion.mp4 \
        --subject Physics --chapter "Rotational Motion" --institute-id abc-123
"""

import os
import argparse
from functools import lru_cache

MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")  # tiny|base|small|medium|large


@lru_cache(maxsize=1)
def _get_model():
    """Load the whisper model once. Raises a clear error if whisper is missing."""
    try:
        import whisper
    except ImportError as e:
        raise RuntimeError(
            "openai-whisper is not installed. Install it with "
            '`pip install "setuptools<81" wheel` then '
            "`pip install --no-build-isolation openai-whisper==20231117`."
        ) from e
    return whisper.load_model(MODEL_SIZE)


def transcribe_media(media_path: str, language: str = None) -> str:
    """Transcribe an audio/video file to plain text (ffmpeg must be on PATH)."""
    model = _get_model()
    result = model.transcribe(media_path, language=language, fp16=False)
    return (result.get("text") or "").strip()


def transcribe_and_index(
    media_path: str,
    subject: str = None,
    chapter: str = None,
    institute_id: str = None,
    language: str = None,
) -> int:
    """Transcribe a lecture and upsert its chunks into Qdrant.

    Institute lectures -> rag_{institute_id}; otherwise -> rag_shared.
    Returns the number of chunks indexed.
    """
    from rag.ingest import chunk_text, _collection_exists
    from rag.qdrant_client import (
        upsert_chunks, create_shared_collection, create_institute_collection,
    )

    text = transcribe_media(media_path, language=language)
    if not text:
        print(f"[transcribe] no text produced for {media_path}")
        return 0

    collection = f"rag_{institute_id}" if institute_id else "rag_shared"
    if not _collection_exists(collection):
        if institute_id:
            create_institute_collection(institute_id)
        else:
            create_shared_collection()

    chunks = [{
        "content": piece,
        "source": "video_transcript",
        "subject": subject,
        "chapter": chapter,
        "level": 1,
    } for piece in chunk_text(text)]

    count = upsert_chunks(chunks, collection)
    print(f"[transcribe] indexed {count} chunks from {media_path} -> {collection}")
    return count


def main():
    parser = argparse.ArgumentParser(description="Transcribe a lecture into Qdrant RAG")
    parser.add_argument("--media", required=True)
    parser.add_argument("--subject", default=None)
    parser.add_argument("--chapter", default=None)
    parser.add_argument("--institute-id", default=None)
    parser.add_argument("--language", default=None, help="e.g. 'hi' for Hindi")
    args = parser.parse_args()

    transcribe_and_index(
        media_path=args.media,
        subject=args.subject,
        chapter=args.chapter,
        institute_id=args.institute_id,
        language=args.language,
    )


if __name__ == "__main__":
    main()
