"""documents.py の _parse_max_upload_size_mb / _read_upload_with_size_limit のユニットテスト"""

import asyncio
import logging
import sys
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

# psycopg2 / openai を事前にモックして import エラーを防ぐ
sys.modules.setdefault("psycopg2", MagicMock())
_openai_mock = MagicMock()
sys.modules.setdefault("openai", _openai_mock)
_openai_mock.OpenAI = MagicMock

from app.routers.documents import (  # noqa: E402
    _parse_max_upload_size_mb,
    _read_upload_with_size_limit,
)


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


class _FakeUploadFile:
    """`UploadFile.read(size)` のみを模したストリーミング読み込み用のスタブ。

    実際の `UploadFile` は SpooledTemporaryFile ベースだが、テストでは
    `read(size)` の挙動と「呼び出しごとにどれだけ読んだか」だけ分かれば十分。
    """

    def __init__(self, payload: bytes):
        self._buf = payload
        self._pos = 0
        self.read_calls: list[int] = []
        self.total_bytes_read = 0

    async def read(self, size: int | None = None) -> bytes:
        self.read_calls.append(size if size is not None else -1)
        if size is None or size < 0:
            chunk = self._buf[self._pos:]
            self._pos = len(self._buf)
        else:
            end = min(self._pos + size, len(self._buf))
            chunk = self._buf[self._pos:end]
            self._pos = end
        self.total_bytes_read += len(chunk)
        return chunk


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestReadUploadWithSizeLimit:
    def test_上限以内_全体を読み切って返す(self):
        payload = b"hello world" * 10
        upload = _FakeUploadFile(payload)
        result = _run(_read_upload_with_size_limit(upload, max_bytes=1024))
        assert result == payload
        assert upload.total_bytes_read == len(payload)

    def test_空ファイル_空バイト列を返す(self):
        upload = _FakeUploadFile(b"")
        result = _run(_read_upload_with_size_limit(upload, max_bytes=1024))
        assert result == b""

    def test_チャンク単位で読み込む(self):
        payload = b"x" * (3 * 1024 * 1024 + 500)
        upload = _FakeUploadFile(payload)
        result = _run(_read_upload_with_size_limit(upload, max_bytes=10 * 1024 * 1024))
        assert result == payload
        assert all(size == 1024 * 1024 for size in upload.read_calls[:-1])

    def test_上限超過_413を送出(self):
        payload = b"y" * (1024 * 1024 + 1)
        upload = _FakeUploadFile(payload)
        with pytest.raises(HTTPException) as excinfo:
            _run(_read_upload_with_size_limit(upload, max_bytes=1024 * 1024))
        assert excinfo.value.status_code == 413
        assert "上限" in excinfo.value.detail

    def test_上限超過_残りを読まずに打ち切る(self):
        """DoS 対策の本命: 上限を超えた瞬間に、ファイル全体を読み切らないこと。"""
        payload = b"z" * (100 * 1024 * 1024)  # 100MB
        upload = _FakeUploadFile(payload)
        with pytest.raises(HTTPException):
            _run(_read_upload_with_size_limit(upload, max_bytes=1024 * 1024))
        # 実際に読み込んだ量が「上限 + 高々 1 チャンク」に収まっていること
        # （= ファイル全体 100MB を読み切っていない）
        assert upload.total_bytes_read <= (1024 * 1024) + (1024 * 1024)
        assert upload.total_bytes_read < len(payload)

    def test_境界値_ちょうど上限は許可(self):
        max_bytes = 1024 * 1024
        payload = b"a" * max_bytes
        upload = _FakeUploadFile(payload)
        result = _run(_read_upload_with_size_limit(upload, max_bytes=max_bytes))
        assert len(result) == max_bytes

    def test_境界値_上限プラス1バイトは拒否(self):
        max_bytes = 1024 * 1024
        payload = b"a" * (max_bytes + 1)
        upload = _FakeUploadFile(payload)
        with pytest.raises(HTTPException) as excinfo:
            _run(_read_upload_with_size_limit(upload, max_bytes=max_bytes))
        assert excinfo.value.status_code == 413
