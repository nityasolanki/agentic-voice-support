"""
Speech-to-Text using Faster-Whisper.
"""
import io
import tempfile
from pathlib import Path
from typing import Optional

from config.settings import get_settings

settings = get_settings()

_model = None


def get_whisper_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(
            settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    return _model


async def transcribe_audio(audio_bytes: bytes, language: str = "en") -> str:
    """
    Transcribe raw audio bytes to text.
    Supports WAV, MP3, OGG, FLAC, etc.
    """
    model = get_whisper_model()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        segments, info = model.transcribe(
            tmp_path,
            language=language,
            beam_size=5,
            vad_filter=True,
        )
        transcript = " ".join(segment.text.strip() for segment in segments)
        return transcript.strip()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def transcribe_file(file_path: str | Path) -> str:
    """Transcribe an audio file from disk."""
    model = get_whisper_model()
    segments, _ = model.transcribe(str(file_path), beam_size=5, vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()
