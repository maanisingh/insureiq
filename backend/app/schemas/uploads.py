"""Pydantic schemas for upload endpoints."""

from typing import Optional
from pydantic import BaseModel


class UploadResponse(BaseModel):
    id:                str
    workspace_id:      str
    filename:          str
    original_filename: Optional[str] = None
    file_type:         str
    file_size:         int
    extraction_status: str
    chunk_count:       int = 0
    uploaded_at:       str
    indexed_at:        Optional[str] = None


class UploadListItem(BaseModel):
    id:                str
    filename:          str
    original_filename: Optional[str] = None
    file_type:         str
    file_size:         int
    extraction_status: str
    chunk_count:       int = 0
    uploaded_at:       str
