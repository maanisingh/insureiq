"""Tests for /uploads endpoints."""

import io
import pytest


def _txt_file(content: str = "This is a test insurance document. Policy number ABC123."):
    return ("test_policy.txt", io.BytesIO(content.encode()), "text/plain")


class TestUploads:
    def test_upload_txt_file(self, client, auth_headers, workspace_id):
        name, content, mime = _txt_file()
        resp = client.post(
            "/uploads",
            data={"workspace_id": workspace_id},
            files={"file": (name, content, mime)},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"]
        assert data["original_filename"] == name
        assert data["extraction_status"] in ("pending", "processing", "done")
        assert data["file_type"] == "txt"

    def test_upload_returns_upload_id(self, client, auth_headers, workspace_id):
        name, content, mime = _txt_file("Another policy doc.")
        resp = client.post(
            "/uploads",
            data={"workspace_id": workspace_id},
            files={"file": (name, content, mime)},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert "id" in resp.json()

    def test_upload_unsupported_format(self, client, auth_headers, workspace_id):
        resp = client.post(
            "/uploads",
            data={"workspace_id": workspace_id},
            files={"file": ("test.mp4", io.BytesIO(b"fake video"), "video/mp4")},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["detail"]

    def test_upload_wrong_workspace(self, client, auth_headers):
        name, content, mime = _txt_file()
        resp = client.post(
            "/uploads",
            data={"workspace_id": "00000000-0000-0000-0000-000000000000"},
            files={"file": (name, content, mime)},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_upload_requires_auth(self, client, workspace_id):
        name, content, mime = _txt_file()
        resp = client.post(
            "/uploads",
            data={"workspace_id": workspace_id},
            files={"file": (name, content, mime)},
        )
        assert resp.status_code == 401

    def test_list_uploads(self, client, auth_headers, workspace_id):
        # Upload first
        name, content, mime = _txt_file("Listing test doc.")
        client.post(
            "/uploads",
            data={"workspace_id": workspace_id},
            files={"file": (name, content, mime)},
            headers=auth_headers,
        )
        resp = client.get(f"/uploads?workspace_id={workspace_id}", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()
        assert isinstance(items, list)
        assert len(items) >= 1
        # Check shape
        for item in items:
            assert "id"                in item
            assert "filename"          in item
            assert "file_type"         in item
            assert "extraction_status" in item

    def test_get_upload_detail(self, client, auth_headers, workspace_id):
        name, content, mime = _txt_file("Detail test doc.")
        upload = client.post(
            "/uploads",
            data={"workspace_id": workspace_id},
            files={"file": (name, content, mime)},
            headers=auth_headers,
        ).json()
        upload_id = upload["id"]

        resp = client.get(
            f"/uploads/{upload_id}?workspace_id={workspace_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == upload_id
        assert data["workspace_id"] == workspace_id

    def test_get_upload_not_found(self, client, auth_headers, workspace_id):
        resp = client.get(
            f"/uploads/00000000-0000-0000-0000-000000000000?workspace_id={workspace_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_delete_upload(self, client, auth_headers, workspace_id):
        name, content, mime = _txt_file("Delete me doc.")
        upload_id = client.post(
            "/uploads",
            data={"workspace_id": workspace_id},
            files={"file": (name, content, mime)},
            headers=auth_headers,
        ).json()["id"]

        del_resp = client.delete(
            f"/uploads/{upload_id}?workspace_id={workspace_id}",
            headers=auth_headers,
        )
        assert del_resp.status_code == 204

        # Verify gone
        get_resp = client.get(
            f"/uploads/{upload_id}?workspace_id={workspace_id}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 404
