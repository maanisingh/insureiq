"""Pydantic schemas for chat endpoints."""

from typing import Optional, List
from pydantic import BaseModel


class ChatMessage(BaseModel):
    workspace_id:     str
    session_id:       str = None
    message:          str
    # Optional: force a specific agent ("RAGAgent", "PricingAgent", etc.)
    # None means auto-route via the SelectorGroupChat
    preferred_agent:  Optional[str] = None
    # Optional: which knowledge sources to enable.
    # Supported values: "rag", "workspace", "web", "regulations", "huggingface"
    # None or empty list means all sources enabled
    enabled_sources:  Optional[List[str]] = None


class ChatResponse(BaseModel):
    session_id:  str
    response:    str
    sources:     list = []
    agent_used:  Optional[str] = None
