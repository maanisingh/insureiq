"""Pydantic schemas for workspace endpoints."""

from typing import Optional
from pydantic import BaseModel


class CreateWorkspaceRequest(BaseModel):
    name:        str
    description: Optional[str] = None


class WorkspaceResponse(BaseModel):
    id:          str
    name:        str
    description: Optional[str] = None
    created_at:  str
