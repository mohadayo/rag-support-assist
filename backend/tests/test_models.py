"""models.py のバリデーションテスト"""

import pytest
from pydantic import ValidationError

from app.models import (
    DocumentInfo,
    DocumentListResponse,
    QueryRequest,
    QueryResponse,
    SourceDocument,
)


class TestQueryRequest:
    """QueryRequest モデルのバリデーションテスト"""

    def test_valid_query(self):
        """有効な問い合わせは正常に作成される"""
        req = QueryRequest(query="注文をキャンセルしたいです", tone="standard")
        assert req.query == "注文をキャンセルしたいです"
        assert req.tone == "standard"

    def test_default_tone_is_standard(self):
        """デフォルトのトーンは standard"""
        req = QueryRequest(query="テスト")
        assert req.tone == "standard"

    def test_empty_query_raises_validation_error(self):
        """空文字列の問い合わせはバリデーションエラー"""
        with pytest.raises(ValidationError):
            QueryRequest(query="")

    def test_whitespace_only_query_raises_validation_error(self):
        """空白のみの問い合わせはバリデーションエラー"""
        with pytest.raises(ValidationError):
            QueryRequest(query="   ")

    def test_query_is_stripped(self):
        """問い合わせ文の前後の空白は除去される"""
        req = QueryRequest(query="  テスト問い合わせ  ")
        assert req.query == "テスト問い合わせ"

    def test_query_too_long_raises_validation_error(self):
        """5000文字を超える問い合わせはバリデーションエラー"""
        with pytest.raises(ValidationError):
            QueryRequest(query="あ" * 5001)

    def test_query_at_max_length(self):
        """5000文字の問い合わせは有効"""
        req = QueryRequest(query="あ" * 5000)
        assert len(req.query) == 5000

    def test_invalid_tone_raises_validation_error(self):
        """無効なトーン値はバリデーションエラー"""
        with pytest.raises(ValidationError):
            QueryRequest(query="テスト", tone="casual")

    def test_valid_tones(self):
        """有効なトーン値はすべて受け付ける"""
        for tone in ["polite", "concise", "standard"]:
            req = QueryRequest(query="テスト", tone=tone)
            assert req.tone == tone


class TestSourceDocument:
    """SourceDocument モデルのテスト"""

    def test_valid_source_document(self):
        """有効なソースドキュメントは正常に作成される"""
        doc = SourceDocument(
            content="テストコンテンツ",
            document_name="test.txt",
            category="faq",
            relevance_score=0.95,
        )
        assert doc.content == "テストコンテンツ"
        assert doc.relevance_score == 0.95


class TestDocumentInfo:
    """DocumentInfo モデルのテスト"""

    def test_valid_document_info(self):
        """有効なドキュメント情報は正常に作成される"""
        info = DocumentInfo(
            id="test-id-123",
            name="sample.txt",
            category="manual",
            chunk_count=10,
            uploaded_at="2024-01-01T00:00:00+00:00",
        )
        assert info.id == "test-id-123"
        assert info.chunk_count == 10


class TestQueryResponse:
    """QueryResponse モデルのテスト

    API のトップレベル応答型のため、フィールド構成の契約変更が起きると
    フロントエンドが静かに壊れる。必須／任意の区分・デフォルト値・
    ネストされた SourceDocument リストの受理を回帰する。
    """

    def _sample_source(self) -> SourceDocument:
        return SourceDocument(
            content="返品は到着から 7 日以内に受け付けます。",
            document_name="returns.md",
            category="policy",
            relevance_score=0.82,
        )

    def test_valid_response_without_escalation(self):
        """エスカレーション不要ケースの最小構成が受理される"""
        resp = QueryResponse(
            answer="返品期限は 7 日間です。",
            sources=[self._sample_source()],
            should_escalate=False,
        )
        assert resp.answer == "返品期限は 7 日間です。"
        assert len(resp.sources) == 1
        assert resp.should_escalate is False
        # `escalation_reason` は省略時に None がデフォルト
        assert resp.escalation_reason is None

    def test_valid_response_with_escalation(self):
        """エスカレーション必要ケース（reason 付き）が受理される"""
        resp = QueryResponse(
            answer="担当者からご連絡します。",
            sources=[],
            should_escalate=True,
            escalation_reason="ナレッジベースに該当情報がありません",
        )
        assert resp.should_escalate is True
        assert resp.escalation_reason == "ナレッジベースに該当情報がありません"

    def test_sources_default_is_not_allowed_missing(self):
        """`sources` は必須フィールド（デフォルト値なし）"""
        with pytest.raises(ValidationError):
            QueryResponse(  # type: ignore[call-arg]
                answer="a",
                should_escalate=False,
            )

    def test_answer_missing_raises_validation_error(self):
        """`answer` は必須フィールド"""
        with pytest.raises(ValidationError):
            QueryResponse(  # type: ignore[call-arg]
                sources=[],
                should_escalate=False,
            )

    def test_should_escalate_missing_raises_validation_error(self):
        """`should_escalate` は必須フィールド（デフォルト値を持たない）"""
        with pytest.raises(ValidationError):
            QueryResponse(  # type: ignore[call-arg]
                answer="a",
                sources=[],
            )

    def test_sources_accepts_dict_input(self):
        """`sources` は dict でも SourceDocument へ自動変換される（Pydantic v2 の挙動）"""
        resp = QueryResponse(
            answer="dummy",
            sources=[
                {
                    "content": "c",
                    "document_name": "d.md",
                    "category": "faq",
                    "relevance_score": 0.5,
                }
            ],
            should_escalate=False,
        )
        assert len(resp.sources) == 1
        assert isinstance(resp.sources[0], SourceDocument)
        assert resp.sources[0].document_name == "d.md"


class TestDocumentListResponse:
    """DocumentListResponse モデルのテスト

    ドキュメント一覧 API のレスポンス型。`total` と `documents` の長さは
    独立して指定できる契約（`total` はページング前の総数用途）。
    """

    def test_valid_document_list_response(self):
        """代表的な有効値でインスタンス化できる"""
        info = DocumentInfo(
            id="1",
            name="a.md",
            category="faq",
            chunk_count=3,
            uploaded_at="2026-08-17T00:00:00+00:00",
        )
        resp = DocumentListResponse(documents=[info], total=1)
        assert resp.total == 1
        assert len(resp.documents) == 1
        assert resp.documents[0].id == "1"

    def test_empty_document_list_is_valid(self):
        """documents は空リストでも有効"""
        resp = DocumentListResponse(documents=[], total=0)
        assert resp.documents == []
        assert resp.total == 0

    def test_total_can_differ_from_documents_length(self):
        """`total` はページング前の総数なので `len(documents)` と一致しなくてよい"""
        info = DocumentInfo(
            id="1",
            name="a.md",
            category="faq",
            chunk_count=1,
            uploaded_at="2026-08-17T00:00:00+00:00",
        )
        resp = DocumentListResponse(documents=[info], total=42)
        assert resp.total == 42
        assert len(resp.documents) == 1

    def test_documents_missing_raises_validation_error(self):
        """`documents` は必須フィールド"""
        with pytest.raises(ValidationError):
            DocumentListResponse(total=0)  # type: ignore[call-arg]

    def test_total_missing_raises_validation_error(self):
        """`total` は必須フィールド"""
        with pytest.raises(ValidationError):
            DocumentListResponse(documents=[])  # type: ignore[call-arg]
