"""Tests for /api-keys endpoints and API key authentication."""

import pytest


class TestApiKeys:
    def test_create_api_key(self, client, auth_headers):
        resp = client.post("/api-keys", json={"name": "Test Key"}, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert "raw_key" in data
        assert data["raw_key"].startswith("ak_")
        assert data["key_prefix"].startswith("ak_")
        assert data["name"] == "Test Key"
        assert data["is_active"] is True

    def test_raw_key_not_in_list(self, client, auth_headers):
        """raw_key must only appear on creation, never in list."""
        client.post("/api-keys", json={"name": "List Test"}, headers=auth_headers)
        resp = client.get("/api-keys", headers=auth_headers)
        assert resp.status_code == 200
        for key in resp.json():
            assert "raw_key" not in key

    def test_list_api_keys(self, client, auth_headers):
        resp = client.get("/api-keys", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_api_key_authenticates(self, client, auth_headers):
        """API key must work as a Bearer token for authenticated endpoints."""
        create_resp = client.post("/api-keys", json={"name": "Auth Test"}, headers=auth_headers)
        raw_key = create_resp.json()["raw_key"]

        # Use the raw key to call /auth/me
        key_headers = {"Authorization": f"Bearer {raw_key}"}
        resp = client.get("/auth/me", headers=key_headers)
        assert resp.status_code == 200
        assert "email" in resp.json()

    def test_revoke_api_key(self, client, auth_headers):
        create_resp = client.post("/api-keys", json={"name": "Revoke Test"}, headers=auth_headers)
        key_id  = create_resp.json()["id"]
        raw_key = create_resp.json()["raw_key"]

        # Revoke it
        del_resp = client.delete(f"/api-keys/{key_id}", headers=auth_headers)
        assert del_resp.status_code == 204

        # Revoked key should no longer authenticate
        key_headers = {"Authorization": f"Bearer {raw_key}"}
        resp = client.get("/auth/me", headers=key_headers)
        assert resp.status_code == 401

    def test_requires_auth(self, client):
        resp = client.post("/api-keys", json={"name": "No Auth"})
        assert resp.status_code == 401

    def test_wrong_workspace_with_api_key(self, client, auth_headers):
        """API key should enforce ownership same as JWT."""
        create_resp = client.post("/api-keys", json={"name": "WS Test"}, headers=auth_headers)
        raw_key     = create_resp.json()["raw_key"]
        key_headers = {"Authorization": f"Bearer {raw_key}"}

        resp = client.get(
            "/policies?workspace_id=00000000-0000-0000-0000-000000000000",
            headers=key_headers,
        )
        assert resp.status_code == 404
