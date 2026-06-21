# System Architecture

## Component Overview

```
STREAMLIT FRONTEND
  Voice Input (WAV) | Text Input | Session Status | Action Log
         |
    HTTP (REST)
         |
FASTAPI BACKEND
  /chat  /voice  /session  /outbound/trigger  /twilio/twiml
         |
SPEECH PIPELINE
  Faster-Whisper (STT)          Kokoro TTS (TTS)
         |
LANGGRAPH PLANNER AGENT
  SystemPrompt -> Agent Node -> should_continue? -> Tool Node
                     ^                                  |
                     +----------------------------------+
                       (loop until no tool calls)
         |
  TOOL LAYER           MEMORY LAYER        OUTBOUND AGENT
  customer_tools       vector_store.py     outbound.py
  order_tools          (Qdrant)            scheduler.py
  refund_tools         session_store.py    Twilio REST API
  ticket_tools         (in-memory)
  email_tools
  rag_tools
  twilio_tools
         |
    PostgreSQL + Qdrant
```

## Agent Decision Flow Example

```
User: "I want a refund for order ORD-10042"
  1. Agent: needs to verify identity first
     -> "Could you provide the email on your account?"
  2. User: "john@example.com"
  3. Tool: verify_customer_by_email -> VERIFIED
  4. Tool: check_refund_eligibility("ORD-10042") -> eligible, $149.99
  5. Agent: "Eligible for full refund. Shall I process it?"
  6. User: "Yes"
  7. Tool: process_refund -> REF-ABC123
  8. Tool: send_refund_confirmation -> email sent
  9. Agent: "Done! REF-ABC123 submitted. 5-7 business days."
```
