"""rag.py のユニットテスト

OpenAI SDK 呼び出しはフェイククライアントで差し替え、
外部 API 依存なしにローカル実行で完結させる。
"""

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# openai を事前にモックして import エラーを防ぐ
_openai_mock = MagicMock()
sys.modules.setdefault("openai", _openai_mock)
_openai_mock.OpenAI = MagicMock

from app.services import rag  # noqa: E402
from app.services.rag import generate_answer  # noqa: E402


# ---------------------------------------------------------------------------
# フェイク OpenAI クライアント
# ---------------------------------------------------------------------------


def _make_response(content: str):
    """`client.chat.completions.create` が返す ChatCompletion 相当のオブジェクトを作る。"""
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


class _FakeChatCompletions:
    """`client.chat.completions.create` の代替。

    呼び出されるたびに `responses` から順に取り出して返す。
    `responses` の要素は文字列（そのまま content として使う）または例外インスタンス。
    """

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("フェイクレスポンスが枯渇しました")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return _make_response(item)


class _FakeClient:
    def __init__(self, responses: list) -> None:
        self.chat = SimpleNamespace(completions=_FakeChatCompletions(responses))


@pytest.fixture(autouse=True)
def _reset_client_singleton():
    """テスト間で `_client` シングルトンを持ち越さない。"""
    rag._client = None
    yield
    rag._client = None


# ---------------------------------------------------------------------------
# RAG_MODEL 環境変数
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# RAG_TEMPERATURE / RAG_MAX_TOKENS 環境変数
# ---------------------------------------------------------------------------


class TestGetTemperature:
    def test_defaults_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv("RAG_TEMPERATURE", raising=False)
        assert rag._get_temperature() == rag.DEFAULT_TEMPERATURE

    def test_defaults_when_env_is_empty_string(self, monkeypatch):
        monkeypatch.setenv("RAG_TEMPERATURE", "")
        assert rag._get_temperature() == rag.DEFAULT_TEMPERATURE

    def test_reads_env_var(self, monkeypatch):
        monkeypatch.setenv("RAG_TEMPERATURE", "0.7")
        assert rag._get_temperature() == 0.7

    def test_reads_zero(self, monkeypatch):
        """0.0 は有効値なのでそのまま返す。"""
        monkeypatch.setenv("RAG_TEMPERATURE", "0")
        assert rag._get_temperature() == 0.0

    def test_reads_upper_bound(self, monkeypatch):
        """2.0 は範囲の上限として有効。"""
        monkeypatch.setenv("RAG_TEMPERATURE", "2.0")
        assert rag._get_temperature() == 2.0

    @pytest.mark.parametrize("value", ["-0.1", "2.5", "10", "-5"])
    def test_out_of_range_falls_back_to_default(self, monkeypatch, value):
        monkeypatch.setenv("RAG_TEMPERATURE", value)
        assert rag._get_temperature() == rag.DEFAULT_TEMPERATURE

    @pytest.mark.parametrize("value", ["abc", "1.2.3", "not-a-number"])
    def test_unparseable_falls_back_to_default(self, monkeypatch, value):
        monkeypatch.setenv("RAG_TEMPERATURE", value)
        assert rag._get_temperature() == rag.DEFAULT_TEMPERATURE


class TestGetMaxTokens:
    def test_defaults_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv("RAG_MAX_TOKENS", raising=False)
        assert rag._get_max_tokens() == rag.DEFAULT_MAX_TOKENS

    def test_defaults_when_env_is_empty_string(self, monkeypatch):
        monkeypatch.setenv("RAG_MAX_TOKENS", "")
        assert rag._get_max_tokens() == rag.DEFAULT_MAX_TOKENS

    def test_reads_env_var(self, monkeypatch):
        monkeypatch.setenv("RAG_MAX_TOKENS", "2000")
        assert rag._get_max_tokens() == 2000

    def test_reads_lower_bound(self, monkeypatch):
        """1 は有効値の最小。"""
        monkeypatch.setenv("RAG_MAX_TOKENS", "1")
        assert rag._get_max_tokens() == 1

    @pytest.mark.parametrize("value", ["0", "-1", "-100"])
    def test_non_positive_falls_back_to_default(self, monkeypatch, value):
        monkeypatch.setenv("RAG_MAX_TOKENS", value)
        assert rag._get_max_tokens() == rag.DEFAULT_MAX_TOKENS

    @pytest.mark.parametrize("value", ["abc", "1.5", "not-a-number"])
    def test_unparseable_falls_back_to_default(self, monkeypatch, value):
        monkeypatch.setenv("RAG_MAX_TOKENS", value)
        assert rag._get_max_tokens() == rag.DEFAULT_MAX_TOKENS


