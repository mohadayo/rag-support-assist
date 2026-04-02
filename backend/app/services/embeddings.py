"""OpenAI Embedding生成サービス"""

import logging

from openai import OpenAI

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """テキストリストのEmbeddingを生成する"""
    client = get_client()
    logger.info("Embedding生成開始: %d件のテキスト", len(texts))
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    logger.info("Embedding生成完了: %d件, usage=%d tokens", len(response.data), response.usage.total_tokens)
    return [item.embedding for item in response.data]


def generate_embedding(text: str) -> list[float]:
    """単一テキストのEmbeddingを生成する"""
    return generate_embeddings([text])[0]
