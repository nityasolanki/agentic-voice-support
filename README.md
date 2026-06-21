# Agentic Voice Customer Support

An AI-powered voice support agent that handles real phone calls end-to-end — verifying customers, looking up orders, processing refunds, raising tickets, and sending email confirmations — all autonomously over a live phone line.

Built on a real-time WebSocket pipeline: **Twilio** streams call audio to **Deepgram** (STT → LLM → TTS), which calls back into a **LangGraph** agent with 17 tools wired to a live PostgreSQL database.

---

## Demo

| Scenario | What happens |
|---|---|
| Customer calls in / receives outbound call | Maya greets, verifies identity via email |
| "Where is my order?" | Looks up order status + tracking in real time |
| "I want a refund" | Checks eligibility, processes refund, sends email confirmation |
| "Cancel my subscription" | Confirms intent, cancels, sends confirmation |
| "My product arrived damaged" | Creates support ticket, escalates if needed |
| Proactive outbound | System detects shipping delay → calls customer automatically |

---

## Architecture

### Voice Pipeline

```
Incoming / Outbound Call
        │
        ▼
  Twilio Media Stream
  (WebSocket — mulaw 8 kHz)
        │
        ▼
  /twilio/media-stream  ←── FastAPI relay server
        │
        ▼
  Deepgram Voice Agent  (wss://agent.deepgram.com/v1/agent/converse)
  ┌─────────────────────────────────────────────┐
  │  STT   Nova-3-General  (speech → text)      │
  │  LLM   Groq / Llama-4-Scout  (reasoning)    │
  │  TTS   Aura-2-Asteria  (text → speech)      │
  └─────────────────────────────────────────────┘
        │  FunctionCallRequest
        ▼
  LangGraph Agent  (17 tools)
  ┌───────────────────────────────────────────────────────┐
  │  verify_customer   get_order   get_shipment_status    │
  │  check_refund_eligibility   process_refund            │
  │  create_ticket   get_ticket   escalate_ticket         │
  │  cancel_subscription   search_knowledge_base          │
  │  send_ticket_confirmation   send_refund_confirmation  │
  │  initiate_outbound_call   send_sms_notification  ...  │
  └───────────────────────────────────────────────────────┘
        │
        ▼
  PostgreSQL  ·  Qdrant (RAG)  ·  Gmail API
```

### Why WebSocket, not HTTP

The old pipeline used Twilio `<Gather>` → HTTP POST → Cartesia TTS → `<Play>` — 4–5 sequential round-trips per turn, 3–6 seconds of silence between customer and agent.

The new pipeline holds **one persistent WebSocket** for the entire call. Audio streams in both directions simultaneously. Response latency drops to under a second. Barge-in (customer interrupting Maya mid-sentence) works automatically.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Telephony** | Twilio (Media Streams, outbound calling, SMS) |
| **Voice AI** | Deepgram Voice Agent (Nova-3 STT · Aura-2 TTS) |
| **LLM** | Groq — Llama-4-Scout-17B (via OpenAI-compatible endpoint) |
| **Agent Framework** | LangGraph + LangChain |
| **Backend** | FastAPI + Uvicorn |
| **Database** | PostgreSQL (SQLAlchemy, asyncpg) |
| **Vector DB** | Qdrant (RAG over knowledge base) |
| **Email** | Gmail API |
| **Frontend** | Streamlit (text + audio chat UI) |
| **WebSocket Client** | `websockets` library |

---

## Project Structure

```
.
├── backend/
│   ├── main.py                  # FastAPI app, legacy Twilio endpoints
│   ├── api/
│   │   └── deepgram_voice.py    # Deepgram Voice Agent relay (primary pipeline)
│   ├── agents/
│   │   ├── planner.py           # LangGraph agent, system prompt, tool registry
│   │   ├── speech.py            # Whisper STT + Cartesia TTS (Streamlit UI path)
│   │   └── outbound.py          # Proactive outbound call campaigns
│   ├── tools/                   # 17 LangChain tools
│   │   ├── customer_tools.py    # verify, profile, cancel subscription
│   │   ├── order_tools.py       # order lookup, shipment status
│   │   ├── refund_tools.py      # eligibility check, process refund
│   │   ├── ticket_tools.py      # create, get, escalate tickets
│   │   ├── email_tools.py       # confirmation emails
│   │   ├── rag_tools.py         # knowledge base search
│   │   └── twilio_tools.py      # outbound calls, SMS
│   ├── db/                      # SQLAlchemy models, seed data, sessions
│   ├── memory/                  # Session store, vector store
│   └── services/                # LLM, STT, TTS, Twilio, Gmail service wrappers
├── config/
│   └── settings.py              # Pydantic settings from .env
├── frontend/                    # Streamlit UI
├── .env                         # API keys and config (not committed)
└── requirements.txt
```

