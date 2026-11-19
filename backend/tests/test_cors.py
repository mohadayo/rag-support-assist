"""`_parse_cors_origins` の回帰テスト。

`CORS_ORIGINS` 環境変数の解釈を固定する。空文字 / 空要素 / 前後空白 / 全要素空白
などの誤設定時に、空の origin が許可されないこと（デフォルトへフォールバック
されること）を保証する。
"""

import pytest

from app.main import DEFAULT_CORS_ORIGIN, _parse_cors_origins


def test_unset_falls_back_to_default(monkeypatch: pytest.MonkeyPatch):
    """`CORS_ORIGINS` 未設定時はデフォルト 1 件を返すこと。"""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert _parse_cors_origins() == [DEFAULT_CORS_ORIGIN]


def test_empty_string_falls_back_to_default(monkeypatch: pytest.MonkeyPatch):
    """`CORS_ORIGINS=""` のとき、空 origin を許可せずデフォルトへフォールバック。"""
    monkeypatch.setenv("CORS_ORIGINS", "")
    assert _parse_cors_origins() == [DEFAULT_CORS_ORIGIN]


def test_all_whitespace_falls_back_to_default(monkeypatch: pytest.MonkeyPatch):
    """空白・カンマのみで構成された値もデフォルトへフォールバックする。"""
    monkeypatch.setenv("CORS_ORIGINS", " , , ")
    assert _parse_cors_origins() == [DEFAULT_CORS_ORIGIN]


def test_single_origin(monkeypatch: pytest.MonkeyPatch):
    """単一オリジンはそのまま 1 要素のリストで返る。"""
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")
    assert _parse_cors_origins() == ["https://example.com"]


def test_multiple_origins(monkeypatch: pytest.MonkeyPatch):
    """カンマ区切りの複数オリジンが順序通りに返る。"""
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example,https://b.example")
    assert _parse_cors_origins() == ["https://a.example", "https://b.example"]


def test_empty_entries_are_dropped(monkeypatch: pytest.MonkeyPatch):
    """`a,,b` / `a,` のような空要素は除外される。空 origin がサイレントに
    許可されるリグレッションを防ぐ。"""
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example,,https://b.example,")
    assert _parse_cors_origins() == ["https://a.example", "https://b.example"]


def test_leading_and_trailing_whitespace_is_stripped(
    monkeypatch: pytest.MonkeyPatch,
):
    """各要素の前後空白が除去される。元から同等の挙動を保持することを固定。"""
    monkeypatch.setenv("CORS_ORIGINS", "  https://a.example , https://b.example  ")
    assert _parse_cors_origins() == ["https://a.example", "https://b.example"]
