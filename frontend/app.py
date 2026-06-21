"""
Streamlit Voice Customer Support Interface

Features:
- Real-time voice recording & playback
- Text chat fallback
- Session management
- Live action log
- Demo scenario shortcuts
"""
import streamlit as st
import requests
import uuid
import base64
import json
import time
from datetime import datetime

# ── Config ────────────────────────────────────────────────────
API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="AI Voice Support",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Main palette */
  :root {
    --brand: #6C63FF;
    --brand-light: #A89CFF;
    --success: #22C55E;
    --warning: #F59E0B;
    --danger: #EF4444;
    --surface: #1E1E2E;
    --surface2: #2A2A3E;
    --text: #E2E8F0;
    --muted: #94A3B8;
  }

  .stApp { background-color: var(--surface); color: var(--text); }
  .chat-bubble-user {
    background: var(--brand);
    color: white;
    border-radius: 18px 18px 4px 18px;
    padding: 12px 16px;
    margin: 8px 0;
    max-width: 80%;
    margin-left: auto;
    font-size: 15px;
  }
  .chat-bubble-agent {
    background: var(--surface2);
    color: var(--text);
    border-radius: 18px 18px 18px 4px;
    padding: 12px 16px;
    margin: 8px 0;
    max-width: 80%;
    border-left: 3px solid var(--brand);
    font-size: 15px;
  }
  .status-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    margin: 2px;
  }
  .badge-verified { background: #166534; color: #86EFAC; }
  .badge-unverified { background: #7C2D12; color: #FCA5A5; }
  .action-log-item {
    background: var(--surface2);
    border-left: 3px solid var(--brand-light);
    padding: 6px 10px;
    margin: 4px 0;
    border-radius: 0 8px 8px 0;
    font-size: 12px;
    font-family: monospace;
    color: var(--muted);
  }
  .demo-card {
    background: var(--surface2);
    border: 1px solid #3A3A5A;
    border-radius: 12px;
    padding: 12px;
    margin: 6px 0;
    cursor: pointer;
    transition: border-color 0.2s;
  }
  .demo-card:hover { border-color: var(--brand); }
  h1, h2, h3 { color: white !important; }
  .stTextInput input { background: var(--surface2) !important; color: white !important; }
  .stButton button {
    background: var(--brand) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
  }
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.verified = False
    st.session_state.customer_name = None
    st.session_state.action_log = []
    st.session_state.recording = False

def log_action(action: str):
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.action_log.insert(0, f"[{ts}] {action}")
    if len(st.session_state.action_log) > 30:
        st.session_state.action_log.pop()


def send_message(message: str):
    try:
        resp = requests.post(
            f"{API_BASE}/chat",
            json={"session_id": st.session_state.session_id, "message": message},
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            st.session_state.messages.append({"role": "user", "content": message})
            st.session_state.messages.append({"role": "assistant", "content": data["response"]})
            if data.get("customer_verified"):
                st.session_state.verified = True
            if data.get("customer_name"):
                st.session_state.customer_name = data["customer_name"]
            log_action(f"Agent responded ({len(data['response'])} chars)")
            return data["response"]
        else:
            st.error(f"API error: {resp.status_code}")
            return None
    except requests.ConnectionError:
        st.error("⚠️ Cannot connect to backend. Is FastAPI running on port 8000?")
        return None


# ── Layout ────────────────────────────────────────────────────
col_left, col_chat, col_right = st.columns([1, 2.5, 1])

# ── LEFT: Status + Demo Scenarios ────────────────────────────
with col_left:
    st.markdown("### 📊 Session")
    verified_badge = (
        '<span class="status-badge badge-verified">✓ VERIFIED</span>'
        if st.session_state.verified
        else '<span class="status-badge badge-unverified">✗ UNVERIFIED</span>'
    )
    st.markdown(verified_badge, unsafe_allow_html=True)
    if st.session_state.customer_name:
        st.markdown(f"👤 **{st.session_state.customer_name}**")
    st.caption(f"Session: `{st.session_state.session_id[:8]}...`")

    if st.button("🔄 New Session"):
        for key in ["session_id", "messages", "verified", "customer_name", "action_log"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    st.markdown("---")
    st.markdown("### 🎭 Demo Scenarios")
    st.caption("Click to auto-send")

    DEMOS = [
        ("📦 Order Tracking", "Hi, I need to check where my order is."),
        ("💰 Request Refund", "I want to request a refund for my recent order."),
        ("📋 Return Policy", "What is your return and refund policy?"),
        ("❌ Cancel Sub", "I want to cancel my subscription."),
        ("🔧 Damaged Item", "My product arrived damaged. I need help."),
        ("📮 Ticket Status", "Can you check the status of my support ticket?"),
    ]
    for label, msg in DEMOS:
        if st.button(label, use_container_width=True):
            send_message(msg)
            st.rerun()

    st.markdown("---")
    st.markdown("### 📡 Outbound")
    if st.button("🔔 Trigger Delay Notifications", use_container_width=True):
        try:
            r = requests.post(
                f"{API_BASE}/outbound/trigger",
                json={"customer_id": 1, "reason": "delay_notification"},
                timeout=30,
            )
            log_action("Outbound delay notification campaign triggered")
            st.success("Campaign triggered!")
        except Exception as e:
            st.error(str(e))

# ── CENTER: Chat Interface ─────────────────────────────────────
with col_chat:
    st.markdown("# 🎙️ AI Voice Support Agent")
    st.caption("Powered by LangGraph · Ollama · Faster-Whisper · Kokoro TTS")

    # Chat history
    chat_container = st.container()
    with chat_container:
        if not st.session_state.messages:
            st.markdown("""
            <div style="text-align:center; padding: 40px; color: #64748B;">
              <div style="font-size: 48px; margin-bottom: 16px;">🎙️</div>
              <div style="font-size: 18px; font-weight: 600; color: #94A3B8;">Ready to help</div>
              <div style="font-size: 14px; margin-top: 8px;">Type a message, use a demo scenario, or record your voice.</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            for msg in st.session_state.messages:
                if msg["role"] == "user":
                    st.markdown(
                        f'<div class="chat-bubble-user">🧑 {msg["content"]}</div>',
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        f'<div class="chat-bubble-agent">🤖 {msg["content"]}</div>',
                        unsafe_allow_html=True
                    )

    st.markdown("---")

    # Voice recording (browser-based using st.audio_input if available, else file upload)
    st.markdown("#### 🎤 Voice Input")
    audio_file = st.file_uploader(
        "Upload a WAV/MP3 recording", type=["wav", "mp3", "m4a", "ogg"],
        label_visibility="collapsed"
    )
    if audio_file and st.button("🎙️ Transcribe & Send"):
        with st.spinner("Transcribing audio..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/voice",
                    data={"session_id": st.session_state.session_id},
                    files={"audio": (audio_file.name, audio_file.getvalue(), audio_file.type)},
                    timeout=60,
                )
                if resp.status_code == 200:
                    transcript = resp.headers.get("X-Transcript", "")
                    response_text = resp.headers.get("X-Response-Text", "")
                    st.session_state.messages.append({"role": "user", "content": f"🎤 {transcript}"})
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                    log_action(f"Voice: '{transcript[:50]}...'")
                    # Play audio response
                    st.audio(resp.content, format="audio/wav")
                    st.rerun()
            except Exception as e:
                st.error(f"Voice processing failed: {e}")

    st.markdown("#### ⌨️ Text Input")
    with st.form("chat_form", clear_on_submit=True):
        user_input = st.text_input(
            "Type your message...",
            placeholder="e.g. Where is my order ORD-10042?",
            label_visibility="collapsed"
        )
        submitted = st.form_submit_button("Send →", use_container_width=True)
        if submitted and user_input.strip():
            with st.spinner("Agent thinking..."):
                send_message(user_input.strip())
            st.rerun()

# ── RIGHT: Action Log ─────────────────────────────────────────
with col_right:
    st.markdown("### 🔧 Action Log")
    st.caption("Real-time agent activity")

    # Backend health
    try:
        health = requests.get(f"{API_BASE}/health", timeout=3).json()
        st.markdown(f"""
        <div style="background:#14532D; border-radius:8px; padding:8px; margin-bottom:8px;">
          <div style="color:#86EFAC; font-size:12px;">● ONLINE</div>
          <div style="color:#BBF7D0; font-size:11px;">Model: {health.get('model','—')}</div>
          <div style="color:#BBF7D0; font-size:11px;">Sessions: {health.get('active_sessions',0)}</div>
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        st.markdown("""
        <div style="background:#7F1D1D; border-radius:8px; padding:8px; margin-bottom:8px;">
          <div style="color:#FCA5A5; font-size:12px;">✗ BACKEND OFFLINE</div>
          <div style="color:#FECACA; font-size:11px;">Start FastAPI on :8000</div>
        </div>
        """, unsafe_allow_html=True)

    for action in st.session_state.action_log:
        st.markdown(f'<div class="action-log-item">{action}</div>', unsafe_allow_html=True)

    if not st.session_state.action_log:
        st.caption("No actions yet.")

    st.markdown("---")
    st.markdown("### 📋 Capabilities")
    capabilities = [
        "✅ Order tracking",
        "✅ Refund processing",
        "✅ Ticket creation",
        "✅ Knowledge base RAG",
        "✅ Customer verification",
        "✅ Email notifications",
        "✅ Subscription mgmt",
        "✅ Escalation workflows",
        "✅ Outbound calling",
        "✅ Voice I/O (STT+TTS)",
    ]
    for cap in capabilities:
        st.markdown(f"<div style='font-size:12px; color:#94A3B8;'>{cap}</div>", unsafe_allow_html=True)
