"""Pydantic models for request/response schemas."""

from typing import Literal

from pydantic import BaseModel, field_validator

Tone = Literal["polite", "concise", "standard"]


class QueryRequest(BaseModel):
    """問い合わせリクエスト"""
    query: str
    tone: Tone = "standard"

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("問い合わせ文を入力してください")
        if len(v) > 5000:
            raise ValueError("問い合わせ文は5000文字以内で入力してください")
        return v.strip()


class SourceDocument(BaseModel):
    """参照元ドキュメント"""
    content: str
    document_name: str
    category: str
    relevance_score: float


class QueryResponse(BaseModel):
    """回答候補レスポンス"""
    answer: str
    sources: list[SourceDocument]
    should_escalate: bool
    escalation_reason: str | None = None


class DocumentInfo(BaseModel):
    """ドキュメント情報"""
    id: str
    name: str
    category: str
    chunk_count: int
    uploaded_at: str


class DocumentListResponse(BaseModel):
    """ドキュメント一覧レスポンス"""
    documents: list[DocumentInfo]
    total: int
