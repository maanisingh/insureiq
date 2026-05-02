"""
RAG tools — search global knowledge base and user workspace documents.

Used by: RAGAgent
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "config" / ".env")


def search_global_knowledge(query: str, limit: int = 8) -> str:
    """Search the global insurance knowledge base (actuarial, underwriting, claims,
    fraud, regulations, policy types, mortality tables, loss data).

    Args:
        query: Natural language search query.
        limit: Number of results to return (default 8).

    Returns:
        Formatted string with numbered search results and source citations.
    """
    try:
        from qdrant_client import QdrantClient
        from app.core.bedrock import embed_query

        vector = embed_query(query)
        qdrant  = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
        )
        results = qdrant.query_points(
            collection_name="insurance_global",
            query=vector,
            limit=limit,
        ).points

        if not results:
            return f"No results found in global knowledge base for: '{query}'"

        lines = [f"## Global Knowledge Results for: '{query}'\n"]
        for i, r in enumerate(results, 1):
            source   = r.payload.get("source", "knowledge_base")
            doc_type = r.payload.get("type", "unknown")
            text     = r.payload.get("text", "")[:800]
            score    = round(r.score, 3)
            lines.append(f"**[{i}] Score: {score} | Source: {source} | Type: {doc_type}**")
            lines.append(text)
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Global search error: {e}"


def search_workspace_documents(query: str, workspace_id: str, limit: int = 8) -> str:
    """Search documents uploaded to the user's private workspace
    (policies, contracts, reports, claims, any uploaded files).

    Args:
        query:        Natural language search query.
        workspace_id: The user's workspace UUID.
        limit:        Number of results (default 8).

    Returns:
        Formatted string with results from the user's own documents.
    """
    try:
        from qdrant_client import QdrantClient
        from app.core.bedrock import embed_query

        collection = f"workspace_{workspace_id}"
        qdrant      = QdrantClient(
            host=os.getenv("QDRANT_WORKSPACE_HOST", "localhost"),
            port=int(os.getenv("QDRANT_WORKSPACE_PORT", "7333")),
        )
        cols = {c.name for c in qdrant.get_collections().collections}
        if collection not in cols:
            return "No documents have been uploaded to this workspace yet."

        vector  = embed_query(query)
        results = qdrant.query_points(
            collection_name=collection,
            query=vector,
            limit=limit,
        ).points

        if not results:
            return f"No matching documents found in workspace for: '{query}'"

        lines = [f"## Workspace Document Results for: '{query}'\n"]
        for i, r in enumerate(results, 1):
            meta     = r.payload.get("metadata", {})
            filename = meta.get("filename", "unknown file")
            score    = round(r.score, 3)
            text     = r.payload.get("text", "")[:800]
            lines.append(f"**[{i}] Score: {score} | File: {filename}**")
            lines.append(text)
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Workspace search error: {e}"


def list_workspace_policies(workspace_id: str) -> str:
    """List all insurance policies stored in the user's workspace.

    Args:
        workspace_id: The user's workspace UUID.

    Returns:
        Formatted list of policies with policy numbers, types, and status.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5433"),
            database=os.getenv("DB_NAME", "insurance_ai"),
            user=os.getenv("DB_USER", "insurance_ai"),
            password=os.getenv("DB_PASSWORD", "insurance_secure_2024"),
        )
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, policy_number, policy_type, status, policy_data, created_at
            FROM policies WHERE workspace_id = %s ORDER BY created_at DESC
            """,
            (workspace_id,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return "No policies found in this workspace."

        lines = [f"## Policies in Workspace\n"]
        for row in rows:
            pid, pnum, ptype, status, pdata, created = row
            lines.append(f"**{pnum}** | Type: {ptype} | Status: {status} | Created: {str(created)[:10]}")
            if pdata:
                # Show key fields from policy_data
                for k, v in list(pdata.items())[:5]:
                    lines.append(f"  {k}: {v}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Policy list error: {e}"


def get_policy_details(policy_number: str, workspace_id: str) -> str:
    """Get the full details of a specific insurance policy.

    Args:
        policy_number: The policy number (e.g. POL-XXXXXXXX).
        workspace_id:  The user's workspace UUID.

    Returns:
        Full policy details as formatted text.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5433"),
            database=os.getenv("DB_NAME", "insurance_ai"),
            user=os.getenv("DB_USER", "insurance_ai"),
            password=os.getenv("DB_PASSWORD", "insurance_secure_2024"),
        )
        cur = conn.cursor()
        cur.execute(
            """
            SELECT policy_number, policy_type, status, policy_data, created_at, updated_at
            FROM policies WHERE policy_number = %s AND workspace_id = %s
            """,
            (policy_number, workspace_id),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return f"Policy {policy_number} not found."

        pnum, ptype, status, pdata, created, updated = row
        lines = [
            f"## Policy: {pnum}",
            f"Type: {ptype}",
            f"Status: {status}",
            f"Created: {str(created)[:10]}",
            f"Last Updated: {str(updated)[:10]}",
            "",
            "### Policy Data:",
        ]
        if pdata:
            for k, v in pdata.items():
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)
    except Exception as e:
        return f"Policy detail error: {e}"


def list_uploaded_documents(workspace_id: str) -> str:
    """List all documents uploaded to the workspace with their extraction status.

    Args:
        workspace_id: The user's workspace UUID.

    Returns:
        List of uploaded documents with status, chunk counts, and file types.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5433"),
            database=os.getenv("DB_NAME", "insurance_ai"),
            user=os.getenv("DB_USER", "insurance_ai"),
            password=os.getenv("DB_PASSWORD", "insurance_secure_2024"),
        )
        cur = conn.cursor()
        cur.execute(
            """
            SELECT original_filename, file_type, file_size, extraction_status,
                   chunk_count, uploaded_at, indexed_at
            FROM uploads WHERE workspace_id = %s ORDER BY uploaded_at DESC
            """,
            (workspace_id,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return "No documents uploaded to this workspace."

        lines = ["## Uploaded Documents\n"]
        for fn, ftype, fsize, status, chunks, uploaded, indexed in rows:
            size_kb = round(fsize / 1024, 1) if fsize else 0
            lines.append(
                f"**{fn}** | {ftype.upper()} | {size_kb} KB | "
                f"Status: {status} | Chunks: {chunks} | Uploaded: {str(uploaded)[:10]}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Document list error: {e}"
