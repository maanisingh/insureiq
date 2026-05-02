"""Tests for /workspaces endpoints."""

import pytest


class TestWorkspaces:
    def test_list_workspaces(self, client, auth_headers):
        resp = client.get("/workspaces", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        # Should have at least the default workspace from registration
        assert len(resp.json()) >= 1

    def test_create_workspace(self, client, auth_headers):
        resp = client.post("/workspaces", json={
            "name": "My Test WS", "description": "created by pytest",
        }, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Test WS"
        assert "id" in data
        assert "created_at" in data

    def test_get_workspace(self, client, auth_headers, workspace_id):
        resp = client.get(f"/workspaces/{workspace_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == workspace_id

    def test_get_workspace_not_found(self, client, auth_headers):
        resp = client.get("/workspaces/00000000-0000-0000-0000-000000000000", headers=auth_headers)
        assert resp.status_code == 404

    def test_workspace_requires_auth(self, client):
        resp = client.get("/workspaces")
        assert resp.status_code == 401

    def test_delete_workspace(self, client, auth_headers):
        # Create a workspace to delete
        resp = client.post("/workspaces", json={"name": "Delete Me"}, headers=auth_headers)
        wid  = resp.json()["id"]
        resp2 = client.delete(f"/workspaces/{wid}", headers=auth_headers)
        assert resp2.status_code == 200
        # Confirm deleted
        resp3 = client.get(f"/workspaces/{wid}", headers=auth_headers)
        assert resp3.status_code == 404

    def test_cannot_access_other_users_workspace(self, client):
        other_email = "other_ws_user@example.com"
        other_pass  = "OtherPass123!"

        # Clean up leftover from previous run
        import psycopg2, os
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST","localhost"), port=os.getenv("DB_PORT","5433"),
            database=os.getenv("DB_NAME","insurance_ai"), user=os.getenv("DB_USER","insurance_ai"),
            password=os.getenv("DB_PASSWORD","insurance_secure_2024"),
        )
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE email = %s", (other_email,))
        conn.commit()
        cur.close()
        conn.close()

        # Register second user
        resp = client.post("/auth/register", json={"email": other_email, "password": other_pass})
        assert resp.status_code == 201, resp.text
        other_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

        # Get their workspace id
        ws_resp      = client.get("/workspaces", headers=other_headers)
        other_ws_id  = ws_resp.json()[0]["id"]

        # Try to access it with main test user
        from tests.conftest import TEST_EMAIL, TEST_PASSWORD
        login = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        main_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        resp2 = client.get(f"/workspaces/{other_ws_id}", headers=main_headers)
        assert resp2.status_code == 404

        # Cleanup
        client.delete("/auth/me", headers=other_headers)
