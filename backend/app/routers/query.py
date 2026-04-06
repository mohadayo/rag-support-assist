"""問い合わせAPI"""

import logging

from fastapi import APIRouter, HTTPException
from openai import OpenAIError

from ..models import QueryRequest, QueryResponse, SourceDocument
from ..services.vectorstore import search
from ..services.rag import generate_answer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def handle_query(request: QueryRequest):
    """問い合わせ文を受け取り、RAGで回答候補を生成する"""
    logger.info("問い合わせ受信: tone=%s, query=%s", request.tone, request.query[:80])

    # ベクトル検索
    try:
        results = search(request.query, n_results=5)
    except Exception:
        logger.exception("ベクトル検索中にエラーが発生しました")
        raise HTTPException(
            status_code=503,
            detail="ベクトルデータベースへの接続に失敗しました。しばらく経ってから再試行してください。",
        )

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
    try:
        answer, should_escalate, escalation_reason = generate_answer(
            query=request.query,
            contexts=contexts,
            tone=request.tone,
        )
    except OpenAIError as e:
        logger.error("OpenAI APIエラー: %s", e)
        raise HTTPException(
            status_code=503,
            detail="AI回答生成サービスに一時的な障害が発生しています。しばらく経ってから再試行してください。",
        )
    except Exception:
        logger.exception("回答生成中に予期しないエラーが発生しました")
        raise HTTPException(
            status_code=500,
            detail="回答の生成中にエラーが発生しました。",
        )

    logger.info(
        "問い合わせ応答完了: sources=%d件, escalate=%s",
        len(sources), should_escalate,
    )
    return QueryResponse(
        answer=answer,
        sources=sources,
        should_escalate=should_escalate,
        escalation_reason=escalation_reason,
    )
