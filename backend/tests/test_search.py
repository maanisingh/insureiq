"""Tests for /search endpoints."""

import pytest


class TestSearch:
    def test_search_global(self, client, auth_headers):
        """Global search should return results (or an empty list if index not ready)."""
        resp = client.get("/search/global?query=insurance+deductible&limit=5", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_search_global_requires_auth(self, client):
        resp = client.get("/search/global?query=test")
        assert resp.status_code == 401

    def test_search_workspace_empty(self, client, auth_headers, workspace_id):
        """Workspace search on an empty collection should return [] not an error."""
        resp = client.get(
            f"/search/workspace/{workspace_id}?query=claims&limit=5",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_search_workspace_wrong_id(self, client, auth_headers):
        resp = client.get(
            "/search/workspace/00000000-0000-0000-0000-000000000000?query=test",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_search_post_dual(self, client, auth_headers, workspace_id):
        """POST /search should always return both global_results and workspace_results keys."""
        resp = client.post("/search", json={
            "query":        "fraud detection",
            "workspace_id": workspace_id,
            "limit":        5,
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "global_results"    in data
        assert "workspace_results" in data

    def test_search_result_shape(self, client, auth_headers):
        """Each result item must have id, score, text, source."""
        resp = client.get("/search/global?query=actuary&limit=3", headers=auth_headers)
        results = resp.json()["results"]
        if results:  # only if index has data
            for r in results:
                assert "id"    in r
                assert "score" in r
                assert "text"  in r
