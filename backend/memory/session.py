"""
Session-scoped conversation memory.
Stores the turn-by-turn conversation history for the current call.
"""
from dataclasses import dataclass, field
from typing import Optional
import uuid


@dataclass
class ConversationTurn:
    role: str  # "user" | "assistant" | "system"
    content: str
    agent: Optional[str] = None  # which agent produced this turn


@dataclass
class CustomerSession:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    is_verified: bool = False
    turns: list[ConversationTurn] = field(default_factory=list)
    current_order_id: Optional[str] = None
    current_ticket_id: Optional[str] = None
    escalated: bool = False

    def add_turn(self, role: str, content: str, agent: Optional[str] = None):
        self.turns.append(ConversationTurn(role=role, content=content, agent=agent))

    def get_history(self) -> list[dict]:
        """Return history in LangChain/Ollama message format."""
        return [{"role": t.role, "content": t.content} for t in self.turns]

    def get_recent_history(self, n: int = 10) -> list[dict]:
        return self.get_history()[-n:]

    def summary(self) -> str:
        """One-line session summary for logging."""
        return (
            f"Session {self.session_id[:8]} | "
            f"Customer: {self.customer_name or 'unverified'} | "
            f"Turns: {len(self.turns)} | "
            f"Escalated: {self.escalated}"
        )


# Simple in-process session store (replace with Redis for production)
_sessions: dict[str, CustomerSession] = {}


def create_session() -> CustomerSession:
    session = CustomerSession()
    _sessions[session.session_id] = session
    return session


def get_session(session_id: str) -> Optional[CustomerSession]:
    return _sessions.get(session_id)


def close_session(session_id: str):
    _sessions.pop(session_id, None)
