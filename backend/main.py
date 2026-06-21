"""
FastAPI application — main entry point.

Voice pipeline (primary):
  Twilio Media Stream -> /twilio/media-stream (WebSocket)
  -> Deepgram Voice Agent (Nova-3 STT + Groq LLM + Aura-2 TTS)
  -> audio streams back over same WebSocket

Voice pipeline (legacy fallback — kept for reference):
  Twilio <Gather> -> /twilio/respond -> Groq LLM -> Cartesia TTS -> <Play>

To activate the new pipeline:
  1. Add DEEPGRAM_API_KEY to .env
  2. Point your Twilio phone number's Voice URL to POST /twilio/connect
"""
from __future__ import annotations
import uuid
import html
import re
import io
import structlog

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config.settings import get_settings
from backend.schemas.api_schemas import ChatRequest, ChatResponse, OutboundCallRequest
from backend.memory.session_store import session_store
from backend.agents.planner import run_agent, AgentState
from backend.agents.speech import transcribe_audio, synthesize_speech
from backend.agents.audio_cache import get_audio_url, AUDIO_DIR, cleanup_old_files
from backend.api.deepgram_voice import router as deepgram_router

settings = get_settings()
log = structlog.get_logger()

app = FastAPI(
    title="Agentic Voice Customer Support",
    version="2.0.0",
    description="AI-powered voice support — Deepgram Voice Agent (Nova-3 STT · Groq LLM · Aura-2 TTS)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Deepgram Voice Agent router (new pipeline)
app.include_router(deepgram_router)

# Serve legacy Cartesia audio files (still used by /voice Streamlit endpoint)
app.mount("/audio", StaticFiles(directory=AUDIO_DIR), name="audio")


# ── Startup: seed test data ───────────────────────────────────

@app.on_event("startup")
async def seed_test_data():
    from sqlalchemy import text
    from backend.db.session import sync_engine
    try:
        with sync_engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO customers (email, name, phone, subscription_active, created_at)
                VALUES ('test@test.com', 'Test User', '+910000000000', true, NOW())
                ON CONFLICT (email) DO NOTHING
            """))
            conn.commit()
            row = conn.execute(text("SELECT id FROM customers WHERE email='test@test.com'")).fetchone()
            if not row:
                return
            cid = row[0]
            statuses = [r[0] for r in conn.execute(text("SELECT unnest(enum_range(NULL::orderstatus))")).fetchall()]
            shipped    = next((s for s in statuses if 'ship'    in s.lower()), statuses[0])
            delivered  = next((s for s in statuses if 'deliver' in s.lower()), statuses[0])
            processing = next((s for s in statuses if 'process' in s.lower()), statuses[0])
            conn.execute(text(f"""
                INSERT INTO orders (order_number, customer_id, status, total_amount, tracking_number, carrier, estimated_delivery, created_at)
                VALUES
                  ('ORD-001', {cid}, '{shipped}',    99.99,  '1Z999AA10123456784', 'UPS',   NOW() + INTERVAL '2 days', NOW() - INTERVAL '3 days'),
                  ('ORD-002', {cid}, '{delivered}',  149.99, '1Z999AA10123456785', 'FedEx', NOW() - INTERVAL '1 day',  NOW() - INTERVAL '7 days'),
                  ('ORD-003', {cid}, '{processing}',  49.99, NULL, NULL,           NOW() + INTERVAL '5 days', NOW() - INTERVAL '1 day')
                ON CONFLICT (order_number) DO UPDATE SET customer_id = EXCLUDED.customer_id
            """))
            conn.commit()
            print(f"[STARTUP] Test customer (id={cid}) and orders ORD-001/002/003 ready.")
    except Exception as e:
        print(f"[STARTUP] Seed failed: {e}")


# ── Helpers ───────────────────────────────────────────────────

def clean_speech_input(text: str) -> str:
    """Fix common Twilio speech recognition mistakes."""
    text = re.sub(r'\b(\d)\s+(?=\d)', r'\1', text)
    text = re.sub(r'\s+dash\s+', '-', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+dash$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'([a-zA-Z])\.\s*([a-zA-Z])', r'\1 \2', text)

    def fix_order_number(match):
        digits_only = re.sub(r'[^\d]', '', match.group(2))
        if not digits_only:
            return match.group(0)
        return f"ORD-{digits_only.zfill(3)}"

    text = re.sub(
        r'\b(ord|odd|od|or-d|o-r-d|already|order|orders|over the|over-the|o r d|o\.r\.d)'
        r'[\s\-\.]*((?:\d[\s,\.]*){1,5})',
        fix_order_number, text, flags=re.IGNORECASE
    )

    text = re.sub(
        r'^(yeah[,.]?\s*|yes[,.]?\s*|sure[,.]?\s*)(\d{3,4})$',
        lambda m: f"{m.group(1)}ORD-{m.group(2).zfill(3)}",
        text.strip(), flags=re.IGNORECASE
    )

    def fix_ticket_number(match):
        digits_only = re.sub(r'[^\d]', '', match.group(2))
        return f"TKT-{digits_only}" if digits_only else match.group(0)

    text = re.sub(
        r'\b(tkt|ticket|t-k-t)[\s\-]*((?:\d[\s,\.]*){1,5})',
        fix_ticket_number, text, flags=re.IGNORECASE
    )

    text = re.sub(r'(?<=\w)\s+at\s+(?=\w)', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'(?<=\w)\s+dot\s+(?=\w)', '.', text, flags=re.IGNORECASE)
    text = re.sub(r'\btext@', 'test@', text, flags=re.IGNORECASE)
    text = re.sub(r'\btets@', 'test@', text, flags=re.IGNORECASE)
    text = re.sub(r'\btes@',  'test@', text, flags=re.IGNORECASE)
    text = re.sub(r'@this\.com\b',   '@test.com', text, flags=re.IGNORECASE)
    text = re.sub(r'@thesis\.com\b', '@test.com', text, flags=re.IGNORECASE)

    return text.strip()


def clean_for_tts(text: str) -> str:
    """Strip markdown and leaked function calls before sending to Cartesia."""
    text = re.sub(r'<function=\w+>.*?</function>', '', text, flags=re.DOTALL)
    text = re.sub(r'<function=\w+>.*$', '', text, flags=re.DOTALL)
    text = re.sub(r"[*#`_]", "", text)
    text = re.sub(r"\s*[-•]\s+", ". ", text)
    text = re.sub(r"\s*\d+\.\s+", ". ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > 200:
        trimmed = text[:200]
        last_end = max(trimmed.rfind(". "), trimmed.rfind("? "), trimmed.rfind("! "))
        text = trimmed[:last_end + 1] if last_end > 50 else trimmed

    return text


def run_agent_sync(session_id: str, message: str) -> str:
    """Run the agent synchronously for Twilio calls."""
    session = session_store.get_or_create(session_id)
    session.add_message("user", message)

    recent_messages = session.messages[-10:]

    state: AgentState = {
        "messages": [
            {"role": m["role"], "content": m["content"]}
            for m in recent_messages
        ],
        "session_id": session_id,
        "customer_id": session.customer_id,
        "customer_name": session.customer_name,
        "verified": session.verified,
        "intent": None,
    }

    response_text, updated_state = run_agent(message, state)

    session.customer_id = updated_state.get("customer_id") or session.customer_id
    session.customer_name = updated_state.get("customer_name") or session.customer_name
    session.verified = updated_state.get("verified") or session.verified

    recent_replies = [m["content"] for m in session.messages if m["role"] == "assistant"]
    if len(recent_replies) >= 3 and len(set(recent_replies[-3:])) == 1:
        print(f"[LOOP DETECTED] {session_id}")
        response_text = "Sorry about that! What can I help you with?"

    session.add_message("assistant", response_text)
    return response_text


# ── Session management ────────────────────────────────────────

@app.post("/session/new")
async def new_session() -> dict:
    session_id = str(uuid.uuid4())
    session = session_store.create(session_id)
    return {"session_id": session_id, "created_at": str(session.created_at)}


@app.delete("/session/{session_id}")
async def end_session(session_id: str) -> dict:
    session_store.delete(session_id)
    return {"message": "Session ended."}


# ── Text chat ─────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    session = session_store.get_or_create(request.session_id)
    session.add_message("user", request.message)

    recent_messages = session.messages[-10:]

    state: AgentState = {
        "messages": [
            {"role": m["role"], "content": m["content"]}
            for m in recent_messages
        ],
        "session_id": request.session_id,
        "customer_id": session.customer_id,
        "customer_name": session.customer_name,
        "verified": session.verified,
        "intent": None,
    }

    response_text, updated_state = run_agent(request.message, state)

    session.customer_id = updated_state.get("customer_id") or session.customer_id
    session.customer_name = updated_state.get("customer_name") or session.customer_name
    session.verified = updated_state.get("verified") or session.verified
    session.add_message("assistant", response_text)

    log.info("chat_turn", session_id=request.session_id, response_len=len(response_text))
    return ChatResponse(
        session_id=request.session_id,
        response=response_text,
        customer_verified=session.verified,
        customer_name=session.customer_name,
    )


# ── Voice endpoint (Streamlit UI) ────────────────────────────

@app.post("/voice")
async def voice_chat(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
):
    audio_bytes = await audio.read()
    try:
        transcript = transcribe_audio(audio_bytes)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Transcription failed: {e}")
    if not transcript.strip():
        raise HTTPException(status_code=422, detail="No speech detected in audio.")

    chat_req = ChatRequest(session_id=session_id, message=transcript)
    chat_resp = await chat(chat_req)
    audio_response = synthesize_speech(chat_resp.response)

    return StreamingResponse(
        io.BytesIO(audio_response), media_type="audio/wav",
        headers={
            "X-Transcript": transcript,
            "X-Response-Text": chat_resp.response,
            "X-Session-Id": session_id,
        },
    )


# ── Outbound calling ──────────────────────────────────────────

@app.post("/outbound/trigger")
async def trigger_outbound(request: OutboundCallRequest) -> dict:
    from backend.agents.outbound import run_delay_notification_campaign, run_ticket_followup_campaign
    from backend.db.models import Customer
    from backend.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        customer = await db.get(Customer, request.customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found.")
    if request.reason == "delay_notification":
        run_delay_notification_campaign()
    elif request.reason == "ticket_followup":
        run_ticket_followup_campaign()
    return {"message": f"Outbound campaign '{request.reason}' triggered."}


# ── Twilio Webhooks ───────────────────────────────────────────
# Legacy pipeline: Twilio <Gather> -> Groq LLM -> Cartesia TTS -> <Play>
# New pipeline: use /twilio/connect (defined in deepgram_voice.py)

GATHER = (
    'input="speech" action="/twilio/respond" method="POST" '
    'speechTimeout="auto" language="en-US" timeout="15" '
    'speechModel="phone_call" enhanced="true"'
)


def build_play_twiml(text: str, emotion: str | None, fallback_say: str) -> str:
    """
    Generate TwiML that plays Cartesia audio if available,
    falls back to Polly <Say> if Cartesia fails.
    """
    audio_url = get_audio_url(text, emotion_override=emotion)
    if audio_url:
        return f'<Play>{audio_url}</Play>'
    else:
        print(f"[TWILIO] Cartesia failed, falling back to Polly for: {text[:50]}")
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f'<Say voice="Polly.Joanna">{escaped}</Say>'


@app.api_route("/twilio/outbound-twiml", methods=["GET", "POST"])
async def outbound_twiml():
    """
    TwiML for outbound calls.
    If Deepgram is configured, opens a Media Stream (low-latency).
    Falls back to legacy <Gather> if DEEPGRAM_API_KEY is not set.
    """
    if settings.deepgram_api_key:
        base = settings.twilio_webhook_base_url.rstrip("/")
        wss_url = base.replace("https://", "wss://").replace("http://", "ws://")
        stream_url = f"{wss_url}/twilio/media-stream"
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{stream_url}"/>
  </Connect>
</Response>"""
    else:
        # Legacy Gather fallback
        greeting = "Hey there! This is Maya from ShopEase. How can I help you today?"
        play_or_say = build_play_twiml(greeting, "warm_greeting", greeting)
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather {GATHER}>
    {play_or_say}
  </Gather>
  <Say voice="Polly.Joanna">Didn't catch you. Call back anytime!</Say>
  <Hangup/>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@app.post("/twilio/respond")
async def twilio_respond(request: Request):
    call_sid = "unknown"
    try:
        form = await request.form()
        call_sid = form.get("CallSid", "unknown")
        session_id = f"call-{call_sid}"

        raw_speech = form.get("SpeechResult", "").strip()
        speech_result = clean_speech_input(raw_speech)
        print(f"[TWILIO] Raw='{raw_speech}' | Cleaned='{speech_result}'")

        if not speech_result:
            retry_text = "Sorry, didn't catch that. Go ahead!"
            play_or_say = build_play_twiml(retry_text, "curious", retry_text)
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather {GATHER}>
    {play_or_say}
  </Gather>
  <Hangup/>
</Response>"""
            return Response(content=twiml, media_type="application/xml")

        agent_reply = run_agent_sync(session_id, speech_result)
        agent_reply = clean_for_tts(agent_reply)
        print(f"[AGENT] '{agent_reply}'")

        play_or_say = build_play_twiml(agent_reply, None, agent_reply)

        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather {GATHER}>
    {play_or_say}
  </Gather>
  <Say voice="Polly.Joanna">Take care! Bye!</Say>
  <Hangup/>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        print(f"[ERROR] twilio_respond CallSid={call_sid}: {e}")
        import traceback; traceback.print_exc()
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Joanna">Something went wrong. Please call back!</Say>
  <Hangup/>
</Response>"""
        return Response(content=twiml, media_type="application/xml")


@app.post("/twilio/hangup")
async def twilio_hangup(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    session_store.delete(f"call-{call_sid}")
    print(f"[TWILIO] Call ended: {call_sid}")
    return Response(content="<Response/>", media_type="application/xml")


# ── Health ────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "model": settings.groq_model,
        "deepgram_enabled": bool(settings.deepgram_api_key),
        "active_sessions": len(session_store.active_sessions()),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