---

## Quickstart

### Prerequisites

- Python 3.11+
- PostgreSQL running locally (or via Docker)
- Qdrant running locally (or via Docker)
- A [Twilio](https://twilio.com) account with a phone number
- A [Deepgram](https://deepgram.com) API key
- A [Groq](https://console.groq.com) API key
- [ngrok](https://ngrok.com) (to expose your local server to Twilio)

### 1. Clone and install

```bash
git clone https://github.com/nityasolanki/agentic-voice-support.git
cd agentic-voice-support
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# LLM
GROQ_API_KEY=gsk_...
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct

# Voice
DEEPGRAM_API_KEY=...

# Telephony
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1...
TWILIO_WEBHOOK_BASE_URL=https://<your-ngrok-subdomain>.ngrok-free.app

# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=support_db
POSTGRES_USER=support_user
POSTGRES_PASSWORD=support_pass

# Vector DB
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

### 3. Start infrastructure

```bash
docker-compose up -d   # starts PostgreSQL + Qdrant
```

### 4. Run the backend

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Expose to the internet

```bash
ngrok http 8000
# copy the https URL into TWILIO_WEBHOOK_BASE_URL in .env, then restart the server
```

### 6. Configure Twilio

In your [Twilio Console](https://console.twilio.com), set your phone number's **Voice webhook** to:

```
POST https://<your-ngrok-url>/twilio/connect
```

### 7. Run the Streamlit UI (optional)

```bash
streamlit run frontend/app.py
```

---

## How a Call Works

```
1.  Customer calls your Twilio number (or server triggers outbound)
2.  Twilio hits POST /twilio/connect
3.  Server returns TwiML: <Connect><Stream url="wss://.../twilio/media-stream"/>
4.  Twilio opens a WebSocket, streams raw audio (mulaw 8kHz)
5.  Server opens a second WebSocket to Deepgram Voice Agent
6.  Server sends Settings: STT model, Groq LLM endpoint, TTS voice, all 17 tools, Maya's personality prompt
7.  Deepgram acknowledges with SettingsApplied
8.  Deepgram speaks Maya's greeting → audio streams back → Twilio plays it

--- conversation loop (all over the same open connections) ---

9.  Customer speaks → audio chunks → Twilio → server → Deepgram
10. Nova-3 transcribes speech to text
11. Llama-4-Scout reasons, may decide to call a tool
12. Deepgram sends FunctionCallRequest to server
13. Server runs the matching LangChain tool (DB query, refund, ticket, etc.)
14. Server sends FunctionCallResponse back to Deepgram
15. Aura-2-Asteria synthesises Maya's reply → audio streams back
16. Twilio plays audio to the customer in real time
17. If customer speaks while Maya is talking → barge-in → Maya stops immediately

--- call ends ---

18. Customer hangs up → stream stop event → both WebSockets close cleanly
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/twilio/connect` | Returns TwiML to open Media Stream (primary pipeline) |
| `WS` | `/twilio/media-stream` | Bidirectional audio relay to Deepgram |
| `POST` | `/twilio/outbound-twiml` | TwiML for outbound calls |
| `POST` | `/twilio/respond` | Legacy Gather pipeline (fallback) |
| `POST` | `/chat` | Text chat via API |
| `POST` | `/voice` | Audio upload → transcript → audio response (Streamlit UI) |
| `POST` | `/outbound/trigger` | Trigger proactive outbound campaign |
| `POST` | `/session/new` | Create a new chat session |
| `DELETE` | `/session/{id}` | End a session |
| `GET` | `/health` | Health check + active session count |

---

## Environment Variables

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Groq API key for LLM inference |
| `GROQ_MODEL` | Model ID (default: `meta-llama/llama-4-scout-17b-16e-instruct`) |
| `DEEPGRAM_API_KEY` | Deepgram API key (STT + Voice Agent + TTS) |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_FROM_NUMBER` | Your Twilio phone number |
| `TWILIO_WEBHOOK_BASE_URL` | Public URL of your server (ngrok URL in dev) |
| `POSTGRES_*` | PostgreSQL connection details |
| `QDRANT_HOST` / `QDRANT_PORT` | Qdrant vector DB connection |
| `GMAIL_CREDENTIALS_FILE` | Path to Gmail OAuth credentials JSON |
| `GMAIL_SENDER_EMAIL` | Sender address for confirmation emails |
