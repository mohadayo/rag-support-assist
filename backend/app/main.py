"""FastAPI エントリポイント"""

import logging
import os
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .routers import query, documents
from .services.vectorstore import migrate, get_chunk_count

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate()
    logger.info("データベースマイグレーション完了")
    yield


app = FastAPI(
    title="RAG Support Assist API",
    description="カスタマーサポート回答支援AI バックエンドAPI",
    version="0.1.0",
    lifespan=lifespan,
)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        logger.info(
            "%s %s %d %.1fms",
            request.method, request.url.path, response.status_code, duration_ms,
        )
        return response


app.add_middleware(RequestLoggingMiddleware)

app.include_router(query.router)
app.include_router(documents.router)


@app.get("/api/health")
async def health():
    """ヘルスチェック（DB接続確認付き）"""
    try:
        doc_count = get_chunk_count()
        return {"status": "ok", "vector_db": "connected", "document_chunks": doc_count}
    except Exception:
        logger.exception("データベース接続エラー")
        return {"status": "degraded", "vector_db": "disconnected"}
