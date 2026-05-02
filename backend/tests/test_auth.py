"""Tests for /auth endpoints."""

import hashlib
import pytest
from tests.conftest import TEST_EMAIL, TEST_PASSWORD, TEST_NAME


class TestRegister:
    def test_register_success(self, client, registered_user):
        assert "access_token" in registered_user
        assert registered_user["email"] == TEST_EMAIL
        assert registered_user["full_name"] == TEST_NAME
        assert registered_user["user_id"]

    def test_register_duplicate_email(self, client):
        resp = client.post("/auth/register", json={
            "email": TEST_EMAIL, "password": TEST_PASSWORD,
        })
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"]

    def test_register_invalid_email(self, client):
        resp = client.post("/auth/register", json={
            "email": "not-an-email", "password": TEST_PASSWORD,
        })
        assert resp.status_code == 422

    def test_register_short_password(self, client):
        resp = client.post("/auth/register", json={
            "email": "short@test.invalid", "password": "abc",
        })
        assert resp.status_code == 422


class TestLogin:
    def test_login_success(self, client):
        resp = client.post("/auth/login", json={
            "email": TEST_EMAIL, "password": TEST_PASSWORD,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["email"] == TEST_EMAIL

    def test_login_wrong_password(self, client):
        resp = client.post("/auth/login", json={
            "email": TEST_EMAIL, "password": "WrongPass999!",
        })
        assert resp.status_code == 401

    def test_login_unknown_email(self, client):
        resp = client.post("/auth/login", json={
            "email": "nobody@example.com", "password": TEST_PASSWORD,
        })
        assert resp.status_code == 401


class TestMe:
    def test_get_me(self, client, auth_headers):
        resp = client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == TEST_EMAIL
        assert data["full_name"] == TEST_NAME
        assert data["is_active"] is True

    def test_get_me_no_token(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401  # HTTPBearer returns 401 when no credentials

    def test_get_me_invalid_token(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer invalidtoken"})
        assert resp.status_code == 401

    def test_update_me_full_name(self, client, auth_headers):
        resp = client.patch("/auth/me", json={"full_name": "Updated Name"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Updated Name"
        # Restore
        client.patch("/auth/me", json={"full_name": TEST_NAME}, headers=auth_headers)

    def test_update_password_requires_current(self, client, auth_headers):
        resp = client.patch("/auth/me", json={"new_password": "NewPass456!"}, headers=auth_headers)
        assert resp.status_code == 400

    def test_update_password_wrong_current(self, client, auth_headers):
        resp = client.patch("/auth/me", json={
            "current_password": "WrongCurrent!",
            "new_password": "NewPass456!",
        }, headers=auth_headers)
        assert resp.status_code == 401


class TestRefresh:
    def test_refresh_returns_new_token(self, client, auth_headers):
        resp = client.post("/auth/refresh", headers=auth_headers)
        assert resp.status_code == 200
        assert "access_token" in resp.json()


class TestPasswordReset:
    def test_forgot_password_returns_token(self, client):
        resp = client.post("/auth/forgot-password", json={"email": TEST_EMAIL})
        assert resp.status_code == 200
        data = resp.json()
        assert "reset_token" in data
        assert data["expires_in_seconds"] == 3600

    def test_forgot_password_unknown_email(self, client):
        # Should return 200 (no enumeration)
        resp = client.post("/auth/forgot-password", json={"email": "ghost@example.com"})
        assert resp.status_code == 200

    def test_reset_password_flow(self, client):
        # Step 1: request token
        resp = client.post("/auth/forgot-password", json={"email": TEST_EMAIL})
        token = resp.json()["reset_token"]

        # Step 2: reset with token
        new_pass = "ResetPass789!"
        resp2 = client.post("/auth/reset-password", json={
            "token": token, "new_password": new_pass,
        })
        assert resp2.status_code == 200
        assert "successfully" in resp2.json()["message"]

        # Step 3: login with new password
        resp3 = client.post("/auth/login", json={"email": TEST_EMAIL, "password": new_pass})
        assert resp3.status_code == 200

        # Step 4: restore original password
        client.post("/auth/forgot-password", json={"email": TEST_EMAIL})
        # (reset again — find new token in DB)
        import psycopg2, os
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST","localhost"), port=os.getenv("DB_PORT","5433"),
            database=os.getenv("DB_NAME","insurance_ai"), user=os.getenv("DB_USER","insurance_ai"),
            password=os.getenv("DB_PASSWORD","insurance_secure_2024"),
        )
        cur = conn.cursor()
        cur.execute("""
            SELECT prt.token_hash FROM password_reset_tokens prt
            JOIN users u ON prt.user_id = u.id
            WHERE u.email = %s AND prt.used_at IS NULL
            ORDER BY prt.created_at DESC LIMIT 1
        """, (TEST_EMAIL,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        # We only have the hash, can't reverse it. Use a second forgot flow instead.
        resp4 = client.post("/auth/forgot-password", json={"email": TEST_EMAIL})
        token2 = resp4.json()["reset_token"]
        client.post("/auth/reset-password", json={"token": token2, "new_password": TEST_PASSWORD})

    def test_reset_invalid_token(self, client):
        resp = client.post("/auth/reset-password", json={
            "token": "totally_invalid_token", "new_password": "NewPass123!",
        })
        assert resp.status_code == 400

    def test_reset_token_reuse_blocked(self, client):
        resp  = client.post("/auth/forgot-password", json={"email": TEST_EMAIL})
        token = resp.json()["reset_token"]
        client.post("/auth/reset-password", json={"token": token, "new_password": "AnotherPass1!"})
        # Try reusing the same token
        resp2 = client.post("/auth/reset-password", json={"token": token, "new_password": "YetAnother1!"})
        assert resp2.status_code == 400
        # Restore
        r2 = client.post("/auth/forgot-password", json={"email": TEST_EMAIL})
        t2 = r2.json()["reset_token"]
        client.post("/auth/reset-password", json={"token": t2, "new_password": TEST_PASSWORD})
