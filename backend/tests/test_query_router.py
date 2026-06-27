"""query ルーターのユニットテスト"""
import sys
from unittest.mock import MagicMock, patch

# 外部依存を事前にモック化（他テストより先に実行される場合に備えて）
sys.modules.setdefault("psycopg2", MagicMock())
_openai_mod = MagicMock()
sys.modules.setdefault("openai", _openai_mod)
_openai_mod.OpenAI = MagicMock


class _FakeOpenAIError(Exception):
    """OpenAIError の代替。openai がモックされているため独自定義する。"""


_openai_mod.OpenAIError = _FakeOpenAIError

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """lifespan の migrate() をモックしてテストクライアントを返す"""
    with patch("app.main.migrate"):
        with TestClient(app) as c:
            yield c


def _make_search_result(docs=None, metas=None, dists=None):
    """ベクトル検索のダミー結果を生成する"""
    docs = docs or ["FAQ内容: 返品は購入後30日以内に可能です。"]
    metas = metas or [{"document_name": "faq.txt", "category": "faq"}]
    dists = dists or [0.1]
    return {"documents": [docs], "metadatas": [metas], "distances": [dists]}


class TestPostQuery:
    def test_正常系_標準トーンで回答を返す(self, client):
        with patch("app.routers.query.search", return_value=_make_search_result()), \
             patch("app.routers.query.generate_answer", return_value=("テスト回答", False, None)):
            resp = client.post("/api/query", json={"query": "返品方法を教えてください"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == "テスト回答"
        assert body["should_escalate"] is False
        assert body["escalation_reason"] is None
        assert len(body["sources"]) == 1
        assert body["sources"][0]["document_name"] == "faq.txt"

    def test_正常系_丁寧トーン(self, client):
        with patch("app.routers.query.search", return_value=_make_search_result()), \
             patch("app.routers.query.generate_answer", return_value=("丁寧な回答文", False, None)):
            resp = client.post("/api/query", json={"query": "問い合わせ内容", "tone": "polite"})
        assert resp.status_code == 200

    def test_正常系_簡潔トーン(self, client):
        with patch("app.routers.query.search", return_value=_make_search_result()), \
             patch("app.routers.query.generate_answer", return_value=("簡潔な回答", False, None)):
            resp = client.post("/api/query", json={"query": "問い合わせ", "tone": "concise"})
        assert resp.status_code == 200

    def test_正常系_エスカレーション要(self, client):
        with patch("app.routers.query.search", return_value=_make_search_result()), \
             patch("app.routers.query.generate_answer", return_value=("回答", True, "法的判断が必要")):
            resp = client.post("/api/query", json={"query": "複雑な問い合わせ"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["should_escalate"] is True
        assert body["escalation_reason"] == "法的判断が必要"

    def test_正常系_relevance_score計算(self, client):
        """distance=0.3 → relevance_score=0.7 になること"""
        result = _make_search_result(dists=[0.3])
        with patch("app.routers.query.search", return_value=result), \
             patch("app.routers.query.generate_answer", return_value=("回答", False, None)):
            resp = client.post("/api/query", json={"query": "テスト"})
        assert resp.status_code == 200
        assert resp.json()["sources"][0]["relevance_score"] == pytest.approx(0.7)

    def test_正常系_distance1以上はscore0になる(self, client):
        """distance >= 1 のとき relevance_score は 0.0 になること"""
        result = _make_search_result(dists=[1.5])
        with patch("app.routers.query.search", return_value=result), \
             patch("app.routers.query.generate_answer", return_value=("回答", False, None)):
            resp = client.post("/api/query", json={"query": "テスト"})
        assert resp.status_code == 200
        assert resp.json()["sources"][0]["relevance_score"] == 0.0

    def test_正常系_複数ソース(self, client):
        docs = ["内容1", "内容2", "内容3"]
        metas = [
            {"document_name": "a.txt", "category": "faq"},
            {"document_name": "b.txt", "category": "manual"},
            {"document_name": "c.txt", "category": "terms"},
        ]
        dists = [0.1, 0.2, 0.3]
        result = _make_search_result(docs=docs, metas=metas, dists=dists)
        with patch("app.routers.query.search", return_value=result), \
             patch("app.routers.query.generate_answer", return_value=("回答", False, None)):
            resp = client.post("/api/query", json={"query": "テスト"})
        assert resp.status_code == 200
        assert len(resp.json()["sources"]) == 3

    def test_422_空クエリ(self, client):
        resp = client.post("/api/query", json={"query": ""})
        assert resp.status_code == 422

    def test_422_空白のみクエリ(self, client):
        resp = client.post("/api/query", json={"query": "   "})
        assert resp.status_code == 422

    def test_422_5001文字超クエリ(self, client):
        resp = client.post("/api/query", json={"query": "あ" * 5001})
        assert resp.status_code == 422

    def test_422_無効トーン(self, client):
        resp = client.post("/api/query", json={"query": "問い合わせ", "tone": "angry"})
        assert resp.status_code == 422

    def test_503_ベクトルDB接続エラー(self, client):
        with patch("app.routers.query.search", side_effect=Exception("pgvector接続失敗")):
            resp = client.post("/api/query", json={"query": "問い合わせ"})
        assert resp.status_code == 503
        assert "再試行" in resp.json()["detail"]

    def test_503_OpenAI_APIエラー(self, client):
        """OpenAIError をモックの例外でシミュレートする"""
        with patch("app.routers.query.OpenAIError", _FakeOpenAIError), \
             patch("app.routers.query.search", return_value=_make_search_result()), \
             patch("app.routers.query.generate_answer", side_effect=_FakeOpenAIError("rate limit")):
            resp = client.post("/api/query", json={"query": "問い合わせ"})
        assert resp.status_code == 503

    def test_500_予期しないエラー(self, client):
        with patch("app.routers.query.OpenAIError", _FakeOpenAIError), \
             patch("app.routers.query.search", return_value=_make_search_result()), \
             patch("app.routers.query.generate_answer", side_effect=ValueError("unexpected")):
            resp = client.post("/api/query", json={"query": "問い合わせ"})
        assert resp.status_code == 500


class TestGetHealth:
    def test_正常系_DB接続OK(self, client):
        with patch("app.main.get_chunk_count", return_value=42):
            resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["vector_db"] == "connected"
        assert body["document_chunks"] == 42

    def test_DB異常_degradedを返す(self, client):
        with patch("app.main.get_chunk_count", side_effect=Exception("DB接続失敗")):
            resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["vector_db"] == "disconnected"
