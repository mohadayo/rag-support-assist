"""問い合わせAPI"""

import logging
import os

from fastapi import APIRouter, HTTPException
from openai import OpenAIError

from ..models import QueryRequest, QueryResponse, SourceDocument
from ..services.vectorstore import search
from ..services.rag import generate_answer

logger = logging.getLogger(__name__)

SEARCH_N_RESULTS = int(os.getenv("SEARCH_N_RESULTS", "5"))

router = APIRouter(prefix="/api", tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def handle_query(request: QueryRequest):
    """問い合わせ文を受け取り、RAGで回答候補を生成する"""
    logger.info("問い合わせ受信: tone=%s, query=%s", request.tone, request.query[:80])

    # ベクトル検索
    try:
        results = search(request.query, n_results=SEARCH_N_RESULTS)
    except OpenAIError as e:
        logger.error("ベクトル検索中にOpenAIエラーが発生: %s", e)
        raise HTTPException(
            status_code=502,
            detail="検索用Embedding生成中にエラーが発生しました。しばらく経ってから再度お試しください。",
        )
    except Exception as e:
        logger.exception("ベクトル検索中に予期しないエラーが発生: %s", e)
        raise HTTPException(
            status_code=500,
            detail="検索処理中にエラーが発生しました。",
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
        logger.error("回答生成中にOpenAIエラーが発生: %s", e)
        raise HTTPException(
            status_code=502,
            detail="回答生成中にエラーが発生しました。しばらく経ってから再度お試しください。",
        )
    except Exception as e:
        logger.exception("回答生成中に予期しないエラーが発生: %s", e)
        raise HTTPException(
            status_code=500,
            detail="回答生成処理中にエラーが発生しました。",
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
