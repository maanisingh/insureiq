"""Pydantic schemas for search endpoints."""

from pydantic import BaseModel


class SearchRequest(BaseModel):
    query:        str
    workspace_id: str = None
    limit:        int = 10


class SearchResult(BaseModel):
    global_results:    list = []
    workspace_results: list = []
