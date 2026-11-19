"""FastAPI エントリポイント"""

import logging
import os
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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

# CORS で許可するオリジンのデフォルト値。ローカル開発時の Next.js dev
# サーバを想定している。環境変数 `CORS_ORIGINS` でカンマ区切り複数指定が可能。
DEFAULT_CORS_ORIGIN = "http://localhost:3000"


def _parse_cors_origins() -> list[str]:
    """環境変数 `CORS_ORIGINS` を解釈して許可オリジンのリストを返す。

    - カンマ区切りで複数指定可能。各要素は `strip()` して前後空白を除く。
    - 空文字・空白のみの要素は捨てる (`CORS_ORIGINS="a,,b"` / `"a,"` /
      `" , , "` のような誤設定で空 origin が許可されるのを防ぐ)。
    - 未設定・空文字・全要素が空白のいずれの場合も、`DEFAULT_CORS_ORIGIN`
      1 件へフォールバックする。これは `chunker._get_chunk_size` 等と揃った
      「安全側にデフォルト」の姿勢。
    """
    raw = os.getenv("CORS_ORIGINS")
    if raw is None:
        return [DEFAULT_CORS_ORIGIN]
    origins = [origin.strip() for origin in raw.split(",")]
    origins = [origin for origin in origins if origin]
    if not origins:
        return [DEFAULT_CORS_ORIGIN]
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
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


# 全応答に付与するセキュリティレスポンスヘッダ。
# JSON API サーバとして外部依存 (secure-headers 等) を追加せずに、
# starlette 標準の BaseHTTPMiddleware で以下を付ける:
#
# - `X-Content-Type-Options: nosniff` … JSON エンドポイントを別 MIME として
#   解釈させる MIME sniffing 攻撃を抑止。
# - `X-Frame-Options: DENY` … API を `<iframe>` に埋め込ませない。
#   JSON API はフレーム表示を意図しないため常時拒否 (clickjacking 対策)。
# - `Referrer-Policy: no-referrer` … 内部 URL やクエリ文字列がリンク先の
#   Referrer ヘッダとして外部に漏れないよう抑止。
#
# 既に同名ヘッダが設定されているレスポンス (テストや将来の per-route
# オーバーライド) は上書きしない — `setdefault` 相当の挙動を `headers.setdefault`
# ではなく `if key not in` で明示する（starlette の `MutableHeaders` にも
# `setdefault` はあるがコメント可読性のため展開）。
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for key, value in _SECURITY_HEADERS.items():
            if key not in response.headers:
                response.headers[key] = value
        return response


# `add_middleware` は LIFO で外側から積まれるため、SecurityHeaders を先に
# 追加すると、後から追加する RequestLogging より外側（応答経路の後段）に
# 位置する。両者はどちらも `call_next` の応答オブジェクトを触るだけなので
# 順序による副作用は無いが、ログには「セキュリティヘッダ付与後の最終応答」の
# ステータスがそのまま出るため、順序をここで固定しておく。
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(query.router)
app.include_router(documents.router)


@app.get("/api/health")
async def health():
    """ヘルスチェック（DB接続確認付き）

    DB 接続に失敗した場合は HTTP 503 を返し、LB や監視ツールが
    ステータスコードで異常を検出できるようにする。
    """
    try:
        doc_count = get_chunk_count()
        return {"status": "ok", "vector_db": "connected", "document_chunks": doc_count}
    except Exception:
        logger.exception("データベース接続エラー")
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "vector_db": "disconnected"},
        )
