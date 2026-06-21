"""
Speech pipeline — STT (Faster-Whisper) + TTS (Cartesia sonic-2)
Updated for Cartesia SDK v3.2.0 API.
"""
from __future__ import annotations
import io
import re
import tempfile
import os


# ── STT: Faster-Whisper ───────────────────────────────────────
_whisper_model = None


def get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model


def transcribe_audio(audio_bytes: bytes, language: str = "en") -> str:
    model = get_whisper()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name
    try:
        segments, _ = model.transcribe(tmp_path, language=language, beam_size=5)
        return " ".join(seg.text.strip() for seg in segments).strip()
    finally:
        os.unlink(tmp_path)


# ── Emotion Engine ────────────────────────────────────────────
# Cartesia v3 'speed' param accepts: "slowest" | "slow" | "normal" | "fast" | "fastest"

EMOTIONS = {
    "happy":         {"speed": "normal"},
    "warm_greeting": {"speed": "normal"},
    "empathetic":    {"speed": "slow"},
    "very_sorry":    {"speed": "slow"},
    "excited":       {"speed": "fast"},
    "curious":       {"speed": "normal"},
    "reassuring":    {"speed": "slow"},
    "professional":  {"speed": "normal"},
    "thinking":      {"speed": "normal"},
    "farewell":      {"speed": "normal"},
}


def classify_emotion(text: str) -> str:
    t = text.lower()
    if any(w in t for w in [
        "i'm so sorry", "deeply sorry", "sincerely apologize",
        "this is unacceptable", "escalat", "urgent",
        "i completely understand your frustration"
    ]):
        return "very_sorry"
    if any(w in t for w in [
        "sorry", "apologize", "unfortunately", "i understand",
        "that's frustrating", "oh no", "my apologies",
        "can't find", "not eligible", "cannot", "unable"
    ]):
        return "empathetic"
    if any(w in t for w in [
        "approved", "all set", "you're good", "great news",
        "refund's", "done!", "there we go",
        "successfully", "processed", "created your ticket"
    ]):
        return "excited"
    if any(w in t for w in [
        "perfect", "found you", "found it", "got it",
        "shipped", "delivered", "on its way", "tracking"
    ]):
        return "happy"
    if any(w in t for w in [
        "don't worry", "i'll take care", "let me help",
        "i've got you", "we'll fix this", "i'm on it"
    ]):
        return "reassuring"
    if any(w in t for w in [
        "let me check", "one sec", "just a moment",
        "pulling that up", "give me a second", "looking into"
    ]):
        return "thinking"
    if any(w in t for w in [
        "can you", "could you", "what's", "which one",
        "can i get", "do you have", "what email"
    ]):
        return "curious"
    if any(w in t for w in [
        "hey there", "hello", "hi!", "welcome",
        "how can i help", "happy to help"
    ]):
        return "warm_greeting"
    if any(w in t for w in [
        "take care", "goodbye", "bye", "have a great",
        "anything else", "hope that helps"
    ]):
        return "farewell"
    return "professional"


def add_natural_rhythm(text: str) -> str:
    fillers = [
        r'\b(got it)\b([^,!?.])', r'\b(sure)\b([^,!?.])',
        r'\b(okay)\b([^,!?.])', r'\b(alright)\b([^,!?.])',
        r'\b(absolutely)\b([^,!?.])', r'\b(perfect)\b([^,!?.])',
        r'\b(great)\b([^,!?.])', r'\b(done)\b([^,!?.])',
        r'\b(found you)\b([^,!?.])', r'\b(found it)\b([^,!?.])',
    ]
    for pattern in fillers:
        text = re.sub(pattern, lambda m: f"{m.group(1)},{m.group(2)}",
                       text, flags=re.IGNORECASE, count=1)
    text = re.sub(r'\bso your\b', 'so, your', text, flags=re.IGNORECASE)
    text = re.sub(r'\bso I\b', 'so, I', text, flags=re.IGNORECASE)
    text = re.sub(r'\bso it\b', 'so, it', text, flags=re.IGNORECASE)
    text = re.sub(r'\.(\S)', r'. \1', text)
    text = re.sub(r'\?(\S)', r'? \1', text)
    text = re.sub(r'!(\S)', r'! \1', text)
    return text.strip()


# ── TTS: Cartesia sonic-2 (SDK v3.2.0) ────────────────────────

# Voice IDs from your Cartesia account — verified working
VOICES = {
    "katie":      "f786b574-daa5-4673-aa0c-cbe3e8534c02",  # Friendly Fixer — great for support
    "corey":      "630ed21c-2c5c-41cf-9d82-10a7fd668370",  # Supportive Buddy
    "jacqueline": "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",  # Reassuring Agent
    "skylar":     "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4",  # Friendly Guide
}

DEFAULT_VOICE_ID = VOICES["katie"]


def synthesize_speech(
    text: str,
    emotion_override: str | None = None,
    voice_id: str | None = None,
) -> bytes:
    """
    Convert text to speech using Cartesia sonic-2 (SDK v3.2.0).
    """
    try:
        from cartesia import Cartesia
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from config.settings import get_settings
        settings = get_settings()

        if not settings.cartesia_api_key:
            print("[TTS] No Cartesia API key set")
            return b""

        client = Cartesia(api_key=settings.cartesia_api_key)

        selected_voice_id = voice_id or DEFAULT_VOICE_ID

        if emotion_override and emotion_override in EMOTIONS:
            controls = EMOTIONS[emotion_override]
            emotion_key = emotion_override
        else:
            emotion_key = classify_emotion(text)
            controls = EMOTIONS[emotion_key]

        text = add_natural_rhythm(text)

        print(f"[TTS] Emotion='{emotion_key}' Speed='{controls.get('speed')}' | '{text[:70]}...'")

        # v3.2.0 API: .generate() returns the full response, not a stream of .bytes()
        result = client.tts.bytes(
            model_id="sonic-2",
            transcript=text,
            voice={"id": selected_voice_id, "mode": "id"},
            output_format={
                "container": "wav",
                "encoding": "pcm_f32le",
                "sample_rate": 22050,
            },
            speed=controls.get("speed", "normal"),
        )

        # result may be a generator/iterator of bytes chunks
        if hasattr(result, "__iter__") and not isinstance(result, (bytes, bytearray)):
            audio_bytes = b"".join(result)
        else:
            audio_bytes = result

        return audio_bytes

    except ImportError:
        print("[TTS] Cartesia not installed — run: pip install cartesia")
        return b""
    except Exception as e:
        print(f"[TTS] Cartesia failed: {e}")
        return b""


def speak_happy(text: str) -> bytes:
    return synthesize_speech(text, emotion_override="happy")

def speak_empathetic(text: str) -> bytes:
    return synthesize_speech(text, emotion_override="empathetic")

def speak_very_sorry(text: str) -> bytes:
    return synthesize_speech(text, emotion_override="very_sorry")

def speak_excited(text: str) -> bytes:
    return synthesize_speech(text, emotion_override="excited")

def speak_reassuring(text: str) -> bytes:
    return synthesize_speech(text, emotion_override="reassuring")

def speak_curious(text: str) -> bytes:
    return synthesize_speech(text, emotion_override="curious")