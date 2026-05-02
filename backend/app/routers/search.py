"""
Search router — semantic search across global and workspace knowledge.
Uses Bedrock Titan embeddings for query vectors.
"""

import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.auth import get_current_user
from app.database import get_db_connection
from app.core.bedrock import embed_query

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    workspace_id: str = None
    limit: int = 10


class SearchResult(BaseModel):
    global_results:    list = []
    workspace_results: list = []


def _qdrant_global():
    from qdrant_client import QdrantClient
    return QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )


def _qdrant_workspace():
    from qdrant_client import QdrantClient
    return QdrantClient(
        host=os.getenv("QDRANT_WORKSPACE_HOST", "localhost"),
        port=int(os.getenv("QDRANT_WORKSPACE_PORT", "7333")),
    )


@router.post("", response_model=SearchResult)
def search(request: SearchRequest, current_user: dict = Depends(get_current_user)):
    """Search both global and workspace knowledge bases."""
    global_results    = []
    workspace_results = []

    try:
        vector  = embed_query(request.query)
        qdrant  = _qdrant_global()
        layer1  = qdrant.query_points(
            collection_name="insurance_global",
            query=vector,
            limit=request.limit,
        ).points
        global_results = [
            {
                "id":     str(r.id),
                "score":  round(r.score, 4),
                "text":   r.payload.get("text", "")[:300],
                "source": r.payload.get("source", "unknown"),
                "type":   r.payload.get("type", "unknown"),
                "layer":  "global",
            }
            for r in layer1
        ]
    except Exception as e:
        global_results = [{"error": str(e)}]

    if request.workspace_id:
        conn = get_db_connection()
        cur  = conn.cursor()
        try:
            cur.execute(
                "SELECT id FROM workspaces WHERE id = %s AND user_id = %s",
                (request.workspace_id, current_user["id"]),
            )
            if cur.fetchone():
                collection = f"workspace_{request.workspace_id}"
                try:
                    qdrant_ws = _qdrant_workspace()
                    layer2    = qdrant_ws.query_points(
                        collection_name=collection,
                        query=vector,
                        limit=request.limit,
                    ).points
                    workspace_results = [
                        {
                            "id":    str(r.id),
                            "score": round(r.score, 4),
                            "text":  r.payload.get("text", "")[:300],
                            "type":  r.payload.get("type", "unknown"),
                            "layer": "workspace",
                        }
                        for r in layer2
                    ]
                except Exception:
                    workspace_results = []
        except Exception:
            pass
        finally:
            cur.close()
            conn.close()

    return SearchResult(global_results=global_results, workspace_results=workspace_results)


@router.get("/global")
def search_global(
    query: str,
    limit: int = 10,
    current_user: dict = Depends(get_current_user),
):
    """Search global knowledge only."""
    try:
        vector  = embed_query(query)
        qdrant  = _qdrant_global()
        results = qdrant.query_points(
            collection_name="insurance_global",
            query=vector,
            limit=limit,
        ).points
        return {
            "query":   query,
            "results": [
                {
                    "id":     str(r.id),
                    "score":  round(r.score, 4),
                    "text":   r.payload.get("text", "")[:500],
                    "source": r.payload.get("source", "unknown"),
                    "type":   r.payload.get("type", "unknown"),
                }
                for r in results
            ],
        }
    except Exception as e:
        return {"query": query, "error": str(e), "results": []}


@router.get("/workspace/{workspace_id}")
def search_workspace(
    workspace_id: str,
    query: str,
    limit: int = 10,
    current_user: dict = Depends(get_current_user),
):
    """Search workspace knowledge only."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM workspaces WHERE id = %s AND user_id = %s",
            (workspace_id, current_user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")

        collection = f"workspace_{workspace_id}"
        try:
            vector    = embed_query(query)
            qdrant_ws = _qdrant_workspace()
            results   = qdrant_ws.query_points(
                collection_name=collection,
                query=vector,
                limit=limit,
            ).points
            return {
                "query":        query,
                "workspace_id": workspace_id,
                "results": [
                    {
                        "id":    str(r.id),
                        "score": round(r.score, 4),
                        "text":  r.payload.get("text", "")[:500],
                        "type":  r.payload.get("type", "unknown"),
                    }
                    for r in results
                ],
            }
        except Exception as e:
            return {"query": query, "workspace_id": workspace_id, "error": str(e), "results": []}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
