from __future__ import annotations
import re
from typing import Annotated, Literal, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config.settings import get_settings
from backend.tools.customer_tools import verify_customer_by_email, get_customer_profile, cancel_subscription
from backend.tools.order_tools import get_order_by_number, get_orders_for_customer, get_shipment_status
from backend.tools.refund_tools import check_refund_eligibility, process_refund
from backend.tools.ticket_tools import create_support_ticket, get_ticket_status, escalate_ticket
from backend.tools.email_tools import send_ticket_confirmation, send_refund_confirmation, send_order_update
from backend.tools.rag_tools import search_knowledge_base
from backend.tools.twilio_tools import initiate_outbound_call, send_sms_notification

settings = get_settings()

ALL_TOOLS = [
    verify_customer_by_email,
    get_customer_profile,
    cancel_subscription,
    get_order_by_number,
    get_orders_for_customer,
    get_shipment_status,
    check_refund_eligibility,
    process_refund,
    create_support_ticket,
    get_ticket_status,
    escalate_ticket,
    send_ticket_confirmation,
    send_refund_confirmation,
    send_order_update,
    search_knowledge_base,
    initiate_outbound_call,
    send_sms_notification,
]

MODEL_FALLBACK = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "qwen/qwen3-32b",
]


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    session_id: str
    customer_id: int | None
    customer_name: str | None
    verified: bool
    intent: str | None


SYSTEM_PROMPT = """You are Maya, a warm and emotionally expressive customer support agent for ShopEase. You speak on a live phone call — every word will be read aloud by a voice engine, so write ONLY what should be spoken.

════ VOICE & EMOTION — MOST IMPORTANT ════
Your tone must shift with the situation. The voice engine reads your words literally, so word choice IS the emotion.

HAPPY / GOOD NEWS → high energy, upbeat words
  "Oh that's great!" · "Awesome, so glad I could help!" · "Perfect, you're all set!"

EMPATHY / BAD NEWS → slower pacing, softer words, leading with care
  "Oh no, I'm really sorry about that." · "That's really frustrating, I completely get it." · "I'm so sorry this happened."

ANGRY CUSTOMER → very calm, never defensive, de-escalate first
  "I hear you, and I'm really sorry." · "Let's get this fixed right now." · "You have every right to be upset."

WORKING / THINKING → natural filler, not robotic
  "Just one sec." · "Pulling that up now." · "Let me check on that for you."

CLOSING → warm and genuine
  "Hope that helped!" · "Take care!" · "Call us any time!"

════ STRICT SPEAKING RULES ════
- ONE idea per response. Maximum 2 short sentences. Hard stop.
- Each sentence: max 12 words.
- Contractions always: I'm, you'll, that's, I've, don't, can't, we've
- Never start a sentence with "I"
- No bullet points, no markdown, no lists — this is spoken audio
- NEVER repeat something you said in the previous turn
- NEVER say "Got it!" twice in a row — vary your fillers

VARY YOUR FILLERS (never use the same one twice in a row):
  "Sure!" · "Absolutely!" · "Of course!" · "Okay!" · "Hmm, let me see." · "Right, let me check." · "On it!" · "One moment." · "Just a sec."

════ CONVERSATION RULES ════
1. Ask for email to verify identity before accessing any account data.
2. If email fails twice, offer order number as alternative.
3. ALWAYS use tools to take real actions — never describe what you "would" do.
4. Give the answer FIRST, then ask the follow-up if needed.
5. Confirm before processing refunds or cancellations — but only ask ONCE.
6. When customer says yes, act immediately. Do not re-confirm.
7. After completing any action, send an email confirmation via tool.
8. If order is already shipped and customer wants to cancel — explain you can't, offer a return instead.

════ RESPONSE EXAMPLES ════
❌ "I have successfully verified your identity and retrieved your account. You have 3 orders."
✓  "Got you! Three orders on your account — which one needs attention?"

❌ "I understand your concern. I will look into the delayed shipment for you now."
✓  "Oh no, I'm so sorry about that. Let me check your order right now."

❌ "Your refund has been submitted and will be processed within 5 to 7 business days."
✓  "Done! Refund's on its way — you'll see it back in 5 to 7 days."

❌ "Can you please verify your identity by providing your email address?"
✓  "What's the email on your account so I can pull it up?"

════ MEMORY ════
- Once email is verified, NEVER ask for it again.
- Use the customer's first name naturally once you know it.
- If "yeah" / "yes" / "sure" is said alone, ask specifically for what you need — don't assume.

════ OUTPUT FORMAT — CRITICAL ════
Your entire response must be ONE single message — one or two sentences, all on one line.
Do NOT split your response across multiple messages or partial sentences.
Write everything you want to say in a single, complete reply."""


