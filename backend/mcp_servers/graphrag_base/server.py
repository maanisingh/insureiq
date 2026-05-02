"""
graphrag_base MCP server — Global insurance knowledge (Layer 1).

Searches the insurance_global Qdrant collection using Bedrock Titan embeddings.
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
from qdrant_client.models import Distance, VectorParams

mcp = FastMCP("graphrag-base")

QDRANT_HOST     = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT     = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = "insurance_global"
EMBED_MODEL     = "amazon.titan-embed-text-v1"
AWS_REGION      = os.getenv("AWS_REGION", "us-east-1")
AWS_KEY         = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET      = os.getenv("AWS_SECRET_ACCESS_KEY")

qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


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


def _ensure_collection():
    collections = {c.name for c in qdrant_client.get_collections().collections}
    if COLLECTION_NAME not in collections:
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
        )


@mcp.tool()
def search_global_knowledge(query: str, limit: int = 10) -> list[dict]:
    """Search the global insurance knowledge base (Layer 1).

    Use this for general insurance questions, actuarial concepts,
    policy calculations, fraud patterns, and regulatory topics.

    Args:
        query: Natural language search query.
        limit: Maximum number of results (default: 10).
    """
    try:
        vector = _embed(query)
        results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=vector,
            limit=limit,
        )
        return [
            {
                "id":       str(r.id),
                "score":    round(r.score, 4),
                "text":     r.payload.get("text", "")[:1000],
                "title":    r.payload.get("title", ""),
                "source":   r.payload.get("source", "unknown"),
                "type":     r.payload.get("type", "unknown"),
                "metadata": r.payload.get("metadata", {}),
                "layer":    "global",
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": str(e), "results": []}]


@mcp.tool()
def get_knowledge_by_id(ids: list[str]) -> list[dict]:
    """Retrieve specific knowledge items by their Qdrant point IDs.

    Args:
        ids: List of point UUID strings.
    """
    try:
        results = qdrant_client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=ids,
        )
        return [
            {
                "id":     str(r.id),
                "text":   r.payload.get("text", ""),
                "title":  r.payload.get("title", ""),
                "source": r.payload.get("source", "unknown"),
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool()
def get_collection_stats() -> dict:
    """Get statistics about the global knowledge collection."""
    try:
        _ensure_collection()
        info = qdrant_client.get_collection(COLLECTION_NAME)
        return {
            "name":          COLLECTION_NAME,
            "vectors_count": info.vectors_count,
            "points_count":  info.points_count,
            "status":        str(info.status),
        }
    except Exception as e:
        return {"error": str(e), "status": "not_found"}


@mcp.tool()
def health_check() -> dict:
    """Health check for the graphrag-base MCP server."""
    try:
        qdrant_client.get_collections()
        return {"status": "healthy", "qdrant": "connected", "collection": COLLECTION_NAME}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    transport = "stdio"
    port = 8001
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        transport = "http"
        port = int(sys.argv[2]) if len(sys.argv) > 2 else port
    mcp.run(transport=transport, port=port) if transport == "http" else mcp.run(transport="stdio")
