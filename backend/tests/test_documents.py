"""documents.py の _parse_max_upload_size_mb / _read_file_with_limit のユニットテスト"""

import asyncio
import logging
import sys
from unittest.mock import MagicMock

# psycopg2 / openai を事前にモックして import エラーを防ぐ
sys.modules.setdefault("psycopg2", MagicMock())
_openai_mock = MagicMock()
sys.modules.setdefault("openai", _openai_mock)
_openai_mock.OpenAI = MagicMock

import pytest
from fastapi import HTTPException

from app.routers.documents import _parse_max_upload_size_mb, _read_file_with_limit  # noqa: E402


class TestParseMaxUploadSizeMb:
    def test_default_is_10(self, monkeypatch):
        monkeypatch.delenv("MAX_UPLOAD_SIZE_MB", raising=False)
        assert _parse_max_upload_size_mb() == 10

    def test_valid_integer(self, monkeypatch):
        monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "5")
        assert _parse_max_upload_size_mb() == 5

    def test_large_value(self, monkeypatch):
        monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "100")
        assert _parse_max_upload_size_mb() == 100

    def test_invalid_string_falls_back_to_default(self, monkeypatch, caplog):
        monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "abc")
        with caplog.at_level(logging.WARNING, logger="app.routers.documents"):
            result = _parse_max_upload_size_mb()
        assert result == 10
        assert any("abc" in r.message for r in caplog.records)

    def test_zero_falls_back_to_default(self, monkeypatch, caplog):
        monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "0")
        with caplog.at_level(logging.WARNING, logger="app.routers.documents"):
            result = _parse_max_upload_size_mb()
        assert result == 10

    def test_negative_falls_back_to_default(self, monkeypatch, caplog):
        monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "-1")
        with caplog.at_level(logging.WARNING, logger="app.routers.documents"):
            result = _parse_max_upload_size_mb()
        assert result == 10

    def test_float_string_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "3.5")
        assert _parse_max_upload_size_mb() == 10


class _FakeStreamingFile:
    """UploadFile の read(size) だけを模した疑似ファイル。

    size を指定しない呼び出し（全体読み込み）を行った場合はテスト側で
    検知できるよう例外を送出する。
    """

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0
        self.read_calls: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            raise AssertionError(
                "read() はサイズ指定なしで呼び出されてはならない（ストリーミング読み込みが壊れている）"
            )
        self.read_calls.append(size)
        chunk = self._data[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk


class TestReadFileWithLimit:
    def test_上限以内のファイルは全体を読み込める(self):
        data = b"hello world"
        fake = _FakeStreamingFile(data)
        result = asyncio.run(_read_file_with_limit(fake, max_bytes=1024, max_mb=1))
        assert result == data

    def test_上限超過時にHTTPExceptionを送出する(self):
        # 上限1MBに対し5MB分のデータを用意する
        data = b"a" * (5 * 1024 * 1024)
        fake = _FakeStreamingFile(data)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(_read_file_with_limit(fake, max_bytes=1 * 1024 * 1024, max_mb=1))
        assert exc_info.value.status_code == 413
        assert "1MB" in exc_info.value.detail

    def test_上限超過時は全データを読み切る前に中断する(self):
        """ストリーミング読み込みにより、上限超過が判明した時点で
        残りのデータを読み込まずに中断できることを確認する
        （= 巨大ファイルでもメモリを使い切らないことの検証）。
        """
        chunk_size = 1024 * 1024  # documents._READ_CHUNK_SIZE と同じ値
        data = b"a" * (10 * chunk_size)  # 10MB
        fake = _FakeStreamingFile(data)
        with pytest.raises(HTTPException):
            asyncio.run(_read_file_with_limit(fake, max_bytes=1 * chunk_size, max_mb=1))
        # 上限(1チャンク分)を超えた2チャンク目で中断するため、
        # 全体(10チャンク)を読み切ってはいないはず
        assert len(fake.read_calls) < 10

    def test_ちょうど上限のファイルは成功する(self):
        data = b"b" * (2 * 1024 * 1024)
        fake = _FakeStreamingFile(data)
        result = asyncio.run(_read_file_with_limit(fake, max_bytes=2 * 1024 * 1024, max_mb=2))
        assert result == data

    def test_空ファイルは空バイト列を返す(self):
        fake = _FakeStreamingFile(b"")
        result = asyncio.run(_read_file_with_limit(fake, max_bytes=1024, max_mb=1))
        assert result == b""
