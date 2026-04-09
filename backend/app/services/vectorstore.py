"""pgvectorベクトルストア操作"""

import logging
import os
from contextlib import contextmanager

import psycopg2

from .embeddings import generate_embeddings, generate_embedding

logger = logging.getLogger(__name__)


def _get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is required")
    return url


@contextmanager
def _get_connection():
    conn = psycopg2.connect(_get_database_url())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate():
    """テーブルとpgvector拡張を初期化する"""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector(1536) NOT NULL
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_document_id
                ON document_chunks(document_id)
            """)
    logger.info("データベースマイグレーション完了")


def add_documents(
    doc_id: str,
    chunks: list[str],
    document_name: str,
    category: str,
) -> int:
    """チャンクをベクトルストアに追加する"""
    if not chunks:
        logger.info("空のチャンクリスト: doc_id=%s, document_name=%s", doc_id, document_name)
        return 0

    logger.info(
        "ドキュメント追加開始: doc_id=%s, document_name=%s, category=%s, chunks=%d",
        doc_id, document_name, category, len(chunks),
    )
    embeddings = generate_embeddings(chunks)

    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO documents (id, name, category) VALUES (%s, %s, %s)",
                (doc_id, document_name, category),
            )
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_id = f"{doc_id}_chunk_{i}"
                cur.execute(
                    """INSERT INTO document_chunks (id, document_id, chunk_index, content, embedding)
                       VALUES (%s, %s, %s, %s, %s::vector)""",
                    (chunk_id, doc_id, i, chunk, str(embedding)),
                )

    logger.info("ドキュメント追加完了: doc_id=%s, %d件のチャンクを登録", doc_id, len(chunks))
    return len(chunks)


def search(query: str, n_results: int = 5) -> dict:
    """クエリに類似するドキュメントを検索する"""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM document_chunks")
            count = cur.fetchone()[0]
            if count == 0:
                logger.info("ベクトル検索: テーブルが空のためスキップ")
                return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

            logger.info("ベクトル検索開始: n_results=%d, chunk_count=%d", n_results, count)
            query_embedding = generate_embedding(query)
            embedding_str = str(query_embedding)

            cur.execute(
                """SELECT dc.content, d.name, d.category,
                          dc.embedding <=> %s::vector AS distance
                   FROM document_chunks dc
                   JOIN documents d ON dc.document_id = d.id
                   ORDER BY dc.embedding <=> %s::vector
                   LIMIT %s""",
                (embedding_str, embedding_str, min(n_results, count)),
            )
            rows = cur.fetchall()

    documents = []
    metadatas = []
    distances = []
    for content, doc_name, category, distance in rows:
        documents.append(content)
        metadatas.append({"document_name": doc_name, "category": category})
        distances.append(float(distance))

    logger.info("ベクトル検索完了: %d件ヒット", len(documents))
    return {
        "documents": [documents],
        "metadatas": [metadatas],
        "distances": [distances],
    }


def delete_document(doc_id: str) -> int:
    """ドキュメントIDに紐づくチャンクを全て削除する"""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM document_chunks WHERE document_id = %s",
                (doc_id,),
            )
            count = cur.fetchone()[0]

            if count > 0:
                cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
                logger.info("ドキュメント削除完了: doc_id=%s, %d件のチャンクを削除", doc_id, count)
            else:
                logger.info("ドキュメント削除: doc_id=%s に該当するチャンクなし", doc_id)

    return count


def get_document_stats() -> list[dict]:
    """登録済みドキュメントの統計情報を取得する"""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT d.id, d.name, d.category, d.uploaded_at, COUNT(dc.id) AS chunk_count
                FROM documents d
                LEFT JOIN document_chunks dc ON d.id = dc.document_id
                GROUP BY d.id, d.name, d.category, d.uploaded_at
                ORDER BY d.uploaded_at DESC
            """)
            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "name": row[1],
            "category": row[2],
            "uploaded_at": row[3].isoformat() if row[3] else "",
            "chunk_count": row[4],
        }
        for row in rows
    ]


def get_chunk_count() -> int:
    """登録済みチャンクの総数を返す"""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM document_chunks")
            return cur.fetchone()[0]
