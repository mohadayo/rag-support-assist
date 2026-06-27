"""documents ルーターのユニットテスト"""
import io
import sys
from unittest.mock import MagicMock, patch

# 外部依存を事前にモック化
sys.modules.setdefault("psycopg2", MagicMock())
sys.modules.setdefault("openai", MagicMock())

import pytest
from fastapi.testclient import TestClient

from app.main import app

_FIXED_TS = "2026-06-27T00:00:00+00:00"


@pytest.fixture
def client():
    """lifespan の migrate() をモックしてテストクライアントを返す"""
    with patch("app.main.migrate"), patch("app.main.get_chunk_count", return_value=0):
        with TestClient(app) as c:
            yield c


def _upload(client, content: bytes, filename: str = "test.txt", category: str = "faq"):
    """ファイルアップロードのヘルパー"""
    return client.post(
        "/api/documents/upload",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
        data={"category": category},
    )


class TestUploadDocument:
    def test_正常系_txtファイルアップロード(self, client):
        with patch("app.routers.documents.chunk_text", return_value=["チャンク1", "チャンク2"]), \
             patch("app.routers.documents.add_documents", return_value=2):
            resp = _upload(client, b"FAQ content for testing", "faq.txt", "faq")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "faq.txt"
        assert body["category"] == "faq"
        assert body["chunk_count"] == 2
        assert "id" in body
        assert "uploaded_at" in body

    def test_正常系_mdファイルアップロード(self, client):
        with patch("app.routers.documents.chunk_text", return_value=["c1"]), \
             patch("app.routers.documents.add_documents", return_value=1):
            resp = _upload(client, b"# Markdown content", "readme.md", "manual")
        assert resp.status_code == 200
        assert resp.json()["name"] == "readme.md"
        assert resp.json()["category"] == "manual"

    def test_正常系_csvファイルアップロード(self, client):
        with patch("app.routers.documents.chunk_text", return_value=["c1"]), \
             patch("app.routers.documents.add_documents", return_value=1):
            resp = _upload(client, b"col1,col2\nv1,v2", "data.csv", "history")
        assert resp.status_code == 200
        assert resp.json()["name"] == "data.csv"

    def test_正常系_全カテゴリ(self, client):
        for cat in ["faq", "terms", "manual", "history"]:
            with patch("app.routers.documents.chunk_text", return_value=["c"]), \
                 patch("app.routers.documents.add_documents", return_value=1):
                resp = _upload(client, b"content", "file.txt", cat)
            assert resp.status_code == 200, f"category={cat} が失敗"

    def test_400_対応外拡張子(self, client):
        resp = _upload(client, b"content", "file.pdf", "faq")
        assert resp.status_code == 400
        assert "対応形式" in resp.json()["detail"]

    def test_400_対応外拡張子_docx(self, client):
        resp = _upload(client, b"content", "file.docx", "faq")
        assert resp.status_code == 400

    def test_400_無効カテゴリ(self, client):
        resp = _upload(client, b"content", "file.txt", "invalid_cat")
        assert resp.status_code == 400
        assert "カテゴリ" in resp.json()["detail"]

    def test_400_空ファイル(self, client):
        resp = _upload(client, b"", "empty.txt", "faq")
        assert resp.status_code == 400
        assert "空" in resp.json()["detail"]

    def test_400_空白のみファイル(self, client):
        resp = _upload(client, b"   \n\n  ", "whitespace.txt", "faq")
        assert resp.status_code == 400

    def test_413_ファイルサイズ超過(self, client):
        big_content = b"a" * (1 * 1024 * 1024 + 1)
        with patch("app.routers.documents._MAX_UPLOAD_SIZE_BYTES", 1 * 1024 * 1024), \
             patch("app.routers.documents._MAX_UPLOAD_SIZE_MB", 1):
            resp = _upload(client, big_content, "big.txt", "faq")
        assert resp.status_code == 413
        assert "上限" in resp.json()["detail"]

    def test_400_拡張子なしファイル名(self, client):
        resp = _upload(client, b"content", "noext", "faq")
        assert resp.status_code == 400


class TestListDocuments:
    def test_正常系_空一覧(self, client):
        with patch("app.routers.documents.get_document_stats", return_value=[]):
            resp = client.get("/api/documents")
        assert resp.status_code == 200
        body = resp.json()
        assert body["documents"] == []
        assert body["total"] == 0

    def test_正常系_1件(self, client):
        stats = [
            {"id": "id1", "name": "a.txt", "category": "faq", "chunk_count": 3, "uploaded_at": _FIXED_TS},
        ]
        with patch("app.routers.documents.get_document_stats", return_value=stats):
            resp = client.get("/api/documents")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["documents"][0]["name"] == "a.txt"

    def test_正常系_複数件(self, client):
        stats = [
            {"id": "id1", "name": "a.txt", "category": "faq", "chunk_count": 3, "uploaded_at": _FIXED_TS},
            {"id": "id2", "name": "b.md", "category": "manual", "chunk_count": 5, "uploaded_at": _FIXED_TS},
            {"id": "id3", "name": "c.csv", "category": "terms", "chunk_count": 2, "uploaded_at": _FIXED_TS},
        ]
        with patch("app.routers.documents.get_document_stats", return_value=stats):
            resp = client.get("/api/documents")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["documents"]) == 3
        assert body["documents"][1]["chunk_count"] == 5


class TestDeleteDocument:
    def test_正常系_削除成功(self, client):
        with patch("app.routers.documents.delete_document", return_value=3):
            resp = client.delete("/api/documents/test-doc-id")
        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted_chunks"] == 3
        assert body["document_id"] == "test-doc-id"

    def test_正常系_1チャンク削除(self, client):
        with patch("app.routers.documents.delete_document", return_value=1):
            resp = client.delete("/api/documents/some-id")
        assert resp.status_code == 200
        assert resp.json()["deleted_chunks"] == 1

    def test_404_存在しないドキュメント(self, client):
        with patch("app.routers.documents.delete_document", return_value=0):
            resp = client.delete("/api/documents/not-exist")
        assert resp.status_code == 404
        assert "見つかりません" in resp.json()["detail"]
