"""
Generated documents router — list, retrieve, and delete AI-generated documents.

Documents are created by:
  PolicyAgent      → generate_policy_document()
  UnderwritingAgent→ generate_underwriting_memo()

Both save via app.core.doc_indexer.save_and_index_doc() which persists the
full text to PostgreSQL and indexes chunks into workspace Qdrant (:7333).

Endpoints:
  GET    /gen-docs?workspace_id=       list (summary, no content)
  GET    /gen-docs/{id}?workspace_id=  full document including content
  DELETE /gen-docs/{id}?workspace_id=  delete DB row + Qdrant vectors
"""

import os
from fastapi import APIRouter, Depends, HTTPException, status

from app.routers.auth import get_current_user
from app.database import get_db_connection

router = APIRouter()


def _verify_workspace(workspace_id: str, user_id: str, cur) -> None:
    cur.execute(
        "SELECT id FROM workspaces WHERE id = %s AND user_id = %s",
        (workspace_id, user_id),
    )
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Workspace not found")


@router.get("")
def list_generated_docs(
    workspace_id: str,
    doc_type:     str | None = None,
    limit:        int        = 50,
    current_user: dict       = Depends(get_current_user),
):
    """List generated documents for a workspace.

    Returns summaries only (no content field) for fast listing.
    Filter by doc_type: 'policy_document' | 'underwriting_memo'
    """
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        _verify_workspace(workspace_id, current_user["id"], cur)

        if doc_type:
            cur.execute(
                """
                SELECT id, title, doc_type, word_count, indexed_at, created_at
                FROM generated_documents
                WHERE workspace_id = %s AND doc_type = %s
                ORDER BY created_at DESC LIMIT %s
                """,
                (workspace_id, doc_type, limit),
            )
        else:
            cur.execute(
                """
                SELECT id, title, doc_type, word_count, indexed_at, created_at
                FROM generated_documents
                WHERE workspace_id = %s
                ORDER BY created_at DESC LIMIT %s
                """,
                (workspace_id, limit),
            )

        return [
            {
                "id":         str(r[0]),
                "title":      r[1],
                "doc_type":   r[2],
                "word_count": r[3] or 0,
                "indexed_at": str(r[4]) if r[4] else None,
                "created_at": str(r[5]),
            }
            for r in cur.fetchall()
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/{doc_id}")
def get_generated_doc(
    doc_id:       str,
    workspace_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a single generated document including full content."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        _verify_workspace(workspace_id, current_user["id"], cur)

        cur.execute(
            """
            SELECT id, title, doc_type, content, word_count, metadata,
                   indexed_at, created_at
            FROM generated_documents
            WHERE id = %s AND workspace_id = %s
            """,
            (doc_id, workspace_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        return {
            "id":         str(row[0]),
            "title":      row[1],
            "doc_type":   row[2],
            "content":    row[3],
            "word_count": row[4] or 0,
            "metadata":   row[5] or {},
            "indexed_at": str(row[6]) if row[6] else None,
            "created_at": str(row[7]),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_generated_doc(
    doc_id:       str,
    workspace_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a generated document from the DB and its Qdrant vectors."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        _verify_workspace(workspace_id, current_user["id"], cur)

        cur.execute(
            "SELECT id FROM generated_documents WHERE id = %s AND workspace_id = %s",
            (doc_id, workspace_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Document not found")

        # Remove Qdrant vectors tagged with this doc_id
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            qdrant = QdrantClient(
                host=os.getenv("QDRANT_WORKSPACE_HOST", "localhost"),
                port=int(os.getenv("QDRANT_WORKSPACE_PORT", "7333")),
            )
            collection = f"workspace_{workspace_id}"
            cols = {c.name for c in qdrant.get_collections().collections}
            if collection in cols:
                qdrant.delete(
                    collection_name=collection,
                    points_selector=Filter(
                        must=[FieldCondition(
                            key="metadata.doc_id",
                            match=MatchValue(value=doc_id),
                        )]
                    ),
                )
        except Exception:
            pass  # Don't block deletion if Qdrant is unavailable

        cur.execute(
            "DELETE FROM generated_documents WHERE id = %s AND workspace_id = %s",
            (doc_id, workspace_id),
        )
        conn.commit()

        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Document not found")

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
