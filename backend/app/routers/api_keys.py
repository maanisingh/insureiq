"""
API Keys router — generate, list, and revoke user API keys.

Keys are formatted as: ak_<32 random URL-safe chars>
Only the SHA-256 hash is stored. The raw key is returned once on creation.
Keys are accepted as Bearer tokens in Authorization headers (alongside JWT).
"""

import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, status

from app.routers.auth import get_current_user
from app.database import get_db_connection
from app.schemas.api_keys import ApiKeyCreate, ApiKeyResponse, ApiKeyCreated

router = APIRouter()


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
def create_api_key(request: ApiKeyCreate, current_user: dict = Depends(get_current_user)):
    """Generate a new API key. Returns the raw key once — store it securely."""
    raw_key    = f"ak_{secrets.token_urlsafe(32)}"
    key_hash   = _hash_key(raw_key)
    key_prefix = raw_key[:12] + "..."

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO api_keys (user_id, name, key_prefix, key_hash)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name, key_prefix, is_active, created_at, last_used_at
            """,
            (current_user["id"], request.name, key_prefix, key_hash),
        )
        row = cur.fetchone()
        conn.commit()
        return ApiKeyCreated(
            id=str(row[0]), name=row[1], key_prefix=row[2],
            is_active=row[3], created_at=str(row[4]),
            last_used_at=str(row[5]) if row[5] else None,
            raw_key=raw_key,
        )
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("", response_model=list[ApiKeyResponse])
def list_api_keys(current_user: dict = Depends(get_current_user)):
    """List all API keys for the current user (prefix + metadata only)."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, name, key_prefix, is_active, created_at, last_used_at
            FROM api_keys WHERE user_id = %s ORDER BY created_at DESC
            """,
            (current_user["id"],),
        )
        return [
            ApiKeyResponse(
                id=str(r[0]), name=r[1], key_prefix=r[2],
                is_active=r[3], created_at=str(r[4]),
                last_used_at=str(r[5]) if r[5] else None,
            )
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(key_id: str, current_user: dict = Depends(get_current_user)):
    """Revoke an API key (sets is_active=false)."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "UPDATE api_keys SET is_active = FALSE WHERE id = %s AND user_id = %s",
            (key_id, current_user["id"]),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="API key not found")
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
