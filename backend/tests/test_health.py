"""/api/health エンドポイントのユニットテスト"""

import sys
from unittest.mock import MagicMock, patch

# 外部依存を事前にモック化
sys.modules.setdefault("psycopg2", MagicMock())
sys.modules.setdefault("openai", MagicMock())

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client_ok():
    """DB 接続が正常なテストクライアント"""
    with patch("app.main.migrate"), patch("app.main.get_chunk_count", return_value=42):
        with TestClient(app) as c:
            yield c


@pytest.fixture
def client_degraded():
    """DB 接続が失敗するテストクライアント"""
    with patch("app.main.migrate"), patch(
        "app.main.get_chunk_count", side_effect=RuntimeError("DB down")
    ):
        with TestClient(app) as c:
            yield c


class TestHealthEndpoint:
    def test_正常系_200_status_ok(self, client_ok):
        resp = client_ok.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["vector_db"] == "connected"
        assert body["document_chunks"] == 42

    def test_異常系_503_status_degraded(self, client_degraded):
        """DB 接続に失敗した場合は HTTP 503 を返し、
        LB/監視ツールがステータスコードで異常を検出できること"""
        resp = client_degraded.get("/api/health")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["vector_db"] == "disconnected"
