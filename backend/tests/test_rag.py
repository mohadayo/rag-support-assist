"""rag.py の RAG_MODEL 環境変数サポートのユニットテスト"""

import os
import sys
from unittest.mock import MagicMock

# openai を事前にモックして import エラーを防ぐ
_openai_mock = MagicMock()
sys.modules.setdefault("openai", _openai_mock)
_openai_mock.OpenAI = MagicMock

from app.services.rag import generate_answer  # noqa: E402


class TestRagModelDefaultValue:
    def test_rag_model_defaults_to_gpt4o_mini(self, monkeypatch):
        """RAG_MODEL 未設定時のデフォルト値を確認する。"""
        monkeypatch.delenv("RAG_MODEL", raising=False)
        result = os.getenv("RAG_MODEL", "gpt-4o-mini")
        assert result == "gpt-4o-mini"

    def test_rag_model_reads_env_var(self, monkeypatch):
        """RAG_MODEL 環境変数が設定されているとき、その値が返ること。"""
        monkeypatch.setenv("RAG_MODEL", "gpt-4o")
        result = os.getenv("RAG_MODEL", "gpt-4o-mini")
        assert result == "gpt-4o"

    def test_rag_model_custom_value(self, monkeypatch):
        monkeypatch.setenv("RAG_MODEL", "claude-sonnet-4-6")
        result = os.getenv("RAG_MODEL", "gpt-4o-mini")
        assert result == "claude-sonnet-4-6"


class TestGenerateAnswerEmptyContext:
    def test_returns_escalate_when_no_context(self):
        """コンテキストが空のとき、OpenAI を呼ばずにエスカレーションを返す。"""
        answer, should_escalate, reason = generate_answer(
            query="テスト問い合わせ",
            contexts=[],
        )
        assert should_escalate is True
        assert reason is not None
        assert "文書" in reason
        assert "登録されている文書に該当する情報が見つかりませんでした" in answer
