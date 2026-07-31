"""app.services.embeddings のユニットテスト。

OpenAI SDK 呼び出しは monkeypatch でスタブ化し、
外部 API に依存しないローカル実行のみで完結させる。
"""

from types import SimpleNamespace

import pytest

from app.services import embeddings


@pytest.fixture(autouse=True)
def _reset_client_singleton():
    """テスト間で `_client` シングルトンを持ち越さない。

    `get_client` が返す OpenAI クライアントは module 変数に保持されるため、
    fixture の scope=function として各テスト前後で必ずリセットする。
    """
    embeddings._client = None
    yield
    embeddings._client = None


class _FakeUsage:
    def __init__(self, total_tokens: int) -> None:
        self.total_tokens = total_tokens


class _FakeEmbeddings:
    """`OpenAI.embeddings.create` を差し替えるためのフェイク。

    渡された `input` のサイズに合わせて data を返し、
    入力を最後の呼び出し引数として `last_call` に記録する。
    """

    def __init__(self) -> None:
        self.last_call: dict | None = None

    def create(self, *, model: str, input: list[str]):
        self.last_call = {"model": model, "input": input}
        data = [SimpleNamespace(embedding=[float(i), float(i) + 0.5]) for i, _ in enumerate(input)]
        return SimpleNamespace(data=data, usage=_FakeUsage(total_tokens=len(input) * 3))


class _FakeClient:
    def __init__(self) -> None:
        self.embeddings = _FakeEmbeddings()


def test_get_client_is_singleton(monkeypatch):
    """`get_client` は一度作成した OpenAI クライアントを再利用する。"""
    created: list[_FakeClient] = []

    def _factory():
        client = _FakeClient()
        created.append(client)
        return client

    monkeypatch.setattr(embeddings, "OpenAI", _factory)
    first = embeddings.get_client()
    second = embeddings.get_client()

    assert first is second
    assert len(created) == 1


def test_generate_embeddings_returns_vectors(monkeypatch):
    """`generate_embeddings` は SDK レスポンスから embedding 配列だけを抽出する。"""
    fake_client = _FakeClient()
    monkeypatch.setattr(embeddings, "OpenAI", lambda: fake_client)

    vectors = embeddings.generate_embeddings(["こんにちは", "テスト", "hello"])

    assert vectors == [[0.0, 0.5], [1.0, 1.5], [2.0, 2.5]]
    assert fake_client.embeddings.last_call == {
        "model": "text-embedding-3-small",
        "input": ["こんにちは", "テスト", "hello"],
    }


def test_generate_embeddings_empty_input(monkeypatch):
    """入力が空のときは空配列を返す（SDK 呼び出しは行われる）。"""
    fake_client = _FakeClient()
    monkeypatch.setattr(embeddings, "OpenAI", lambda: fake_client)

    vectors = embeddings.generate_embeddings([])

    assert vectors == []
    assert fake_client.embeddings.last_call == {
        "model": "text-embedding-3-small",
        "input": [],
    }


def test_generate_embedding_single(monkeypatch):
    """`generate_embedding` は `generate_embeddings` の 1 件版として最初の要素を返す。"""
    fake_client = _FakeClient()
    monkeypatch.setattr(embeddings, "OpenAI", lambda: fake_client)

    vector = embeddings.generate_embedding("単一テキスト")

    assert vector == [0.0, 0.5]
    assert fake_client.embeddings.last_call == {
        "model": "text-embedding-3-small",
        "input": ["単一テキスト"],
    }
