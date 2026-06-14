"""documents.py ルーターのテスト"""

import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with (
        patch("app.main.migrate"),
        patch("app.main.get_chunk_count", return_value=0),
    ):
        with TestClient(app) as c:
            yield c


def _make_upload(content: bytes = b"test document content", filename: str = "test.txt"):
    return {"file": (filename, io.BytesIO(content), "text/plain")}


class TestUploadDocument:
    """POST /api/documents/upload エンドポイントのテスト"""

    def test_upload_txt_success(self, client):
        """txtファイルのアップロードが成功する"""
        with (
            patch("app.routers.documents.chunk_text", return_value=["チャンク1", "チャンク2"]),
            patch("app.routers.documents.add_documents", return_value=2),
        ):
            resp = client.post(
                "/api/documents/upload",
                data={"category": "faq"},
                files=_make_upload(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test.txt"
        assert data["category"] == "faq"
        assert data["chunk_count"] == 2
        assert "id" in data
        assert "uploaded_at" in data

    def test_upload_md_success(self, client):
        """mdファイルのアップロードが成功する"""
        with (
            patch("app.routers.documents.chunk_text", return_value=["チャンク"]),
            patch("app.routers.documents.add_documents", return_value=1),
        ):
            resp = client.post(
                "/api/documents/upload",
                data={"category": "manual"},
                files=_make_upload(filename="guide.md"),
            )

        assert resp.status_code == 200
        assert resp.json()["name"] == "guide.md"

    def test_upload_csv_success(self, client):
        """csvファイルのアップロードが成功する"""
        with (
            patch("app.routers.documents.chunk_text", return_value=["チャンク"]),
            patch("app.routers.documents.add_documents", return_value=1),
        ):
            resp = client.post(
                "/api/documents/upload",
                data={"category": "history"},
                files=_make_upload(b"col1,col2\nval1,val2", filename="data.csv"),
            )

        assert resp.status_code == 200

    def test_upload_invalid_extension_rejected(self, client):
        """対応外の拡張子は400で拒否される"""
        resp = client.post(
            "/api/documents/upload",
            data={"category": "faq"},
            files=_make_upload(filename="doc.pdf"),
        )
        assert resp.status_code == 400
        assert "対応形式" in resp.json()["detail"]

    def test_upload_invalid_category_rejected(self, client):
        """無効なカテゴリは400で拒否される"""
        resp = client.post(
            "/api/documents/upload",
            data={"category": "invalid"},
            files=_make_upload(),
        )
        assert resp.status_code == 400
        assert "カテゴリ" in resp.json()["detail"]

    def test_upload_empty_file_rejected(self, client):
        """空ファイルは400で拒否される"""
        resp = client.post(
            "/api/documents/upload",
            data={"category": "faq"},
            files=_make_upload(content=b"   \n\n   "),
        )
        assert resp.status_code == 400
        assert "空" in resp.json()["detail"]

    def test_upload_file_too_large_rejected(self, client):
        """上限を超えるファイルは413で拒否される"""
        large_content = b"a" * (11 * 1024 * 1024)
        resp = client.post(
            "/api/documents/upload",
            data={"category": "faq"},
            files=_make_upload(content=large_content),
        )
        assert resp.status_code == 413
        assert "上限" in resp.json()["detail"]

    def test_upload_default_category_is_faq(self, client):
        """カテゴリ省略時のデフォルトはfaq"""
        with (
            patch("app.routers.documents.chunk_text", return_value=["チャンク"]),
            patch("app.routers.documents.add_documents", return_value=1),
        ):
            resp = client.post(
                "/api/documents/upload",
                files=_make_upload(),
            )

        assert resp.status_code == 200
        assert resp.json()["category"] == "faq"

    def test_upload_valid_categories(self, client):
        """すべての有効カテゴリが受け付けられる"""
        for category in ["faq", "terms", "manual", "history"]:
            with (
                patch("app.routers.documents.chunk_text", return_value=["チャンク"]),
                patch("app.routers.documents.add_documents", return_value=1),
            ):
                resp = client.post(
                    "/api/documents/upload",
                    data={"category": category},
                    files=_make_upload(),
                )
            assert resp.status_code == 200, f"category={category} should be accepted"
            assert resp.json()["category"] == category

    def test_upload_generates_unique_ids(self, client):
        """複数アップロード時に一意のIDが採番される"""
        ids = []
        for _ in range(3):
            with (
                patch("app.routers.documents.chunk_text", return_value=["チャンク"]),
                patch("app.routers.documents.add_documents", return_value=1),
            ):
                resp = client.post(
                    "/api/documents/upload",
                    data={"category": "faq"},
                    files=_make_upload(),
                )
            ids.append(resp.json()["id"])
        assert len(set(ids)) == 3


class TestListDocuments:
    """GET /api/documents エンドポイントのテスト"""

    def test_list_documents_empty(self, client):
        """ドキュメントが0件の場合は空リストを返す"""
        with patch("app.routers.documents.get_document_stats", return_value=[]):
            resp = client.get("/api/documents")

        assert resp.status_code == 200
        data = resp.json()
        assert data["documents"] == []
        assert data["total"] == 0

    def test_list_documents_returns_all(self, client):
        """登録済みドキュメントの一覧を返す"""
        mock_stats = [
            {
                "id": "abc-123",
                "name": "faq.txt",
                "category": "faq",
                "chunk_count": 5,
                "uploaded_at": "2024-01-01T00:00:00+00:00",
            },
            {
                "id": "def-456",
                "name": "manual.md",
                "category": "manual",
                "chunk_count": 10,
                "uploaded_at": "2024-01-02T00:00:00+00:00",
            },
        ]
        with patch("app.routers.documents.get_document_stats", return_value=mock_stats):
            resp = client.get("/api/documents")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["documents"]) == 2
        assert data["documents"][0]["id"] == "abc-123"
        assert data["documents"][1]["name"] == "manual.md"

    def test_list_documents_structure(self, client):
        """ドキュメント情報に必要なフィールドが含まれる"""
        mock_stats = [
            {
                "id": "test-id",
                "name": "test.txt",
                "category": "faq",
                "chunk_count": 3,
                "uploaded_at": "2024-06-14T00:00:00+00:00",
            }
        ]
        with patch("app.routers.documents.get_document_stats", return_value=mock_stats):
            resp = client.get("/api/documents")

        assert resp.status_code == 200
        doc = resp.json()["documents"][0]
        for field in ["id", "name", "category", "chunk_count", "uploaded_at"]:
            assert field in doc, f"フィールド {field} が欠けています"


class TestDeleteDocument:
    """DELETE /api/documents/{doc_id} エンドポイントのテスト"""

    def test_delete_existing_document(self, client):
        """存在するドキュメントを削除すると200が返る"""
        with patch("app.routers.documents.delete_document", return_value=5):
            resp = client.delete("/api/documents/test-doc-id")

        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted_chunks"] == 5
        assert data["document_id"] == "test-doc-id"

    def test_delete_nonexistent_document_returns_404(self, client):
        """存在しないドキュメントの削除は404を返す"""
        with patch("app.routers.documents.delete_document", return_value=0):
            resp = client.delete("/api/documents/nonexistent-id")

        assert resp.status_code == 404
        assert "見つかりません" in resp.json()["detail"]

    def test_delete_uses_correct_doc_id(self, client):
        """指定されたdoc_idでdeleteが呼ばれる"""
        with patch("app.routers.documents.delete_document", return_value=3) as mock_delete:
            client.delete("/api/documents/specific-id-123")

        mock_delete.assert_called_once_with("specific-id-123")
