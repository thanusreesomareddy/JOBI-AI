import uuid
from pathlib import Path

import httpx

from app.config import settings

ALLOWED_EXTENSIONS = {".webm", ".wav", ".mp3", ".m4a", ".mp4", ".mpeg", ".mpga"}
CONTENT_TYPES = {
    ".webm": "audio/webm",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
}


def transcribe_audio(file_path: Path) -> str:
    if not settings.stt_configured:
        if settings.stt_provider == "deepgram":
            raise RuntimeError("STT is not configured. Set DEEPGRAM_API_KEY in .env")
        raise RuntimeError("STT is not configured. Set OPENAI_API_KEY in .env")

    if settings.stt_provider == "deepgram":
        return _transcribe_deepgram(file_path)
    return _transcribe_openai(file_path)


def _transcribe_deepgram(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    content_type = CONTENT_TYPES.get(suffix, "audio/webm")
    audio_bytes = file_path.read_bytes()

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                "https://api.deepgram.com/v1/listen",
                params={"model": "nova-2", "language": "en", "smart_format": "true"},
                headers={
                    "Authorization": f"Token {settings.deepgram_api_key}",
                    "Content-Type": content_type,
                },
                content=audio_bytes,
            )
    except httpx.HTTPError as e:
        raise RuntimeError(f"Could not reach Deepgram: {e}") from e

    if response.status_code == 401:
        raise RuntimeError("Invalid DEEPGRAM_API_KEY. Check your .env file.")
    if response.status_code == 402:
        raise RuntimeError(
            "Deepgram credits exhausted. Add credits at console.deepgram.com — "
            "or use browser voice (Chrome/Edge, no key) or Type mode."
        )
    if response.status_code >= 400:
        detail = response.text[:300]
        raise RuntimeError(f"Deepgram error ({response.status_code}): {detail}")

    data = response.json()
    try:
        text = data["results"]["channels"][0]["alternatives"][0]["transcript"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError("Could not parse Deepgram response.") from e

    text = (text or "").strip()
    if not text:
        raise ValueError("Could not understand the audio. Try speaking louder or recording again.")
    return text


def _transcribe_openai(file_path: Path) -> str:
    from openai import APIError, AuthenticationError, OpenAI, RateLimitError

    client = OpenAI(api_key=settings.openai_api_key)
    suffix = file_path.suffix.lower()
    content_type = CONTENT_TYPES.get(suffix, "audio/webm")

    try:
        with file_path.open("rb") as audio_file:
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=(file_path.name, audio_file, content_type),
                language="en",
            )
    except RateLimitError as e:
        raise RuntimeError(
            "OpenAI quota exceeded. Add billing at platform.openai.com — "
            "or set STT_PROVIDER=deepgram in .env."
        ) from e
    except AuthenticationError as e:
        raise RuntimeError("Invalid OPENAI_API_KEY. Check your .env file.") from e
    except APIError as e:
        raise RuntimeError(f"Speech-to-text failed: {e.message}") from e

    text = (result.text or "").strip()
    if not text:
        raise ValueError("Could not understand the audio. Try speaking louder or recording again.")
    return text


def save_uploaded_audio(content: bytes, filename: str | None) -> Path:
    suffix = Path(filename or "recording.webm").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        suffix = ".webm"
    dest = settings.upload_dir / f"audio_{uuid.uuid4()}{suffix}"
    dest.write_bytes(content)
    return dest
