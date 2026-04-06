"""models.py のバリデーションテスト"""

import pytest
from pydantic import ValidationError

from app.models import QueryRequest, SourceDocument, QueryResponse, DocumentInfo, DocumentListResponse


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