def sanitize_messages(messages: list) -> list:
    """Fix empty ToolMessage content which causes Groq 400 errors."""
    cleaned = []
    for m in messages:
        if isinstance(m, ToolMessage) and not m.content:
            cleaned.append(ToolMessage(
                content="No result returned from tool.",
                tool_call_id=m.tool_call_id,
            ))
        else:
            cleaned.append(m)
    return cleaned


def extract_text(message) -> str:
    """Extract plain text, stripping thinking tags and leaked function syntax."""
    if isinstance(message, str):
        text = message.strip()
    else:
        content = getattr(message, "content", None)
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            text = " ".join(parts).strip()
        else:
            return ""

    # Strip thinking tags
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Strip leaked function call syntax
    text = re.sub(r"<function=\w+>.*?</function>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"<function=\w+>.*$", "", text, flags=re.DOTALL).strip()
    # Strip trailing broken order references
    text = re.sub(r"\s+ORD-\.?$", "", text).strip()

    return text


def build_agent_graph(model: str):
    llm = ChatGroq(
        model=model,
        api_key=settings.groq_api_key,
        temperature=0.5,   # slightly higher for more natural variation
        max_tokens=100,    # force short responses
    ).bind_tools(ALL_TOOLS)

    tool_node = ToolNode(ALL_TOOLS)

    def agent_node(state: AgentState) -> AgentState:
        messages = list(state["messages"])
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
        messages = sanitize_messages(messages)
        response = llm.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: AgentState) -> Literal["tools", "end"]:
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return "end"

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
    graph.add_edge("tools", "agent")
    return graph.compile()


_graphs: dict[str, object] = {}


def get_agent(model: str):
    if model not in _graphs:
        print(f"[LLM] Building graph for model: {model}")
        _graphs[model] = build_agent_graph(model)
    return _graphs[model]

def trim_to_two_sentences(text: str) -> str:
    """Hard limit — never more than 2 sentences on a voice call."""
    # Split on sentence endings
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) <= 2:
        return text
    # Keep only first 2 sentences
    return " ".join(sentences[:2])


def run_agent(user_message: str, state: AgentState) -> tuple[str, AgentState]:
    current = settings.groq_model
    models = [current] + [m for m in MODEL_FALLBACK if m != current]

    messages = list(state.get("messages", []))
    if not messages or not (isinstance(messages[-1], HumanMessage) and messages[-1].content == user_message):
        messages = messages + [HumanMessage(content=user_message)]
    state["messages"] = messages

    last_error = None
    for model in models:
        try:
            print(f"[LLM] Using model: {model}")
            agent = get_agent(model)
            result = agent.invoke(state)

            for message in reversed(result["messages"]):
                if not isinstance(message, AIMessage):
                    continue
                if hasattr(message, "tool_calls") and message.tool_calls and not message.content:
                    continue
                text = extract_text(message)
                if text:
                    # Hard trim to 2 sentences — enforced regardless of model
                    text = trim_to_two_sentences(text)
                    return text, result

            print(f"[LLM] Model {model} returned empty text, trying next...")

        except Exception as e:
            err = str(e)
            if any(x in err for x in ["429", "rate_limit", "over capacity", "503"]):
                print(f"[LLM] Model {model} rate limited, trying next...")
            else:
                print(f"[LLM] Model {model} error: {err[:120]}, trying next...")
            last_error = e
            continue

    print(f"[LLM] All models failed. Last error: {last_error}")
    return "I'm really sorry, give me just a moment and try again!", state