"""ChromaDBベクトルストア操作"""

import os
import chromadb
from chromadb.config import Settings

from .embeddings import generate_embeddings, generate_embedding

_client: chromadb.ClientAPI | None = None
COLLECTION_NAME = "support_documents"


def get_chroma_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
        _client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def get_collection() -> chromadb.Collection:
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def add_documents(
    doc_id: str,
    chunks: list[str],
    document_name: str,
    category: str,
) -> int:
    """チャンクをベクトルストアに追加する"""
    if not chunks:
        return 0

    collection = get_collection()
    embeddings = generate_embeddings(chunks)

    ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "document_id": doc_id,
            "document_name": document_name,
            "category": category,
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=chunks,
        metadatas=metadatas,
    )
    return len(chunks)


def search(query: str, n_results: int = 5) -> dict:
    """クエリに類似するドキュメントを検索する"""
    collection = get_collection()

    if collection.count() == 0:
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    query_embedding = generate_embedding(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    return results


def delete_document(doc_id: str) -> int:
    """ドキュメントIDに紐づくチャンクを全て削除する"""
    collection = get_collection()
    # doc_idに紐づくチャンクを検索
    results = collection.get(
        where={"document_id": doc_id},
        include=[],
    )
    if results["ids"]:
        collection.delete(ids=results["ids"])
    return len(results["ids"])


def get_document_stats() -> list[dict]:
    """登録済みドキュメントの統計情報を取得する"""
    collection = get_collection()
    all_data = collection.get(include=["metadatas"])

    doc_map: dict[str, dict] = {}
    for meta in all_data["metadatas"]:
        did = meta["document_id"]
        if did not in doc_map:
            doc_map[did] = {
                "id": did,
                "name": meta["document_name"],
                "category": meta["category"],
                "chunk_count": 0,
            }
        doc_map[did]["chunk_count"] += 1

    return list(doc_map.values())
