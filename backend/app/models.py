"""Pydantic models for request/response schemas."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

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
        # NUL バイトは正当な問い合わせ文に含まれる余地が無く、ログ出力時の
        # truncation やログ基盤 (Elasticsearch / fluentd 等) での解析失敗の
        # 原因となる。`documents.py::_validate_filename` と揃った多層防御の
        # 一環として、API の入り口で明示的に拒否する。
        # なお `\t` / `\r` / `\n` は複数行の問い合わせ本文として正当に
        # 使われうるため、ここでは NUL のみに限定して許容範囲を広く取る
        # (ファイル名バリデータとは要件が異なる)。
        if "\x00" in v:
            raise ValueError("問い合わせ文に NUL バイトは使用できません")
        return v.strip()


class SourceDocument(BaseModel):
    """参照元ドキュメント"""
    content: str
    document_name: str
    category: str
    # `relevance_score` は `query.py` 側で `max(0.0, 1.0 - cosine距離)` として
    # 算出されるため、常に [0.0, 1.0] に収まる契約を持つ。Pydantic の Field
    # 制約で範囲外の値を早期に弾くことで、将来 ingest / search ロジックが
    # 変わってもサイレントに契約が崩れないようにする（多層防御）。
    relevance_score: float = Field(ge=0.0, le=1.0)


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
    # チャンク数は論理上非負（0 件登録のケースは有効）。負値はベクトル
    # ストア側のバグを示唆するため、レスポンス境界でも早期に検出する。
    chunk_count: int = Field(ge=0)
    uploaded_at: str


class DocumentListResponse(BaseModel):
    """ドキュメント一覧レスポンス"""
    documents: list[DocumentInfo]
    # ページング前の総数。`chunk_count` と同じ理由で非負を強制する。
    total: int = Field(ge=0)
