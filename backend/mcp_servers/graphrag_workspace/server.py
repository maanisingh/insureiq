"""
graphrag_workspace MCP server — Per-workspace knowledge (Layer 2).

Each workspace has its own Qdrant collection: workspace_{workspace_id}.
Uses Bedrock Titan for both indexing and query embeddings.
"""

import os
import sys
import json
import uuid
import boto3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "config" / ".env")

try:
    from fastmcp import FastMCP
except ImportError:
    from mcp import FastMCP

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

mcp = FastMCP("graphrag-workspace")

QDRANT_WORKSPACE_HOST = os.getenv("QDRANT_WORKSPACE_HOST", "localhost")
QDRANT_WORKSPACE_PORT = int(os.getenv("QDRANT_WORKSPACE_PORT", "7333"))
EMBED_MODEL           = "amazon.titan-embed-text-v1"
AWS_REGION            = os.getenv("AWS_REGION", "us-east-1")
AWS_KEY               = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET            = os.getenv("AWS_SECRET_ACCESS_KEY")

qdrant_workspace = QdrantClient(host=QDRANT_WORKSPACE_HOST, port=QDRANT_WORKSPACE_PORT)


def _bedrock():
    kwargs = {"region_name": AWS_REGION}
    if AWS_KEY and AWS_SECRET:
        kwargs["aws_access_key_id"]     = AWS_KEY
        kwargs["aws_secret_access_key"] = AWS_SECRET
    return boto3.client("bedrock-runtime", **kwargs)


def _embed(text: str) -> list[float]:
    client = _bedrock()
    resp = client.invoke_model(
        modelId=EMBED_MODEL,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text[:8000]}),
    )
    return json.loads(resp["body"].read())["embedding"]


def _collection_name(workspace_id: str) -> str:
    return f"workspace_{workspace_id}"


def _ensure_collection(workspace_id: str) -> str:
    name = _collection_name(workspace_id)
    collections = {c.name for c in qdrant_workspace.get_collections().collections}
    if name not in collections:
        qdrant_workspace.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
        )
    return name


@mcp.tool()
def search_workspace_knowledge(workspace_id: str, query: str, limit: int = 10) -> list[dict]:
    """Search workspace-specific knowledge (Layer 2).

    Use this for questions about the user's own policies, uploaded documents,
    and workspace-specific data.

    Args:
        workspace_id: Workspace UUID.
        query:        Natural language search query.
        limit:        Maximum number of results (default: 10).
    """
    collection_name = _collection_name(workspace_id)
    try:
        vector = _embed(query)
        results = qdrant_workspace.search(
            collection_name=collection_name,
            query_vector=vector,
            limit=limit,
        )
        return [
            {
                "id":       str(r.id),
                "score":    round(r.score, 4),
                "text":     r.payload.get("text", "")[:1000],
                "type":     r.payload.get("type", "unknown"),
                "metadata": r.payload.get("metadata", {}),
                "layer":    "workspace",
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": str(e), "results": []}]


@mcp.tool()
def index_document_to_workspace(
    workspace_id: str,
    text: str,
    doc_type: str,
    metadata: dict = None,
) -> dict:
    """Index a document chunk into the workspace knowledge base.

    Uses Bedrock Titan to generate a real 1536-dim embedding.

    Args:
        workspace_id: Workspace UUID.
        text:         Text content to index.
        doc_type:     Type of document (policy, upload, note, chat).
        metadata:     Optional metadata dict (upload_id, filename, etc.).
    """
    collection_name = _ensure_collection(workspace_id)
    vector          = _embed(text)
    point_id        = str(uuid.uuid4())

    qdrant_workspace.upsert(
        collection_name=collection_name,
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "text":     text[:5000],
                    "type":     doc_type,
                    "metadata": metadata or {},
                },
            )
        ],
    )
    return {"status": "indexed", "point_id": point_id, "workspace_id": workspace_id}


@mcp.tool()
def delete_points_by_upload(workspace_id: str, upload_id: str) -> dict:
    """Delete all Qdrant points associated with a specific upload.

    Args:
        workspace_id: Workspace UUID.
        upload_id:    Upload UUID to remove from the vector store.
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    collection_name = _collection_name(workspace_id)
    try:
        qdrant_workspace.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="metadata.upload_id", match=MatchValue(value=upload_id))]
            ),
        )
        return {"status": "deleted", "upload_id": upload_id, "workspace_id": workspace_id}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
def get_workspace_stats(workspace_id: str) -> dict:
    """Get statistics about a workspace's vector collection.

    Args:
        workspace_id: Workspace UUID.
    """
    collection_name = _collection_name(workspace_id)
    try:
        info = qdrant_workspace.get_collection(collection_name)
        return {
            "workspace_id":  workspace_id,
            "vectors_count": info.vectors_count,
            "points_count":  info.points_count,
            "status":        str(info.status),
        }
    except Exception:
        return {"workspace_id": workspace_id, "vectors_count": 0, "points_count": 0, "status": "empty"}


@mcp.tool()
def delete_workspace_data(workspace_id: str) -> dict:
    """Delete the entire workspace collection from Qdrant.

    Args:
        workspace_id: Workspace UUID.
    """
    collection_name = _collection_name(workspace_id)
    try:
        qdrant_workspace.delete_collection(collection_name)
        return {"status": "deleted", "workspace_id": workspace_id}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
def health_check() -> dict:
    """Health check for the graphrag-workspace MCP server."""
    try:
        qdrant_workspace.get_collections()
        return {"status": "healthy", "qdrant_workspace": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    transport = "stdio"
    port = 8002
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        transport = "http"
        port = int(sys.argv[2]) if len(sys.argv) > 2 else port
    mcp.run(transport=transport, port=port) if transport == "http" else mcp.run(transport="stdio")
