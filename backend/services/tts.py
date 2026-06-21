"""
Text-to-Speech using Kokoro TTS.
"""
import io
import soundfile as sf
import numpy as np
from typing import Optional

from config.settings import get_settings

settings = get_settings()

_pipeline = None


def get_tts_pipeline():
    global _pipeline
    if _pipeline is None:
        from kokoro import KPipeline
        _pipeline = KPipeline(lang_code="a")  # 'a' = American English
    return _pipeline


async def synthesize_speech(text: str, voice: Optional[str] = None) -> bytes:
    """
    Convert text to speech. Returns WAV bytes.
    """
    pipeline = get_tts_pipeline()
    voice_id = voice or settings.kokoro_voice

    audio_chunks = []
    generator = pipeline(
        text,
        voice=voice_id,
        speed=settings.kokoro_speed,
        split_pattern=r"\n+",
    )

    for _, _, audio in generator:
        if audio is not None:
            audio_chunks.append(audio)

    if not audio_chunks:
        return b""

    combined = np.concatenate(audio_chunks)

    buf = io.BytesIO()
    sf.write(buf, combined, samplerate=24000, format="WAV")
    buf.seek(0)
    return buf.read()


async def synthesize_to_file(text: str, output_path: str, voice: Optional[str] = None) -> str:
    """Synthesize and save to a file. Returns the output path."""
    wav_bytes = await synthesize_speech(text, voice)
    with open(output_path, "wb") as f:
        f.write(wav_bytes)
    return output_path
