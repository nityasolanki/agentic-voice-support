"""
Audio file caching for Cartesia TTS playback over Twilio.

Twilio's <Play> tag needs a publicly fetchable URL — we generate
Cartesia audio, save it as a file, and serve it via FastAPI static files.
Twilio fetches the URL and plays the real Cartesia voice instead of Polly.
"""
from __future__ import annotations
import hashlib
import os
import time
import threading

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config.settings import get_settings
from backend.agents.speech import synthesize_speech

settings = get_settings()

AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Keep files for cleanup tracking
_file_registry: dict[str, float] = {}
_lock = threading.Lock()

# Twilio needs mono 8kHz mulaw or standard formats — use mp3/wav, Twilio handles conversion
OUTPUT_FORMAT_FOR_TWILIO = {
    "container": "wav",
    "encoding": "pcm_f32le",
    "sample_rate": 8000,  # Lower rate, faster generation, Twilio-friendly
}


def _audio_filename(text: str, emotion: str | None = None) -> str:
    """Generate a deterministic filename from text content."""
    key = f"{text}:{emotion or 'auto'}"
    hash_id = hashlib.md5(key.encode()).hexdigest()[:16]
    return f"{hash_id}.wav"


def generate_and_cache_audio(text: str, emotion_override: str | None = None) -> str:
    """
    Generate Cartesia audio for the given text and save to disk.
    Returns the filename (not full path) to be served via static route.
    """
    filename = _audio_filename(text, emotion_override)
    filepath = os.path.join(AUDIO_DIR, filename)

    # Return cached version if it already exists
    if os.path.exists(filepath):
        with _lock:
            _file_registry[filename] = time.time()
        return filename

    # Generate fresh audio via Cartesia
    audio_bytes = synthesize_speech(text, emotion_override=emotion_override)

    if not audio_bytes:
        print(f"[AUDIO_CACHE] Cartesia returned no audio for: {text[:50]}")
        return ""

    with open(filepath, "wb") as f:
        f.write(audio_bytes)

    with _lock:
        _file_registry[filename] = time.time()

    print(f"[AUDIO_CACHE] Generated {filename} ({len(audio_bytes)} bytes)")
    return filename


def get_audio_url(text: str, emotion_override: str | None = None) -> str:
    """
    Generate audio and return the full public URL for Twilio <Play>.
    """
    filename = generate_and_cache_audio(text, emotion_override)
    if not filename:
        return ""
    base_url = settings.twilio_webhook_base_url.rstrip("/")
    return f"{base_url}/audio/{filename}"


def cleanup_old_files(max_age_seconds: int = 3600):
    """Remove audio files older than max_age_seconds (default 1 hour)."""
    now = time.time()
    with _lock:
        expired = [f for f, t in _file_registry.items() if now - t > max_age_seconds]
        for filename in expired:
            filepath = os.path.join(AUDIO_DIR, filename)
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                del _file_registry[filename]
            except Exception as e:
                print(f"[AUDIO_CACHE] Cleanup error for {filename}: {e}")
    if expired:
        print(f"[AUDIO_CACHE] Cleaned up {len(expired)} old audio files")