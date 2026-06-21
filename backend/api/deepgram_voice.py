"""
Deepgram Voice Agent — replaces the Twilio <Gather> / Cartesia TTS round-trip.

Architecture
────────────
  Twilio phone call
      │  (Media Stream WebSocket — mulaw 8 kHz)
      ▼
  /twilio/media-stream  ← this file
      │  (WebSocket — raw binary mulaw 8 kHz frames to/from Deepgram)
      ▼
  Deepgram Voice Agent API  (wss://agent.deepgram.com/agent)
      • STT  : Nova-3
      • LLM  : Groq (via OpenAI-compatible endpoint)
      • TTS  : Aura-2
      │
      │  FunctionCallRequest  ──►  our LangChain tools  ──►  FunctionCallResponse
      │  ConversationText     ──►  logged
      │  UserStartedSpeaking  ──►  <clear> sent to Twilio (barge-in)
      └──────────────────────────────────────────────────────────────────────────

Twilio phone-number webhook
───────────────────────────
  Point your Twilio number's Voice URL to:
    POST  https://<your-ngrok>/twilio/connect

That endpoint returns TwiML <Connect><Stream> which tells Twilio to open the
WebSocket to this server.  All audio then flows through media-stream.
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
import os

import websockets
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config.settings import get_settings
from backend.agents.planner import ALL_TOOLS, SYSTEM_PROMPT

router = APIRouter()
settings = get_settings()

# ── Build Deepgram function schemas from existing LangChain tools ──────────

def _tool_to_function(tool) -> dict:
    """Convert a LangChain @tool to an OpenAI-style function definition."""
    if getattr(tool, "args_schema", None) is not None:
        try:
            raw = tool.args_schema.model_json_schema()
        except Exception:
            raw = {}
    else:
        raw = {}

    params: dict = {
        "type": "object",
        "properties": raw.get("properties", {}),
    }
    if raw.get("required"):
        params["required"] = raw["required"]

    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": params,
    }


DEEPGRAM_FUNCTIONS = [_tool_to_function(t) for t in ALL_TOOLS]
TOOL_MAP = {t.name: t for t in ALL_TOOLS}


# ── Deepgram Settings payload ──────────────────────────────────────────────

GREETING = "Hey there! This is Maya from ShopEase. How can I help you today?"


def _build_settings() -> dict:
    """
    Build the Deepgram Voice Agent v1 Settings message.
    Audio: mulaw 8 kHz in both directions — no conversion needed with Twilio.
    LLM: Groq via OpenAI-compatible endpoint using the v1 provider.endpoint format.
    """
    return {
        "type": "Settings",
        "audio": {
            "input":  {"encoding": "mulaw", "sample_rate": 8000},
            "output": {"encoding": "mulaw", "sample_rate": 8000, "container": "none"},
        },
        "agent": {
            "listen": {
                "provider": {
                    "type": "deepgram",
                    "model": "nova-3-general",
                },
            },
            "think": {
                "provider": {
                    "type": "open_ai",
                    "model": settings.groq_model,
                    "temperature": 0.6,
                },
                "endpoint": {
                    "url": "https://api.groq.com/openai/v1/chat/completions",
                    "headers": {
                        "Authorization": f"Bearer {settings.groq_api_key}",
                    },
                },
                "prompt": SYSTEM_PROMPT,
                "functions": DEEPGRAM_FUNCTIONS,
            },
            "speak": {
                "provider": {
                    # Aura-2-Asteria: warm, professional female voice — matches "Maya"
                    "type": "deepgram",
                    "model": "aura-2-asteria-en",
                },
            },
            "greeting": GREETING,
        },
    }


# ── Tool execution ─────────────────────────────────────────────────────────

async def _run_tool(name: str, inputs: dict) -> str:
    """
    Dispatch a Deepgram FunctionCallRequest to the matching LangChain tool.
    Runs the synchronous tool in a thread-pool so we don't block the event loop.
    """
    tool = TOOL_MAP.get(name)
    if not tool:
        return json.dumps({"error": f"Tool '{name}' not found."})
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, tool.invoke, inputs
        )
        return json.dumps(result) if isinstance(result, (dict, list)) else str(result)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── TwiML connect endpoint ─────────────────────────────────────────────────

@router.api_route("/twilio/connect", methods=["GET", "POST"])
async def twilio_connect(request: Request) -> Response:
    """
    Return TwiML that opens a Twilio Media Stream to this server.

    Set your Twilio phone number's Voice webhook to:
      POST  https://<ngrok-host>/twilio/connect
    """
    base = settings.twilio_webhook_base_url.rstrip("/")
    wss_url = base.replace("https://", "wss://").replace("http://", "ws://")
    stream_url = f"{wss_url}/twilio/media-stream"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{stream_url}"/>
  </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


# ── Media Stream WebSocket ─────────────────────────────────────────────────

@router.websocket("/twilio/media-stream")
async def media_stream(twilio_ws: WebSocket) -> None:
    """
    Bidirectional relay between Twilio Media Stream and Deepgram Voice Agent.

    Twilio frames  → raw mulaw bytes  → Deepgram
    Deepgram audio → base64 mulaw     → Twilio JSON
    Deepgram FunctionCallRequest      → tool exec → FunctionCallResponse
    Deepgram UserStartedSpeaking      → <clear>   → Twilio (barge-in)
    """
    await twilio_ws.accept()
    stream_sid: str | None = None

    if not settings.deepgram_api_key:
        print("[DG] ERROR: DEEPGRAM_API_KEY is not set — closing connection.")
        await twilio_ws.close()
        return

    # Correct Voice Agent endpoint (v1). Auth via Authorization header —
    # websockets >=14 uses `additional_headers` kwarg on the new async API.
    dg_url = "wss://agent.deepgram.com/v1/agent/converse"
    dg_headers = [("Authorization", f"Token {settings.deepgram_api_key}")]
    dg_settings = _build_settings()

    try:
        async with websockets.connect(
            dg_url,
            additional_headers=dg_headers,
            ping_interval=5,
            ping_timeout=20,
        ) as dg_ws:

            # ── 1. Send configuration ──────────────────────────────────────
            settings_json = json.dumps(dg_settings)
            await dg_ws.send(settings_json)
            # Log settings without the full system prompt / function list
            print(f"[DG] Settings sent — listen={dg_settings['agent']['listen']['provider']['model']}, "
                  f"think={dg_settings['agent']['think']['provider']['model']}, "
                  f"speak={dg_settings['agent']['speak']['provider']['model']}, "
                  f"functions={len(dg_settings['agent']['think']['functions'])}")

            # ── 2. Twilio → Deepgram ───────────────────────────────────────
            async def twilio_to_dg() -> None:
                nonlocal stream_sid
                try:
                    while True:
                        raw = await twilio_ws.receive_text()
                        msg = json.loads(raw)
                        event = msg.get("event")

                        if event == "start":
                            stream_sid = msg["start"]["streamSid"]
                            print(f"[DG] Stream started: {stream_sid}")

                        elif event == "media":
                            audio = base64.b64decode(msg["media"]["payload"])
                            await dg_ws.send(audio)

                        elif event == "stop":
                            print(f"[DG] Stream stopped: {stream_sid}")
                            break

                except WebSocketDisconnect:
                    print("[DG] Twilio disconnected.")
                except Exception as exc:
                    print(f"[DG] twilio_to_dg: {exc}")

            # ── 3. Deepgram → Twilio ───────────────────────────────────────
            async def dg_to_twilio() -> None:
                nonlocal stream_sid
                try:
                    async for msg in dg_ws:

                        # ── Binary: TTS audio ──────────────────────────────
                        if isinstance(msg, bytes):
                            if stream_sid:
                                payload = base64.b64encode(msg).decode("utf-8")
                                await twilio_ws.send_json({
                                    "event":     "media",
                                    "streamSid": stream_sid,
                                    "media":     {"payload": payload},
                                })

                        # ── JSON: control events ───────────────────────────
                        else:
                            print(f"[DG RAW] {msg[:300]}")
                            event = json.loads(msg)
                            etype = event.get("type", "")

                            if etype == "SettingsApplied":
                                print("[DG] Ready — settings applied.")
                                # Greeting is handled by agent.greeting in the Settings
                                # payload — no InjectAgentMessage needed here.

                            elif etype == "UserStartedSpeaking":
                                # Barge-in: discard queued TTS audio in Twilio
                                if stream_sid:
                                    await twilio_ws.send_json({
                                        "event":     "clear",
                                        "streamSid": stream_sid,
                                    })

                            elif etype == "ConversationText":
                                role = event.get("role", "?")
                                text = event.get("content", "")
                                print(f"[DG] {role.upper()}: {text}")

                            elif etype == "FunctionCallRequest":
                                # v1 format: functions is an array of call objects
                                for fn in event.get("functions", []):
                                    fn_name    = fn.get("name", "")
                                    fn_call_id = fn.get("id", "")
                                    try:
                                        fn_input = json.loads(fn.get("arguments", "{}"))
                                    except Exception:
                                        fn_input = {}
                                    print(f"[DG] Tool call → {fn_name}({fn_input})")

                                    result = await _run_tool(fn_name, fn_input)
                                    print(f"[DG] Tool result → {result[:120]}")

                                    await dg_ws.send(json.dumps({
                                        "type":    "FunctionCallResponse",
                                        "id":      fn_call_id,
                                        "name":    fn_name,
                                        "content": result,
                                    }))

                            elif etype == "AgentStartedSpeaking":
                                print("[DG] Agent speaking…")

                            elif etype == "AgentAudioDone":
                                pass  # end of a TTS utterance — nothing to do

                            elif etype == "Error":
                                print(f"[DG] Error from Deepgram: {event}")
                                if event.get("code") == "FAILED_TO_THINK":
                                    # Groq rate-limit or context overflow — stay on the call
                                    await dg_ws.send(json.dumps({
                                        "type": "InjectAgentMessage",
                                        "message": "Sorry about that, give me just a moment.",
                                    }))

                            elif etype == "Welcome":
                                print(f"[DG] Connected — session_id={event.get('session_id')}")

                            elif etype == "Close":
                                print(f"[DG] Deepgram closed connection: {event.get('reason')}")
                                break

                            # else: Metadata etc. — ignore silently

                except Exception as exc:
                    print(f"[DG] dg_to_twilio: {exc}")

            # ── Run both directions concurrently ───────────────────────────
            await asyncio.gather(twilio_to_dg(), dg_to_twilio())

    except Exception as exc:
        print(f"[DG] Failed to connect to Deepgram: {exc}")
        import traceback
        traceback.print_exc()
