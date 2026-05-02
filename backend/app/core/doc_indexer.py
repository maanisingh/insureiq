"""
doc_indexer.py — shared helper to persist AI-generated documents to PostgreSQL
and index them into the workspace Qdrant collection.

Called by:
  agents/tools/policy_tools.py        → generate_policy_document()
  agents/tools/underwriting_tools.py  → generate_underwriting_memo()

Design:
  - Saves document to generated_documents table first (always succeeds if DB is up)
  - Then chunks → embeds → upserts to Qdrant :7333 (same pipeline as uploads)
  - Sets indexed_at on success; silently continues if Qdrant fails
  - Never raises — tool functions must not crash due to indexing failures
  - Returns the new doc_id so callers can surface it if needed
"""

import os
import uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "config" / ".env")


def save_and_index_doc(
    workspace_id: str,
    content:      str,
    title:        str,
    doc_type:     str,
    metadata:     dict | None = None,
) -> str | None:
    """Persist a generated document and index it into the workspace RAG collection.

    Args:
        workspace_id: Workspace UUID — scopes the Qdrant collection.
        content:      Full document text.
        title:        Human-readable document title.
        doc_type:     'policy_document' | 'underwriting_memo'
        metadata:     Optional dict stored as JSONB (e.g. policy_number, decision).

    Returns:
        The new document UUID, or None if the DB insert failed.
    """
    if not content or not workspace_id:
        return None

    doc_id     = str(uuid.uuid4())
    word_count = len(content.split())
    meta       = metadata or {}

    # ── 1. Persist to PostgreSQL ─────────────────────────────────────────────
    try:
        import psycopg2, json as _json
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
            INSERT INTO generated_documents
              (id, workspace_id, title, doc_type, content, word_count, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (doc_id, workspace_id, title, doc_type,
             content, word_count, _json.dumps(meta)),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        # DB failure — can't proceed
        print(f"[doc_indexer] DB save failed: {e}")
        return None

    # ── 2. Chunk → embed → upsert to Qdrant workspace collection ────────────
    try:
        from app.core.chunker import chunk_text
        from app.core.bedrock import embed_query
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams, PointStruct

        chunks = chunk_text(content, doc_id, workspace_id, title)
        if not chunks:
            return doc_id

        qdrant          = QdrantClient(
            host=os.getenv("QDRANT_WORKSPACE_HOST", "localhost"),
            port=int(os.getenv("QDRANT_WORKSPACE_PORT", "7333")),
        )
        collection_name = f"workspace_{workspace_id}"
        existing        = {c.name for c in qdrant.get_collections().collections}
        if collection_name not in existing:
            qdrant.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )

        points = []
        for chunk in chunks:
            try:
                vector = embed_query(chunk["text"])
                points.append(PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "text":  chunk["text"][:5000],
                        "type":  "generated_doc",
                        "metadata": {
                            **chunk["metadata"],
                            "doc_id":   doc_id,
                            "doc_type": doc_type,
                            "title":    title,
                        },
                    },
                ))
            except Exception:
                continue

        if points:
            for i in range(0, len(points), 50):
                qdrant.upsert(collection_name=collection_name, points=points[i:i + 50])

        # Mark as indexed
        try:
            import psycopg2 as _pg
            conn2 = _pg.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=os.getenv("DB_PORT", "5433"),
                database=os.getenv("DB_NAME", "insurance_ai"),
                user=os.getenv("DB_USER", "insurance_ai"),
                password=os.getenv("DB_PASSWORD", "insurance_secure_2024"),
            )
            cur2 = conn2.cursor()
            cur2.execute(
                "UPDATE generated_documents SET indexed_at = NOW() WHERE id = %s",
                (doc_id,),
            )
            conn2.commit()
            cur2.close()
            conn2.close()
        except Exception:
            pass

    except Exception as e:
        print(f"[doc_indexer] Qdrant indexing failed (doc still saved): {e}")

    return doc_id
