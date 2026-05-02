"""Tests for /policies endpoints."""

import pytest


def _policy_data():
    return {
        "type":          "auto",
        "insured_name":  "Test Corp Ltd",
        "coverage":      100000,
        "deductible":    500,
        "premium":       1200,
        "effective_date": "2026-01-01",
        "expiry_date":   "2027-01-01",
    }


class TestPolicies:
    def test_create_policy(self, client, auth_headers, workspace_id):
        resp = client.post("/policies", json={
            "workspace_id": workspace_id,
            "policy_data":  _policy_data(),
        }, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["policy_number"].startswith("POL-")
        assert len(data["policy_number"]) == 12   # POL- + 8 hex chars
        assert data["policy_type"] == "auto"

    def test_list_policies(self, client, auth_headers, workspace_id):
        resp = client.get(f"/policies?workspace_id={workspace_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1

    def test_get_policy(self, client, auth_headers, workspace_id):
        # Create one
        create = client.post("/policies", json={
            "workspace_id": workspace_id,
            "policy_data":  _policy_data(),
        }, headers=auth_headers)
        policy_id = create.json()["id"]

        # Get it
        resp = client.get(
            f"/policies/{policy_id}?workspace_id={workspace_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == policy_id
        assert data["policy_data"]["insured_name"] == "Test Corp Ltd"

    def test_update_policy(self, client, auth_headers, workspace_id):
        create = client.post("/policies", json={
            "workspace_id": workspace_id,
            "policy_data":  _policy_data(),
        }, headers=auth_headers)
        policy_id = create.json()["id"]

        updated = dict(_policy_data())
        updated["premium"] = 1500

        resp = client.patch(
            f"/policies/{policy_id}?workspace_id={workspace_id}",
            json={"policy_data": updated},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # Verify update persisted
        get_resp = client.get(
            f"/policies/{policy_id}?workspace_id={workspace_id}",
            headers=auth_headers,
        )
        assert get_resp.json()["policy_data"]["premium"] == 1500

    def test_delete_policy(self, client, auth_headers, workspace_id):
        create = client.post("/policies", json={
            "workspace_id": workspace_id,
            "policy_data":  _policy_data(),
        }, headers=auth_headers)
        policy_id = create.json()["id"]

        del_resp = client.delete(
            f"/policies/{policy_id}?workspace_id={workspace_id}",
            headers=auth_headers,
        )
        assert del_resp.status_code == 200

        get_resp = client.get(
            f"/policies/{policy_id}?workspace_id={workspace_id}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 404

    def test_policy_requires_auth(self, client, workspace_id):
        resp = client.get(f"/policies?workspace_id={workspace_id}")
        assert resp.status_code == 401

    def test_policy_wrong_workspace_returns_404(self, client, auth_headers):
        resp = client.get(
            "/policies?workspace_id=00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 404
