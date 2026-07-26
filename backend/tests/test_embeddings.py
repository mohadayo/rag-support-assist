"""embeddings.py のユニットテスト"""
import sys
from unittest.mock import MagicMock, patch

# 外部依存を事前にモック化（他テストより先に実行される場合に備えて）
sys.modules.setdefault("psycopg2", MagicMock())
_openai_mod = MagicMock()
sys.modules.setdefault("openai", _openai_mod)
_openai_mod.OpenAI = MagicMock

import pytest  # noqa: E402

import app.services.embeddings as embeddings_module  # noqa: E402


@pytest.fixture(autouse=True)
def reset_client_singleton():
    """テスト間で _client のシングルトン状態が漏れないようにリセットする"""
    embeddings_module._client = None
    yield
    embeddings_module._client = None


class TestGetClient:
    def test_returns_singleton_instance(self):
        """2回呼び出しても同一インスタンスが返ること"""
        with patch.object(embeddings_module, "OpenAI") as mock_openai_cls:
            mock_openai_cls.return_value = MagicMock()

            client1 = embeddings_module.get_client()
            client2 = embeddings_module.get_client()

        assert client1 is client2
        mock_openai_cls.assert_called_once()

    def test_creates_instance_only_once(self):
        """OpenAI() のコンストラクタが1回しか呼ばれないこと"""
        with patch.object(embeddings_module, "OpenAI") as mock_openai_cls:
            mock_openai_cls.return_value = MagicMock()
            embeddings_module.get_client()
            embeddings_module.get_client()
        mock_openai_cls.assert_called_once_with()


def _make_embedding_response(vectors):
    """OpenAI embeddings.create() のレスポンスを模したモックを生成する"""
    response = MagicMock()
    response.data = [MagicMock(embedding=v) for v in vectors]
    response.usage.total_tokens = 42
    return response


class TestGenerateEmbeddings:
    def test_calls_api_with_correct_model_and_input(self):
        """text-embedding-3-small モデルと入力テキストでAPIが呼ばれること"""
        fake_client = MagicMock()
        fake_client.embeddings.create.return_value = _make_embedding_response(
            [[0.1, 0.2], [0.3, 0.4]]
        )

        with patch.object(embeddings_module, "get_client", return_value=fake_client):
            result = embeddings_module.generate_embeddings(["テキスト1", "テキスト2"])

        fake_client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input=["テキスト1", "テキスト2"],
        )
        assert result == [[0.1, 0.2], [0.3, 0.4]]

    def test_returns_empty_list_for_empty_input(self):
        """空リストを渡した場合は空リストが返ること"""
        fake_client = MagicMock()
        fake_client.embeddings.create.return_value = _make_embedding_response([])

        with patch.object(embeddings_module, "get_client", return_value=fake_client):
            result = embeddings_module.generate_embeddings([])

        assert result == []

    def test_preserves_order_of_returned_embeddings(self):
        """レスポンスの順序通りに embedding が並ぶこと"""
        fake_client = MagicMock()
        fake_client.embeddings.create.return_value = _make_embedding_response(
            [[1.0], [2.0], [3.0]]
        )

        with patch.object(embeddings_module, "get_client", return_value=fake_client):
            result = embeddings_module.generate_embeddings(["a", "b", "c"])

        assert result == [[1.0], [2.0], [3.0]]


class TestGenerateEmbedding:
    def test_returns_first_embedding_from_generate_embeddings(self):
        """generate_embeddings() を単一要素リストで呼び出し、先頭要素を返すこと"""
        with patch.object(
            embeddings_module, "generate_embeddings", return_value=[[9.9, 8.8]]
        ) as mock_generate:
            result = embeddings_module.generate_embedding("単一テキスト")

        mock_generate.assert_called_once_with(["単一テキスト"])
        assert result == [9.9, 8.8]
