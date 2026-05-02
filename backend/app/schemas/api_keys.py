"""Pydantic schemas for API key endpoints."""

from typing import Optional
from pydantic import BaseModel


class ApiKeyCreate(BaseModel):
    name: str


class ApiKeyResponse(BaseModel):
    id:           str
    name:         str
    key_prefix:   str
    is_active:    bool
    created_at:   str
    last_used_at: Optional[str] = None


class ApiKeyCreated(ApiKeyResponse):
    """Returned only on POST — raw key never shown again."""
    raw_key: str
