"""OpenAI Embedding生成サービス"""

import logging
import os
import time

from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)

OPENAI_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "30"))

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
        logger.info("OpenAIクライアントを初期化しました")
    return _client


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """テキストリストのEmbeddingを生成する"""
    client = get_client()
    logger.info("Embedding生成開始: %d件のテキスト", len(texts))
    start_time = time.time()
    try:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
            timeout=OPENAI_TIMEOUT,
        )
    except OpenAIError as e:
        elapsed = time.time() - start_time
        logger.error(
            "Embedding生成中にOpenAIエラーが発生: error=%s, elapsed=%.2fs, texts=%d件",
            e, elapsed, len(texts),
        )
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logger.exception(
            "Embedding生成中に予期しないエラーが発生: error=%s, elapsed=%.2fs", e, elapsed,
        )
        raise

    elapsed = time.time() - start_time
    logger.info(
        "Embedding生成完了: %d件, usage=%d tokens, elapsed=%.2fs",
        len(response.data), response.usage.total_tokens, elapsed,
    )
    return [item.embedding for item in response.data]


def generate_embedding(text: str) -> list[float]:
    """単一テキストのEmbeddingを生成する"""
    return generate_embeddings([text])[0]
