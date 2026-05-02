"""Tests for /chat endpoints."""

import pytest


class TestChatSession:
    def test_create_session(self, client, auth_headers, workspace_id):
        resp = client.post(f"/chat/session?workspace_id={workspace_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["workspace_id"] == workspace_id

    def test_create_session_wrong_workspace(self, client, auth_headers):
        resp = client.post(
            "/chat/session?workspace_id=00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_create_session_requires_auth(self, client, workspace_id):
        resp = client.post(f"/chat/session?workspace_id={workspace_id}")
        assert resp.status_code == 401


class TestChat:
    def test_chat_returns_response(self, client, auth_headers, workspace_id):
        """Smoke test: agent must return a non-empty response string."""
        resp = client.post("/chat", json={
            "workspace_id": workspace_id,
            "message":      "What is insurance deductible?",
        }, headers=auth_headers, timeout=60)
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert isinstance(data["response"], str)
        assert len(data["response"]) > 10
        assert "session_id" in data
        assert isinstance(data["sources"], list)

    def test_chat_session_persists(self, client, auth_headers, workspace_id):
        """Messages should be stored in history."""
        session = client.post(f"/chat/session?workspace_id={workspace_id}", headers=auth_headers).json()["session_id"]

        client.post("/chat", json={
            "workspace_id": workspace_id,
            "session_id":   session,
            "message":      "What is a premium?",
        }, headers=auth_headers, timeout=60)

        # Fetch history
        hist = client.get(
            f"/chat/history?workspace_id={workspace_id}&session_id={session}",
            headers=auth_headers,
        )
        assert hist.status_code == 200
        messages = hist.json()["messages"]
        assert len(messages) >= 1

    def test_chat_auto_creates_session(self, client, auth_headers, workspace_id):
        """If session_id is omitted, one should be created."""
        resp = client.post("/chat", json={
            "workspace_id": workspace_id,
            "message":      "Define actuary.",
        }, headers=auth_headers, timeout=60)
        assert resp.status_code == 200
        assert resp.json()["session_id"]

    def test_chat_requires_auth(self, client, workspace_id):
        resp = client.post("/chat", json={
            "workspace_id": workspace_id,
            "message":      "Hello",
        })
        assert resp.status_code == 401


class TestChatHistory:
    def test_list_sessions(self, client, auth_headers, workspace_id):
        resp = client.get(f"/chat/history?workspace_id={workspace_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert "sessions" in resp.json()

    def test_history_wrong_workspace(self, client, auth_headers):
        resp = client.get(
            "/chat/history?workspace_id=00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 404
