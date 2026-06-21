"""Pydantic request/response schemas for the API."""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    response: str
    customer_verified: bool = False
    customer_name: str | None = None
    actions_taken: list[str] = Field(default_factory=list)


class VoiceResponse(BaseModel):
    session_id: str
    transcript: str
    response_text: str


class OutboundCallRequest(BaseModel):
    customer_id: int
    reason: str
    order_number: str | None = None
    ticket_number: str | None = None


class SessionSummary(BaseModel):
    session_id: str
    customer_name: str | None
    verified: bool
    message_count: int
