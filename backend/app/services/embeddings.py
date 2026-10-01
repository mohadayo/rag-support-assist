"""OpenAI Embedding生成サービス"""

import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)

# 使用する Embedding モデル名。環境変数 EMBEDDING_MODEL で変更可能
# （デフォルト: text-embedding-3-small）。`rag.py` の `RAG_MODEL` と同じ運用で、
# 本番環境では精度を優先した上位モデル（例: `text-embedding-3-large`）に
# 切り替えられるようにする。モデルを変更すると既存チャンクの埋め込み次元が
# 変わり得るため、変更時は再 ingest が必要であることを運用側に明示する
# （README / docs 側で案内）。
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def _get_embedding_model() -> str:
    """環境変数 EMBEDDING_MODEL から Embedding モデル名を取得する。

    空文字・未設定は `DEFAULT_EMBEDDING_MODEL` にフォールバックする。
    モジュール読み込み時ではなく呼び出し時に評価することで、テスト間で
    `monkeypatch.setenv` した値がそのまま効く（`rag.py` 側の環境変数
    getter と同じ姿勢）。
    """
    value = os.getenv("EMBEDDING_MODEL", "").strip()
    return value or DEFAULT_EMBEDDING_MODEL


_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """テキストリストのEmbeddingを生成する"""
    client = get_client()
    model = _get_embedding_model()
    logger.info("Embedding生成開始: %d件のテキスト (model=%s)", len(texts), model)
    response = client.embeddings.create(
        model=model,
        input=texts,
    )
    logger.info("Embedding生成完了: %d件, usage=%d tokens", len(response.data), response.usage.total_tokens)
    return [item.embedding for item in response.data]


def generate_embedding(text: str) -> list[float]:
    """単一テキストのEmbeddingを生成する"""
    return generate_embeddings([text])[0]
