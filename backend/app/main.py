"""FastAPI エントリポイント"""

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import query, documents

app = FastAPI(
    title="RAG Support Assist API",
    description="カスタマーサポート回答支援AI バックエンドAPI",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router)
app.include_router(documents.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
