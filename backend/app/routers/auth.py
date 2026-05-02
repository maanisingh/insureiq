"""
Auth router — registration, login, JWT, password reset, profile management.
"""

import os
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import bcrypt
import jwt

from app.database import get_db_connection
from app.schemas.auth import (
    RegisterRequest, LoginRequest, TokenResponse, UserResponse,
    UserUpdate, ForgotPasswordRequest, ResetPasswordRequest,
)

load_dotenv(Path(__file__).parent.parent.parent / "config" / ".env")

router   = APIRouter()
security = HTTPBearer()

SECRET_KEY       = os.getenv("SECRET_KEY", "insurance-ai-jwt-secret-change-in-production")
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
FRONTEND_URL     = os.getenv("FRONTEND_URL", "http://localhost:3000")
RESET_TOKEN_TTL  = 3600  # 1 hour in seconds


# ── Token helpers ─────────────────────────────────────────────────────────────

def create_token(user_id: str, email: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode(
        {"user_id": user_id, "email": email, "exp": exp},
        SECRET_KEY,
        algorithm="HS256",
    )


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Validate JWT or API key and return {id, email, full_name, is_active}.

    Accepts:
    - JWT Bearer tokens (standard login flow)
    - API keys starting with 'ak_' (programmatic access)
    """
    token = credentials.credentials

    # ── API Key path ──────────────────────────────────────────────────────────
    if token.startswith("ak_"):
        import hashlib
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        conn = get_db_connection()
        cur  = conn.cursor()
        try:
            cur.execute(
                """
                SELECT ak.user_id, u.email, u.full_name, u.is_active
                FROM api_keys ak
                JOIN users u ON u.id = ak.user_id
                WHERE ak.key_hash = %s AND ak.is_active = TRUE AND u.is_active = TRUE
                """,
                (key_hash,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="Invalid or revoked API key")
            # Update last_used_at
            cur.execute(
                "UPDATE api_keys SET last_used_at = NOW() WHERE key_hash = %s",
                (key_hash,),
            )
            conn.commit()
            return {"id": str(row[0]), "email": row[1], "full_name": row[2]}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            cur.close()
            conn.close()

    # ── JWT path ──────────────────────────────────────────────────────────────
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id, email, full_name, is_active FROM users WHERE id = %s",
            (payload["user_id"],),
        )
        user = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user[3]:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    return {"id": str(user[0]), "email": user[1], "full_name": user[2]}


# ── Register ──────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest):
    """Register a new user. Creates a default workspace automatically."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE email = %s", (request.email,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")

        user_id       = str(uuid.uuid4())
        password_hash = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()

        cur.execute(
            """
            INSERT INTO users (id, email, password_hash, full_name)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, request.email, password_hash, request.full_name),
        )

        # Create a default workspace
        workspace_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO workspaces (id, user_id, name, description)
            VALUES (%s, %s, %s, %s)
            """,
            (workspace_id, user_id, "Default Workspace", "Your default workspace"),
        )
        conn.commit()

        token = create_token(user_id, request.email)
        return TokenResponse(
            access_token=token,
            user_id=user_id,
            email=request.email,
            full_name=request.full_name,
        )
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest):
    """Authenticate user and return JWT."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id, email, password_hash, full_name, is_active FROM users WHERE email = %s",
            (request.email,),
        )
        user = cur.fetchone()

        if not user or not bcrypt.checkpw(request.password.encode(), user[2].encode()):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not user[4]:
            raise HTTPException(status_code=403, detail="Account is deactivated")

        token = create_token(str(user[0]), user[1])
        return TokenResponse(
            access_token=token,
            user_id=str(user[0]),
            email=user[1],
            full_name=user[3],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ── Refresh ───────────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
def refresh_token(current_user: dict = Depends(get_current_user)):
    """Issue a new JWT with a fresh 24-hour expiry."""
    token = create_token(current_user["id"], current_user["email"])
    return TokenResponse(
        access_token=token,
        user_id=current_user["id"],
        email=current_user["email"],
        full_name=current_user.get("full_name"),
    )


# ── Me ────────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT id, email, full_name, is_active, is_verified FROM users WHERE id = %s",
            (current_user["id"],),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return UserResponse(
            id=str(row[0]), email=row[1], full_name=row[2],
            is_active=row[3], is_verified=row[4],
        )
    finally:
        cur.close()
        conn.close()


@router.patch("/me", response_model=UserResponse)
def update_me(request: UserUpdate, current_user: dict = Depends(get_current_user)):
    """Update the current user's profile (full_name, email, password)."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT password_hash FROM users WHERE id = %s",
            (current_user["id"],),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        updates = []
        params  = []

        if request.full_name is not None:
            updates.append("full_name = %s")
            params.append(request.full_name)

        if request.email is not None or request.new_password is not None:
            # Require current password for sensitive changes
            if not request.current_password:
                raise HTTPException(status_code=400, detail="current_password required to change email or password")
            if not bcrypt.checkpw(request.current_password.encode(), row[0].encode()):
                raise HTTPException(status_code=401, detail="Incorrect current password")

            if request.email is not None:
                cur.execute("SELECT id FROM users WHERE email = %s", (request.email,))
                if cur.fetchone():
                    raise HTTPException(status_code=400, detail="Email already in use")
                updates.append("email = %s")
                params.append(str(request.email))

            if request.new_password is not None:
                new_hash = bcrypt.hashpw(request.new_password.encode(), bcrypt.gensalt()).decode()
                updates.append("password_hash = %s")
                params.append(new_hash)

        if updates:
            params.append(current_user["id"])
            cur.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = %s",
                params,
            )
            conn.commit()

        cur.execute(
            "SELECT id, email, full_name, is_active, is_verified FROM users WHERE id = %s",
            (current_user["id"],),
        )
        row = cur.fetchone()
        return UserResponse(
            id=str(row[0]), email=row[1], full_name=row[2],
            is_active=row[3], is_verified=row[4],
        )
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(current_user: dict = Depends(get_current_user)):
    """Permanently delete the current user account (cascades to all data)."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("DELETE FROM users WHERE id = %s", (current_user["id"],))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ── Password Reset ────────────────────────────────────────────────────────────

@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest):
    """Generate a password reset token.

    The raw token is returned in the response (for now — wire up email when
    SMTP is configured). In production the token should only be sent via email.
    """
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE email = %s AND is_active = TRUE", (request.email,))
        user = cur.fetchone()

        # Always return 200 to avoid email enumeration
        if not user:
            return {"message": "If that email exists, a reset token has been issued."}

        user_id = str(user[0])

        # Invalidate existing unused tokens for this user
        cur.execute(
            "UPDATE password_reset_tokens SET used_at = NOW() WHERE user_id = %s AND used_at IS NULL",
            (user_id,),
        )

        raw_token  = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=RESET_TOKEN_TTL)

        cur.execute(
            """
            INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
            VALUES (%s, %s, %s)
            """,
            (user_id, token_hash, expires_at),
        )
        conn.commit()

        # TODO: Replace with email when SMTP is configured
        # reset_url = f"{FRONTEND_URL}/reset-password?token={raw_token}"
        # await send_password_reset_email(request.email, reset_url)

        return {
            "message": "Password reset token issued.",
            "reset_token": raw_token,  # Remove this line once email is configured
            "expires_in_seconds": RESET_TOKEN_TTL,
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest):
    """Consume a reset token and set a new password."""
    token_hash = hashlib.sha256(request.token.encode()).hexdigest()

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, user_id, expires_at, used_at
            FROM password_reset_tokens
            WHERE token_hash = %s
            """,
            (token_hash,),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")

        token_id, user_id, expires_at, used_at = row[0], row[1], row[2], row[3]

        if used_at is not None:
            raise HTTPException(status_code=400, detail="Reset token already used")

        # Make expires_at timezone-aware for comparison
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(status_code=400, detail="Reset token has expired")

        new_hash = bcrypt.hashpw(request.new_password.encode(), bcrypt.gensalt()).decode()

        cur.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (new_hash, user_id),
        )
        cur.execute(
            "UPDATE password_reset_tokens SET used_at = NOW() WHERE id = %s",
            (token_id,),
        )
        conn.commit()

        return {"message": "Password reset successfully. Please log in with your new password."}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