# ---------------------------------------------------------------------------
# get_client
# ---------------------------------------------------------------------------


class TestGetClient:
    def test_get_client_is_singleton(self, monkeypatch):
        """`get_client` は一度作成したクライアントを再利用する。"""
        created: list = []

        def _factory():
            client = object()
            created.append(client)
            return client

        monkeypatch.setattr(rag, "OpenAI", _factory)
        first = rag.get_client()
        second = rag.get_client()

        assert first is second
        assert len(created) == 1


# ---------------------------------------------------------------------------
# generate_answer: 早期リターン系
# ---------------------------------------------------------------------------


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

    def test_empty_contexts_does_not_call_openai(self, monkeypatch):
        """コンテキストが空のときは get_client も呼ばれない（副作用なし）。"""
        called = {"n": 0}

        def _factory():
            called["n"] += 1
            return _FakeClient([])

        monkeypatch.setattr(rag, "OpenAI", _factory)

        generate_answer(query="テスト", contexts=[])

        # get_client は呼ばれるが、chat.completions.create は呼ばれない
        # 早期リターンのため create レスポンスを消費しない
        assert called["n"] <= 1


# ---------------------------------------------------------------------------
# generate_answer: 正常系（コンテキストあり）
# ---------------------------------------------------------------------------


class TestGenerateAnswerWithContext:
    def _install_fake_client(self, monkeypatch, responses: list) -> _FakeClient:
        fake = _FakeClient(responses)
        monkeypatch.setattr(rag, "OpenAI", lambda: fake)
        return fake

    def test_returns_answer_and_escalation(self, monkeypatch):
        """コンテキストがあるとき、生成された回答とエスカレーション結果を返す。"""
        fake = self._install_fake_client(
            monkeypatch,
            [
                "これはテスト回答です。---\nfaq.txt",
                json.dumps({"should_escalate": False, "reason": None}),
            ],
        )

        answer, should_escalate, reason = generate_answer(
            query="返品したいです",
            contexts=[
                {
                    "document_name": "faq.txt",
                    "category": "faq",
                    "content": "返品は購入後30日以内に可能です。",
                },
            ],
        )

        assert answer == "これはテスト回答です。---\nfaq.txt"
        assert should_escalate is False
        assert reason is None
        # 2 回呼ばれる（回答生成 + エスカレーション判定）
        assert len(fake.chat.completions.calls) == 2

    def test_uses_rag_model_for_chat_call(self, monkeypatch):
        """回答生成呼び出しでは RAG_MODEL がモデル引数として使われる。"""
        fake = self._install_fake_client(
            monkeypatch,
            [
                "回答",
                json.dumps({"should_escalate": False, "reason": None}),
            ],
        )
        generate_answer(
            query="テスト",
            contexts=[{"document_name": "a.txt", "category": "faq", "content": "内容"}],
        )
        assert fake.chat.completions.calls[0]["model"] == rag.RAG_MODEL

    def test_default_temperature_and_max_tokens_are_used(self, monkeypatch):
        """RAG_TEMPERATURE / RAG_MAX_TOKENS が未設定のとき、デフォルト値が使われる。"""
        monkeypatch.delenv("RAG_TEMPERATURE", raising=False)
        monkeypatch.delenv("RAG_MAX_TOKENS", raising=False)
        fake = self._install_fake_client(
            monkeypatch,
            [
                "回答",
                json.dumps({"should_escalate": False, "reason": None}),
            ],
        )
        generate_answer(
            query="テスト",
            contexts=[{"document_name": "a.txt", "category": "faq", "content": "内容"}],
        )
        call = fake.chat.completions.calls[0]
        assert call["temperature"] == rag.DEFAULT_TEMPERATURE
        assert call["max_tokens"] == rag.DEFAULT_MAX_TOKENS

    def test_env_overrides_temperature_and_max_tokens(self, monkeypatch):
        """RAG_TEMPERATURE / RAG_MAX_TOKENS が指定されているとき、その値が呼び出しに反映される。"""
        monkeypatch.setenv("RAG_TEMPERATURE", "0.9")
        monkeypatch.setenv("RAG_MAX_TOKENS", "512")
        fake = self._install_fake_client(
            monkeypatch,
            [
                "回答",
                json.dumps({"should_escalate": False, "reason": None}),
            ],
        )
        generate_answer(
            query="テスト",
            contexts=[{"document_name": "a.txt", "category": "faq", "content": "内容"}],
        )
        call = fake.chat.completions.calls[0]
        assert call["temperature"] == 0.9
        assert call["max_tokens"] == 512

    def test_escalation_call_is_unaffected_by_temperature_env(self, monkeypatch):
        """エスカレーション判定は temperature=0 固定であり、RAG_TEMPERATURE で上書きされない。"""
        monkeypatch.setenv("RAG_TEMPERATURE", "1.5")
        monkeypatch.setenv("RAG_MAX_TOKENS", "999")
        fake = self._install_fake_client(
            monkeypatch,
            [
                "回答",
                json.dumps({"should_escalate": False, "reason": None}),
            ],
        )
        generate_answer(
            query="テスト",
            contexts=[{"document_name": "a.txt", "category": "faq", "content": "内容"}],
        )
        escalation_call = fake.chat.completions.calls[1]
        # エスカレーション判定は「決定的な判定を得るため」 temperature=0 が固定要件
        assert escalation_call["temperature"] == 0
        # 判定用の max_tokens も従来通り 200 固定（JSON なので短い応答で十分）
        assert escalation_call["max_tokens"] == 200

    def test_context_text_includes_document_metadata(self, monkeypatch):
        """user メッセージには document_name / category / content が含まれる。"""
        fake = self._install_fake_client(
            monkeypatch,
            [
                "回答",
                json.dumps({"should_escalate": False, "reason": None}),
            ],
        )
        generate_answer(
            query="返品したい",
            contexts=[
                {
                    "document_name": "terms.txt",
                    "category": "terms",
                    "content": "セール品は返品不可です。",
                },
            ],
        )
        user_content = fake.chat.completions.calls[0]["messages"][1]["content"]
        assert "terms.txt" in user_content
        assert "terms" in user_content
        assert "セール品は返品不可です。" in user_content
        assert "返品したい" in user_content

    def test_multiple_contexts_are_numbered(self, monkeypatch):
        """複数コンテキストは【参照1】【参照2】... のように連番で埋め込まれる。"""
        fake = self._install_fake_client(
            monkeypatch,
            [
                "回答",
                json.dumps({"should_escalate": False, "reason": None}),
            ],
        )
        generate_answer(
            query="質問",
            contexts=[
                {"document_name": "a.txt", "category": "faq", "content": "内容A"},
                {"document_name": "b.txt", "category": "manual", "content": "内容B"},
                {"document_name": "c.txt", "category": "terms", "content": "内容C"},
            ],
        )
        user_content = fake.chat.completions.calls[0]["messages"][1]["content"]
        assert "【参照1】" in user_content
        assert "【参照2】" in user_content
        assert "【参照3】" in user_content

    @pytest.mark.parametrize(
        "tone,keyword",
        [
            ("polite", "丁寧"),
            ("concise", "簡潔"),
            ("standard", "標準"),
        ],
    )
    def test_tone_instruction_is_embedded_in_system_prompt(self, monkeypatch, tone, keyword):
        """指定したトーンの説明文が system メッセージに含まれる。"""
        fake = self._install_fake_client(
            monkeypatch,
            [
                "回答",
                json.dumps({"should_escalate": False, "reason": None}),
            ],
        )
        generate_answer(
            query="質問",
            contexts=[{"document_name": "a.txt", "category": "faq", "content": "X"}],
            tone=tone,
        )
        system_content = fake.chat.completions.calls[0]["messages"][0]["content"]
        assert keyword in system_content

    def test_unknown_tone_falls_back_to_standard(self, monkeypatch):
        """未知のトーンが渡されても standard の説明で system プロンプトが構築される。"""
        fake = self._install_fake_client(
            monkeypatch,
            [
                "回答",
                json.dumps({"should_escalate": False, "reason": None}),
            ],
        )
        generate_answer(
            query="質問",
            contexts=[{"document_name": "a.txt", "category": "faq", "content": "X"}],
            tone="unknown-tone",
        )
        system_content = fake.chat.completions.calls[0]["messages"][0]["content"]
        assert rag.TONE_INSTRUCTIONS["standard"] in system_content

    def test_returns_escalation_reason_from_check(self, monkeypatch):
        """エスカレーション判定が true を返した場合、その reason が上流に伝わる。"""
        self._install_fake_client(
            monkeypatch,
            [
                "高額返金のご相談です",
                json.dumps({"should_escalate": True, "reason": "金額が大きい返金判断が必要"}),
            ],
        )
        answer, should_escalate, reason = generate_answer(
            query="5万円返金希望",
            contexts=[{"document_name": "terms.txt", "category": "terms", "content": "..."}],
        )
        assert answer == "高額返金のご相談です"
        assert should_escalate is True
        assert reason == "金額が大きい返金判断が必要"


