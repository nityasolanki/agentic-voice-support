"""In-process session store for active call context (replaced by Redis in prod)."""
from __future__ import annotations
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SessionState:
    session_id: str
    customer_id: int | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    verified: bool = False
    current_order_id: int | None = None
    current_ticket_id: int | None = None
    messages: list[dict] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_active: datetime = field(default_factory=datetime.utcnow)

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        self.last_active = datetime.utcnow()

    def to_langchain_messages(self) -> list[dict]:
        return [{"role": m["role"], "content": m["content"]} for m in self.messages[-20:]]


class SessionStore:
    """Thread-safe in-memory session store."""

    def __init__(self):
        self._sessions: dict[str, SessionState] = {}
        self._lock = threading.Lock()

    def create(self, session_id: str) -> SessionState:
        with self._lock:
            state = SessionState(session_id=session_id)
            self._sessions[session_id] = state
            return state

    def get(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str) -> SessionState:
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
            return self._sessions[session_id]

    def delete(self, session_id: str):
        with self._lock:
            self._sessions.pop(session_id, None)

    def active_sessions(self) -> list[str]:
        return list(self._sessions.keys())


# Singleton
session_store = SessionStore()
