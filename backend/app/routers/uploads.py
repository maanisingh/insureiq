"""
Uploads router — file upload, listing, detail, and deletion.

Flow:
  POST /uploads
    → save file to disk
    → create uploads row (status=pending)
    → trigger BackgroundTask: extract → chunk → embed → index → update status

  GET  /uploads?workspace_id=
    → list uploads for workspace

  GET  /uploads/{id}
    → single upload detail (includes extraction_status, chunk_count)

  DELETE /uploads/{id}
    → delete file from disk
    → remove Qdrant vectors (metadata.upload_id filter)
    → delete uploads row
"""

import os
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, status

from app.routers.auth import get_current_user
from app.database import get_db_connection
from app.schemas.uploads import UploadResponse, UploadListItem
from app.core.extractor import SUPPORTED_EXTENSIONS

router = APIRouter()

UPLOAD_DIR = Path(__file__).parent.parent.parent / "storage" / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


# ── Background task ───────────────────────────────────────────────────────────

def _process_upload(upload_id: str, workspace_id: str, file_path: str, filename: str) -> None:
    """Extract, chunk, embed, and index an uploaded document.

    Runs in a BackgroundTask after the upload endpoint returns.
    Updates the uploads row with status, chunk_count, and indexed_at.
    """
    conn = get_db_connection()
    cur  = conn.cursor()

    def _set_status(status_val: str, error: str = None, chunk_count: int = 0) -> None:
        try:
            cur.execute(
                """
                UPDATE uploads
                SET extraction_status = %s,
                    error_message     = %s,
                    chunk_count       = %s,
                    indexed_at        = CASE WHEN %s = 'done' THEN NOW() ELSE NULL END
                WHERE id = %s
                """,
                (status_val, error, chunk_count, status_val, upload_id),
            )
            conn.commit()
        except Exception:
            pass

    try:
        _set_status("processing")

        # 1. Read file
        file_bytes = Path(file_path).read_bytes()

        # 2. Extract text via Bedrock
        from app.core.extractor import extract as extract_text
        extracted = extract_text(file_bytes, filename)

        # Persist extracted text
        cur.execute(
            "UPDATE uploads SET extracted_text = %s WHERE id = %s",
            (extracted[:100_000], upload_id),  # cap at 100K chars in DB
        )
        conn.commit()

        # 3. Chunk text
        from app.core.chunker import chunk_text
        chunks = chunk_text(extracted, upload_id, workspace_id, filename)

        if not chunks:
            _set_status("done", chunk_count=0)
            return

        # 4. Embed each chunk with Bedrock Titan and upsert to workspace Qdrant
        from app.core.bedrock import embed_query
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams, PointStruct

        qdrant          = QdrantClient(
            host=os.getenv("QDRANT_WORKSPACE_HOST", "localhost"),
            port=int(os.getenv("QDRANT_WORKSPACE_PORT", "7333")),
        )
        collection_name = f"workspace_{workspace_id}"
        existing_cols   = {c.name for c in qdrant.get_collections().collections}
        if collection_name not in existing_cols:
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
                        "text":     chunk["text"][:5000],
                        "type":     "upload",
                        "metadata": chunk["metadata"],
                    },
                ))
            except Exception:
                continue  # skip chunks that fail to embed

        if points:
            # Upsert in batches of 50
            for i in range(0, len(points), 50):
                qdrant.upsert(collection_name=collection_name, points=points[i:i + 50])

        _set_status("done", chunk_count=len(points))

    except Exception as e:
        _set_status("failed", error=str(e)[:500])
    finally:
        cur.close()
        conn.close()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    background_tasks: BackgroundTasks,
    workspace_id:     str         = Form(...),
    file:             UploadFile  = File(...),
    current_user:     dict        = Depends(get_current_user),
):
    """Upload a document (PDF, DOCX, TXT, CSV, Excel).

    Returns immediately. Extraction and indexing run in the background.
    Poll GET /uploads/{id} to check extraction_status.
    """
    # Validate workspace ownership
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM workspaces WHERE id = %s AND user_id = %s",
            (workspace_id, current_user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")
    finally:
        cur.close()
        conn.close()

    # Validate extension
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    # Read file (enforce size limit)
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File exceeds 50 MB limit")

    # Save to disk
    upload_id      = str(uuid.uuid4())
    ws_dir         = UPLOAD_DIR / workspace_id
    ws_dir.mkdir(parents=True, exist_ok=True)
    safe_name      = f"{upload_id}{suffix}"
    file_path      = ws_dir / safe_name

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(file_bytes)

    # Persist uploads row
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO uploads
              (id, workspace_id, filename, original_filename, file_path, file_type, file_size, extraction_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
            RETURNING id, workspace_id, filename, original_filename, file_type, file_size,
                      extraction_status, chunk_count, uploaded_at, indexed_at
            """,
            (
                upload_id, workspace_id, safe_name, file.filename,
                str(file_path), suffix.lstrip("."), len(file_bytes),
            ),
        )
        row = cur.fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

    # Kick off background extraction
    background_tasks.add_task(
        _process_upload,
        upload_id=upload_id,
        workspace_id=workspace_id,
        file_path=str(file_path),
        filename=file.filename or safe_name,
    )

    return UploadResponse(
        id=str(row[0]),
        workspace_id=str(row[1]),
        filename=row[2],
        original_filename=row[3],
        file_type=row[4],
        file_size=row[5],
        extraction_status=row[6],
        chunk_count=row[7] or 0,
        uploaded_at=str(row[8]),
        indexed_at=str(row[9]) if row[9] else None,
    )


@router.get("", response_model=list[UploadListItem])
def list_uploads(
    workspace_id: str,
    current_user: dict = Depends(get_current_user),
):
    """List all uploads for a workspace."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM workspaces WHERE id = %s AND user_id = %s",
            (workspace_id, current_user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")

        cur.execute(
            """
            SELECT id, filename, original_filename, file_type, file_size,
                   extraction_status, chunk_count, uploaded_at
            FROM uploads WHERE workspace_id = %s
            ORDER BY uploaded_at DESC
            """,
            (workspace_id,),
        )
        return [
            UploadListItem(
                id=str(r[0]), filename=r[1], original_filename=r[2],
                file_type=r[3], file_size=r[4], extraction_status=r[5],
                chunk_count=r[6] or 0, uploaded_at=str(r[7]),
            )
            for r in cur.fetchall()
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/{upload_id}", response_model=UploadResponse)
def get_upload(
    upload_id:    str,
    workspace_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a single upload including extraction status and indexed_at."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM workspaces WHERE id = %s AND user_id = %s",
            (workspace_id, current_user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")

        cur.execute(
            """
            SELECT id, workspace_id, filename, original_filename, file_type, file_size,
                   extraction_status, chunk_count, uploaded_at, indexed_at
            FROM uploads WHERE id = %s AND workspace_id = %s
            """,
            (upload_id, workspace_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Upload not found")

        return UploadResponse(
            id=str(row[0]), workspace_id=str(row[1]),
            filename=row[2], original_filename=row[3],
            file_type=row[4], file_size=row[5],
            extraction_status=row[6], chunk_count=row[7] or 0,
            uploaded_at=str(row[8]), indexed_at=str(row[9]) if row[9] else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_upload(
    upload_id:    str,
    workspace_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete an upload: removes file from disk, Qdrant vectors, and DB row."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM workspaces WHERE id = %s AND user_id = %s",
            (workspace_id, current_user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Workspace not found")

        cur.execute(
            "SELECT file_path FROM uploads WHERE id = %s AND workspace_id = %s",
            (upload_id, workspace_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Upload not found")

        file_path = row[0]

        # Remove from Qdrant workspace collection
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
                            key="metadata.upload_id",
                            match=MatchValue(value=upload_id),
                        )]
                    ),
                )
        except Exception:
            pass  # Don't block deletion if Qdrant fails

        # Remove file from disk
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass

        # Delete DB row
        cur.execute("DELETE FROM uploads WHERE id = %s", (upload_id,))
        conn.commit()

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
