"""問い合わせAPI"""

from fastapi import APIRouter

from ..models import QueryRequest, QueryResponse, SourceDocument
from ..services.vectorstore import search
from ..services.rag import generate_answer

router = APIRouter(prefix="/api", tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def handle_query(request: QueryRequest):
    """問い合わせ文を受け取り、RAGで回答候補を生成する"""
    # ベクトル検索
    results = search(request.query, n_results=5)

    # コンテキスト構築
    contexts = []
    sources = []
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for doc, meta, dist in zip(documents, metadatas, distances):
        relevance = max(0.0, 1.0 - dist)  # cosine距離をスコアに変換
        contexts.append({
            "content": doc,
            "document_name": meta["document_name"],
            "category": meta["category"],
        })
        sources.append(SourceDocument(
            content=doc,
            document_name=meta["document_name"],
            category=meta["category"],
            relevance_score=round(relevance, 3),
        ))

    # RAG回答生成
    answer, should_escalate, escalation_reason = generate_answer(
        query=request.query,
        contexts=contexts,
        tone=request.tone,
    )

    return QueryResponse(
        answer=answer,
        sources=sources,
        should_escalate=should_escalate,
        escalation_reason=escalation_reason,
    )
