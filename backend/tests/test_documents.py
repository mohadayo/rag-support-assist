"""documents.py の _parse_max_upload_size_mb のユニットテスト"""

import logging
import sys
from unittest.mock import MagicMock

# psycopg2 / openai を事前にモックして import エラーを防ぐ
sys.modules.setdefault("psycopg2", MagicMock())
_openai_mock = MagicMock()
sys.modules.setdefault("openai", _openai_mock)
_openai_mock.OpenAI = MagicMock

from app.routers.documents import _parse_max_upload_size_mb  # noqa: E402


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
