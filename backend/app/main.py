"""FastAPI エントリポイント"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import query, documents
from .services.vectorstore import get_collection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RAG Support Assist API",
    description="カスタマーサポート回答支援AI バックエンドAPI",
    version="0.1.0",
)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router)
app.include_router(documents.router)


@app.get("/api/health")
async def health():
    """ヘルスチェック（ベクトルDB接続確認付き）"""
    try:
        collection = get_collection()
        doc_count = collection.count()
        return {"status": "ok", "vector_db": "connected", "document_chunks": doc_count}
    except Exception:
        logger.exception("ベクトルDB接続エラー")
        return {"status": "degraded", "vector_db": "disconnected"}
