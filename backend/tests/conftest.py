"""
pytest configuration and shared fixtures.

Requires the full docker stack to be running:
  docker compose up -d  (postgres, redis, qdrant-global, qdrant-workspace)
"""

import os
import pytest
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(Path(__file__).parent.parent / "config" / ".env")

from app.main import app


# ── DB helper ─────────────────────────────────────────────────────────────────

def _db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5433"),
        database=os.getenv("DB_NAME", "insurance_ai"),
        user=os.getenv("DB_USER", "insurance_ai"),
        password=os.getenv("DB_PASSWORD", "insurance_secure_2024"),
    )


# ── Client fixture ────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


# ── Test user (session-scoped, cleaned up after all tests) ───────────────────

TEST_EMAIL    = "pytest_user_insurance@example.com"
TEST_PASSWORD = "TestPass123!"
TEST_NAME     = "Pytest User"


@pytest.fixture(scope="session")
def registered_user(client):
    """Register a test user once for the whole session."""
    # Clean up any leftover from a previous run
    conn = _db()
    cur  = conn.cursor()
    cur.execute("DELETE FROM users WHERE email = %s", (TEST_EMAIL,))
    conn.commit()
    cur.close()
    conn.close()

    resp = client.post("/auth/register", json={
        "email":     TEST_EMAIL,
        "password":  TEST_PASSWORD,
        "full_name": TEST_NAME,
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    yield data

    # Teardown: delete test user (cascades everything)
    conn = _db()
    cur  = conn.cursor()
    cur.execute("DELETE FROM users WHERE email = %s", (TEST_EMAIL,))
    conn.commit()
    cur.close()
    conn.close()


@pytest.fixture(scope="session")
def auth_headers(client, registered_user):
    """Return Authorization headers for the test user."""
    token = registered_user["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def user_id(registered_user):
    return registered_user["user_id"]


# ── Workspace fixture ─────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def workspace_id(client, auth_headers):
    """Create a test workspace and return its id."""
    resp = client.post("/workspaces", json={"name": "Test Workspace", "description": "pytest"}, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── DB connection fixture ─────────────────────────────────────────────────────

@pytest.fixture()
def db():
    conn = _db()
    yield conn
    conn.close()
