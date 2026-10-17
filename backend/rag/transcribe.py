"""Lecture transcription — openai-whisper (local, free) -> timestamped .txt -> RAG_SERVER.

Transcribes a recorded video/audio lecture and uploads the transcript as study
material (material_type "lecture") through the same path as the teacher upload
page: original .txt in Supabase Storage + a study_materials row + RAG_SERVER
indexing. Doubts can then cite what the teacher actually said in class, and the
lecture can be re-indexed from the Study Material page like any other file.

Whisper is imported lazily and cached, so the rest of the backend boots even if
whisper isn't installed (it has a heavy/fragile build — see Dockerfile).

CLI:
    python -m rag.transcribe --media data/lectures/rotational_motion.mp4 \
        --subject Physics --chapter "Rotational Motion" --institute-id <institute uuid>
"""

import os
import argparse
import asyncio
from functools import lru_cache
from pathlib import Path

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


def _stamp(seconds: float) -> str:
    s = int(seconds or 0)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def transcribe_media(media_path: str, language: str = None) -> str:
    """Transcribe an audio/video file (ffmpeg must be on PATH).

    Returns one "[hh:mm:ss] text" line per segment, so a cited chunk tells the
    student where in the lecture to look.
    """
    model = _get_model()
    result = model.transcribe(media_path, language=language, fp16=False)
    lines = [f"[{_stamp(seg.get('start'))}] {seg.get('text', '').strip()}"
             for seg in result.get("segments") or [] if seg.get("text", "").strip()]
    return "\n".join(lines) or (result.get("text") or "").strip()


def transcribe_and_upload(
    media_path: str,
    subject: str = None,
    chapter: str = None,
    institute_id: str = None,
    language: str = None,
    class_level: str = None,
    exam: str = None,
    uploaded_by: str = None,
) -> dict:
    """Transcribe a lecture and upload it as study material. Returns the study_materials row."""
    from rag.study_materials import create_material, CLI_UPLOADER

    text = transcribe_media(media_path, language=language)
    if not text:
        print(f"[transcribe] no text produced for {media_path}")
        return {}

    title = f"{subject + ' — ' if subject else ''}{chapter or Path(media_path).stem} (lecture transcript)"
    content = f"{title}\nSource recording: {Path(media_path).name}\n\n{text}\n".encode("utf-8")
    row = asyncio.run(create_material(
        content, f"{Path(media_path).stem}.txt", institute_id=institute_id,
        uploaded_by=uploaded_by or CLI_UPLOADER, subject=subject, chapter=chapter,
        class_level=class_level, exam=exam, material_type="lecture"))
    print(f"[transcribe] uploaded {row.get('filename')} -> status {row.get('status')}"
          + (f" ({row.get('message')})" if row.get("message") else ""))
    return row


def main():
    from dotenv import load_dotenv
    from rag.study_materials import MaterialError
    load_dotenv()

    parser = argparse.ArgumentParser(description="Transcribe a lecture and upload it to RAG_SERVER")
    parser.add_argument("--media", required=True)
    parser.add_argument("--subject", default=None)
    parser.add_argument("--chapter", default=None)
    parser.add_argument("--institute-id", default=None,
                        help="institute uuid (omit for the env-default RAG tenant)")
    parser.add_argument("--class-level", default=None)
    parser.add_argument("--exam", default=None, help="JEE | NEET | Boards | Other")
    parser.add_argument("--uploaded-by", default=None, help="auth user id to record as uploader")
    parser.add_argument("--language", default=None, help="e.g. 'hi' for Hindi")
    args = parser.parse_args()

    import uuid
    for name in ("institute_id", "uploaded_by"):
        value = getattr(args, name)
        try:
            if value:
                uuid.UUID(value)
        except ValueError:
            raise SystemExit(f"[transcribe] --{name.replace('_', '-')} must be a UUID, got {value!r}")

    try:
        transcribe_and_upload(
            media_path=args.media,
            subject=args.subject,
            chapter=args.chapter,
            institute_id=args.institute_id,
            language=args.language,
            class_level=args.class_level,
            exam=args.exam,
            uploaded_by=args.uploaded_by,
        )
    except MaterialError as e:
        raise SystemExit(f"[transcribe] {e.detail}")


if __name__ == "__main__":
    main()