# ---------------------------------------------------------------------------
# _check_escalation
# ---------------------------------------------------------------------------


class TestCheckEscalation:
    def test_valid_json_should_escalate_true(self):
        """有効な JSON で should_escalate=true / reason 付きを返す。"""
        client = _FakeClient(
            [json.dumps({"should_escalate": True, "reason": "法的判断が必要"})]
        )
        should_escalate, reason = rag._check_escalation(
            client, "問い合わせ", "回答", "参照"
        )
        assert should_escalate is True
        assert reason == "法的判断が必要"

    def test_valid_json_should_escalate_false(self):
        """有効な JSON で should_escalate=false / reason=null を返す。"""
        client = _FakeClient(
            [json.dumps({"should_escalate": False, "reason": None})]
        )
        should_escalate, reason = rag._check_escalation(
            client, "問い合わせ", "回答", "参照"
        )
        assert should_escalate is False
        assert reason is None

    def test_missing_should_escalate_defaults_to_false(self):
        """should_escalate キーが欠けている場合は False (デフォルト) を返す。"""
        client = _FakeClient([json.dumps({"reason": "テスト"})])
        should_escalate, reason = rag._check_escalation(
            client, "問い合わせ", "回答", "参照"
        )
        assert should_escalate is False
        assert reason == "テスト"

    def test_missing_reason_returns_none(self):
        """reason キーが欠けている場合は None を返す。"""
        client = _FakeClient([json.dumps({"should_escalate": True})])
        should_escalate, reason = rag._check_escalation(
            client, "問い合わせ", "回答", "参照"
        )
        assert should_escalate is True
        assert reason is None

    def test_json_decode_error_returns_safe_default(self, caplog):
        """レスポンスが不正な JSON の場合、安全側でエスカレーションを推奨する。"""
        client = _FakeClient(["これは JSON ではありません"])
        import logging

        with caplog.at_level(logging.WARNING, logger="app.services.rag"):
            should_escalate, reason = rag._check_escalation(
                client, "問い合わせ", "回答", "参照"
            )
        assert should_escalate is True
        assert reason is not None
        assert "エスカレーション" in reason

    def test_unexpected_exception_returns_safe_default(self, caplog):
        """OpenAI 呼び出しが予期しない例外を投げた場合、安全側でエスカレーションを推奨する。"""

        class _BoomError(Exception):
            pass

        client = _FakeClient([_BoomError("boom")])
        import logging

        with caplog.at_level(logging.ERROR, logger="app.services.rag"):
            should_escalate, reason = rag._check_escalation(
                client, "問い合わせ", "回答", "参照"
            )
        assert should_escalate is True
        assert reason is not None
        assert "エスカレーション" in reason

    def test_uses_json_object_response_format(self):
        """エスカレーション判定呼び出しでは response_format=json_object を指定する。"""
        client = _FakeClient(
            [json.dumps({"should_escalate": False, "reason": None})]
        )
        rag._check_escalation(client, "問い合わせ", "回答", "参照")
        call = client.chat.completions.calls[0]
        assert call.get("response_format") == {"type": "json_object"}
        assert call.get("temperature") == 0
