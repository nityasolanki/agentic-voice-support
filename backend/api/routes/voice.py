"""
Voice conversation routes.
Handles audio upload → STT → agent → TTS → response.
"""
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.memory.session import create_session, get_session, CustomerSession
from backend.services.stt import transcribe_audio
from backend.services.tts import synthesize_speech
from backend.services.qdrant import search, store_conversation_memory
from backend.agents.planner import classify_intent
from backend.agents.verification import run_verification
from backend.agents.order_management import run_order_management
from backend.agents.refund import run_refund
from backend.agents.ticketing import run_ticketing
from backend.agents.escalation import run_escalation
from config.prompts import RAG_SYSTEM_PROMPT

router = APIRouter()


# ── Session Management ─────────────────────────────────────────────────────

@router.post("/session")
async def start_session():
    """Start a new support session. Returns session_id."""
    session = create_session()
    return {"session_id": session.session_id}


@router.delete("/session/{session_id}")
async def end_session(session_id: str):
    from backend.memory.session import close_session
    close_session(session_id)
    return {"status": "closed"}


# ── Text Turn (for testing without audio) ────────────────────────────────

@router.post("/text")
async def text_turn(
    session_id: str = Form(...),
    message: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Process a text message and return a text response."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.add_turn("user", message)
    response_text = await _dispatch(session, message, db)
    session.add_turn("assistant", response_text)

    # Store in vector memory
    await store_conversation_memory(session_id, session.customer_id or "guest", "user", message)
    await store_conversation_memory(session_id, session.customer_id or "guest", "assistant", response_text)

    return {
        "response": response_text,
        "session_id": session_id,
        "is_verified": session.is_verified,
        "customer_name": session.customer_name,
    }


# ── Voice Turn ────────────────────────────────────────────────────────────

@router.post("/turn")
async def voice_turn(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Full voice round-trip:
    1. Transcribe incoming audio (Faster-Whisper)
    2. Dispatch to appropriate agent
    3. Synthesize response (Kokoro TTS)
    4. Return WAV bytes
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    audio_bytes = await audio.read()
    transcript = await transcribe_audio(audio_bytes)

    if not transcript:
        fallback = "I didn't catch that. Could you please repeat?"
        wav = await synthesize_speech(fallback)
        return Response(content=wav, media_type="audio/wav")

    session.add_turn("user", transcript)
    response_text = await _dispatch(session, transcript, db)
    session.add_turn("assistant", response_text)

    wav = await synthesize_speech(response_text)
    return Response(
        content=wav,
        media_type="audio/wav",
        headers={
            "X-Transcript": transcript,
            "X-Response": response_text,
        },
    )


# ── Dispatch Logic ─────────────────────────────────────────────────────────

async def _dispatch(session: CustomerSession, message: str, db) -> str:
    """Route the message to the right agent and return a response string."""

    # Verification gate
    if not session.is_verified:
        return await run_verification(session, message, db)

    # Intent classification
    intent = classify_intent(message)

    if intent == "track_order":
        return await run_order_management(session, message, db)

    if intent == "refund":
        return await run_refund(session, message, db)

    if intent in ("damaged", "ticket"):
        return await run_ticketing(session, message, db)

    # Frustration check
    frustration_words = ["angry", "frustrated", "unacceptable", "terrible", "lawsuit"]
    if any(w in message.lower() for w in frustration_words):
        return await run_escalation(session, message, db)

    # Fallback: RAG knowledge base search
    return await _rag_response(message)


async def _rag_response(query: str) -> str:
    """Search the knowledge base and answer using retrieved context."""
    from backend.services.llm import llm_service

    results = await search(query, top_k=3)
    if not results:
        return (
            "I want to make sure I give you accurate information. "
            "Let me connect you with a specialist who can help. "
            "Would you like me to create a support ticket?"
        )

    context = "\n\n".join(r.get("text", "") for r in results)
    prompt = f"Context:\n{context}\n\nCustomer question: {query}"
    return await llm_service.chat(
        messages=[{"role": "user", "content": prompt}],
        system=RAG_SYSTEM_PROMPT,
    )
