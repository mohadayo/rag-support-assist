"""query.py ルーターのテスト"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from openai import OpenAIError

from app.main import app


@pytest.fixture
def client():
    with (
        patch("app.main.migrate"),
        patch("app.main.get_chunk_count", return_value=0),
    ):
        with TestClient(app) as c:
            yield c


_MOCK_SEARCH_RESULT = {
    "documents": [["返金ポリシーについて説明します。"]],
    "metadatas": [[{"document_name": "policy.txt", "category": "faq"}]],
    "distances": [[0.15]],
}


class TestQueryEndpoint:
    """POST /api/query エンドポイントのテスト"""

    def test_query_success(self, client):
        """正常なクエリで200と回答を返す"""
        with (
            patch("app.routers.query.search", return_value=_MOCK_SEARCH_RESULT),
            patch(
                "app.routers.query.generate_answer",
                return_value=("返金は7日以内に承ります。", False, None),
            ),
        ):
            resp = client.post("/api/query", json={"query": "返金ポリシーを教えてください"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "返金は7日以内に承ります。"
        assert data["should_escalate"] is False
        assert data["escalation_reason"] is None
        assert len(data["sources"]) == 1
        assert data["sources"][0]["document_name"] == "policy.txt"

    def test_query_with_escalation(self, client):
        """エスカレーションが必要なクエリは should_escalate=True を返す"""
        with (
            patch("app.routers.query.search", return_value=_MOCK_SEARCH_RESULT),
            patch(
                "app.routers.query.generate_answer",
                return_value=("担当者へご確認ください。", True, "法的判断が必要なケースです"),
            ),
        ):
            resp = client.post("/api/query", json={"query": "訴訟について教えてください"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["should_escalate"] is True
        assert "法的判断" in data["escalation_reason"]

    def test_query_tone_polite(self, client):
        """politeトーンを指定して正常応答"""
        with (
            patch("app.routers.query.search", return_value=_MOCK_SEARCH_RESULT),
            patch(
                "app.routers.query.generate_answer",
                return_value=("丁寧な回答です。", False, None),
            ) as mock_generate,
        ):
            resp = client.post(
                "/api/query",
                json={"query": "商品の交換方法を教えてください", "tone": "polite"},
            )

        assert resp.status_code == 200
        mock_generate.assert_called_once()
        call_kwargs = mock_generate.call_args.kwargs
        assert call_kwargs["tone"] == "polite"

    def test_query_tone_concise(self, client):
        """conciseトーンを指定して正常応答"""
        with (
            patch("app.routers.query.search", return_value=_MOCK_SEARCH_RESULT),
            patch(
                "app.routers.query.generate_answer",
                return_value=("簡潔な回答。", False, None),
            ) as mock_generate,
        ):
            resp = client.post(
                "/api/query",
                json={"query": "配送日数は？", "tone": "concise"},
            )

        assert resp.status_code == 200
        call_kwargs = mock_generate.call_args.kwargs
        assert call_kwargs["tone"] == "concise"

    def test_query_empty_string_rejected(self, client):
        """空文字列のクエリは422で拒否される"""
        resp = client.post("/api/query", json={"query": ""})
        assert resp.status_code == 422

    def test_query_whitespace_only_rejected(self, client):
        """空白のみのクエリは422で拒否される"""
        resp = client.post("/api/query", json={"query": "   "})
        assert resp.status_code == 422

    def test_query_too_long_rejected(self, client):
        """5001文字を超えるクエリは422で拒否される"""
        resp = client.post("/api/query", json={"query": "あ" * 5001})
        assert resp.status_code == 422

    def test_query_invalid_tone_rejected(self, client):
        """無効なトーン値は422で拒否される"""
        resp = client.post("/api/query", json={"query": "テスト", "tone": "casual"})
        assert resp.status_code == 422

    def test_query_vectorstore_error_returns_503(self, client):
        """ベクトルストア接続エラー時は503を返す"""
        with patch("app.routers.query.search", side_effect=Exception("DB接続エラー")):
            resp = client.post("/api/query", json={"query": "テスト問い合わせ"})

        assert resp.status_code == 503
        assert "ベクトルデータベース" in resp.json()["detail"]

    def test_query_openai_error_returns_503(self, client):
        """OpenAI APIエラー時は503を返す"""
        with (
            patch("app.routers.query.search", return_value=_MOCK_SEARCH_RESULT),
            patch(
                "app.routers.query.generate_answer",
                side_effect=OpenAIError("API接続エラー"),
            ),
        ):
            resp = client.post("/api/query", json={"query": "テスト問い合わせ"})

        assert resp.status_code == 503
        assert "AI回答生成" in resp.json()["detail"]

    def test_query_unexpected_error_returns_500(self, client):
        """予期しないエラー時は500を返す"""
        with (
            patch("app.routers.query.search", return_value=_MOCK_SEARCH_RESULT),
            patch(
                "app.routers.query.generate_answer",
                side_effect=RuntimeError("予期しないエラー"),
            ),
        ):
            resp = client.post("/api/query", json={"query": "テスト問い合わせ"})

        assert resp.status_code == 500

    def test_query_relevance_score_calculated(self, client):
        """relevance_scoreがdistanceから正しく計算される"""
        mock_result = {
            "documents": [["内容"]],
            "metadatas": [[{"document_name": "doc.txt", "category": "manual"}]],
            "distances": [[0.3]],
        }
        with (
            patch("app.routers.query.search", return_value=mock_result),
            patch(
                "app.routers.query.generate_answer",
                return_value=("回答", False, None),
            ),
        ):
            resp = client.post("/api/query", json={"query": "テスト"})

        assert resp.status_code == 200
        source = resp.json()["sources"][0]
        assert abs(source["relevance_score"] - 0.7) < 0.001

    def test_query_empty_vectorstore_results(self, client):
        """ベクトルストアが空の結果を返した場合も正常応答"""
        empty_result = {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        with (
            patch("app.routers.query.search", return_value=empty_result),
            patch(
                "app.routers.query.generate_answer",
                return_value=("情報が見つかりませんでした。", True, "参照文書がありません"),
            ),
        ):
            resp = client.post("/api/query", json={"query": "テスト"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["sources"] == []
        assert data["should_escalate"] is True

    def test_query_multiple_sources(self, client):
        """複数のソース文書を含む検索結果が正しくレスポンスに反映される"""
        multi_result = {
            "documents": [["内容1", "内容2", "内容3"]],
            "metadatas": [
                [
                    {"document_name": "a.txt", "category": "faq"},
                    {"document_name": "b.txt", "category": "manual"},
                    {"document_name": "c.txt", "category": "terms"},
                ]
            ],
            "distances": [[0.1, 0.2, 0.4]],
        }
        with (
            patch("app.routers.query.search", return_value=multi_result),
            patch(
                "app.routers.query.generate_answer",
                return_value=("総合回答", False, None),
            ),
        ):
            resp = client.post("/api/query", json={"query": "テスト"})

        assert resp.status_code == 200
        sources = resp.json()["sources"]
        assert len(sources) == 3
        assert sources[0]["document_name"] == "a.txt"
        assert sources[1]["document_name"] == "b.txt"
        assert sources[2]["document_name"] == "c.txt"

    def test_query_missing_body_rejected(self, client):
        """リクエストボディなしは422で拒否される"""
        resp = client.post("/api/query")
        assert resp.status_code == 422


class TestHealthEndpoint:
    """GET /api/health エンドポイントのテスト"""

    def test_health_ok(self, client):
        """DBが接続できる場合はstatus=okを返す"""
        with patch("app.main.get_chunk_count", return_value=42):
            resp = client.get("/api/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["vector_db"] == "connected"
        assert data["document_chunks"] == 42

    def test_health_degraded_on_db_error(self, client):
        """DB接続エラー時はstatus=degradedを返す"""
        with patch("app.main.get_chunk_count", side_effect=Exception("接続失敗")):
            resp = client.get("/api/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["vector_db"] == "disconnected"
