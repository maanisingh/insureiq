"""
qdrant_vector MCP server — Generic dual-Qdrant search interface.

Provides unified search across global (:6333) and workspace (:7333) Qdrant instances
using Bedrock Titan embeddings.
"""

import os
import sys
import json
import boto3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "config" / ".env")

try:
    from fastmcp import FastMCP
except ImportError:
    from mcp import FastMCP

from qdrant_client import QdrantClient

mcp = FastMCP("qdrant-vector")

QDRANT_HOST           = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT           = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_WORKSPACE_HOST = os.getenv("QDRANT_WORKSPACE_HOST", "localhost")
QDRANT_WORKSPACE_PORT = int(os.getenv("QDRANT_WORKSPACE_PORT", "7333"))
EMBED_MODEL           = "amazon.titan-embed-text-v1"
AWS_REGION            = os.getenv("AWS_REGION", "us-east-1")
AWS_KEY               = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET            = os.getenv("AWS_SECRET_ACCESS_KEY")

qdrant_global    = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
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


@mcp.tool()
def search_vector_db(
    query: str,
    collection: str = "insurance_global",
    limit: int = 10,
    use_workspace: bool = False,
) -> list[dict]:
    """Search a Qdrant collection by semantic query.

    Args:
        query:         Natural language search query.
        collection:    Collection name (default: insurance_global).
        limit:         Number of results (default: 10).
        use_workspace: If True, search workspace Qdrant (:7333) instead of global (:6333).
    """
    client = qdrant_workspace if use_workspace else qdrant_global
    try:
        vector  = _embed(query)
        results = client.search(
            collection_name=collection,
            query_vector=vector,
            limit=limit,
        )
        return [
            {
                "id":      str(r.id),
                "score":   round(r.score, 4),
                "text":    r.payload.get("text", "")[:500],
                "payload": r.payload,
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool()
def list_collections(use_workspace: bool = False) -> list[dict]:
    """List all collections in a Qdrant instance.

    Args:
        use_workspace: If True, list from workspace instance.
    """
    client = qdrant_workspace if use_workspace else qdrant_global
    try:
        return [{"name": c.name} for c in client.get_collections().collections]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool()
def get_collection_info(collection: str, use_workspace: bool = False) -> dict:
    """Get collection metadata and vector count.

    Args:
        collection:    Collection name.
        use_workspace: If True, query workspace instance.
    """
    client = qdrant_workspace if use_workspace else qdrant_global
    try:
        info = client.get_collection(collection)
        return {
            "name":          collection,
            "vectors_count": info.vectors_count,
            "points_count":  info.points_count,
            "status":        str(info.status),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def health_check() -> dict:
    """Health check for both Qdrant instances."""
    results = {}
    try:
        g = qdrant_global.get_collections().collections
        results["global"] = {"status": "ok", "collections": len(g)}
    except Exception as e:
        results["global"] = {"status": "error", "error": str(e)}
    try:
        w = qdrant_workspace.get_collections().collections
        results["workspace"] = {"status": "ok", "collections": len(w)}
    except Exception as e:
        results["workspace"] = {"status": "error", "error": str(e)}

    overall = "healthy" if all(v.get("status") == "ok" for v in results.values()) else "degraded"
    return {"status": overall, **results}


if __name__ == "__main__":
    transport = "stdio"
    port = 8007
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        transport = "http"
        port = int(sys.argv[2]) if len(sys.argv) > 2 else port
    mcp.run(transport=transport, port=port) if transport == "http" else mcp.run(transport="stdio")
