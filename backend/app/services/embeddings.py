"""OpenAI Embedding生成サービス"""

from openai import OpenAI

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """テキストリストのEmbeddingを生成する"""
    client = get_client()
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [item.embedding for item in response.data]


def generate_embedding(text: str) -> list[float]:
    """単一テキストのEmbeddingを生成する"""
    return generate_embeddings([text])[0]
