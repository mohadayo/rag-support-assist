"""vectorstore.py のユニットテスト"""
import sys
from unittest.mock import MagicMock, patch

# 外部依存を事前にモック化（他テストより先に実行される場合に備えて）
sys.modules.setdefault("psycopg2", MagicMock())
_openai_mod = MagicMock()
sys.modules.setdefault("openai", _openai_mod)
_openai_mod.OpenAI = MagicMock

import pytest  # noqa: E402

import app.services.vectorstore as vectorstore_module  # noqa: E402


def _make_mock_connection():
    """psycopg2.connect() の戻り値を模したモック接続/カーソルを生成する"""
    mock_cursor = MagicMock()
    mock_cursor_cm = MagicMock()
    mock_cursor_cm.__enter__.return_value = mock_cursor
    mock_cursor_cm.__exit__.return_value = False

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor_cm
    return mock_conn, mock_cursor


@pytest.fixture
def mock_db(monkeypatch):
    """DATABASE_URL と psycopg2.connect をモック化する"""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    mock_conn, mock_cursor = _make_mock_connection()
    with patch.object(
        vectorstore_module.psycopg2, "connect", return_value=mock_conn
    ) as mock_connect:
        yield mock_conn, mock_cursor, mock_connect


class TestGetDatabaseUrl:
    def test_raises_when_not_set(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(RuntimeError):
            vectorstore_module._get_database_url()

    def test_returns_value_when_set(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db")
        assert vectorstore_module._get_database_url() == "postgresql://u:p@host/db"


class TestAddDocuments:
    def test_empty_chunks_returns_zero_without_db_access(self, mock_db):
        """空チャンクリストの場合はDB接続もEmbedding生成も行わないこと"""
        _, _, mock_connect = mock_db
        result = vectorstore_module.add_documents(
            doc_id="doc-1", chunks=[], document_name="empty.txt", category="faq"
        )
        assert result == 0
        mock_connect.assert_not_called()

    def test_inserts_document_and_chunks(self, mock_db):
        """通常系: documents への1件とchunk件数分のINSERTが行われること"""
        _, mock_cursor, _ = mock_db
        with patch.object(
            vectorstore_module,
            "generate_embeddings",
            return_value=[[0.1] * 1536, [0.2] * 1536],
        ) as mock_gen:
            result = vectorstore_module.add_documents(
                doc_id="doc-1",
                chunks=["チャンク1", "チャンク2"],
                document_name="faq.txt",
                category="faq",
            )

        assert result == 2
        mock_gen.assert_called_once_with(["チャンク1", "チャンク2"])
        # documents テーブルへのINSERT 1回 + chunk INSERT 2回 = 計3回execute
        assert mock_cursor.execute.call_count == 3


class TestSearch:
    def test_returns_empty_result_when_no_chunks(self, mock_db):
        """チャンクが0件の場合はEmbedding生成せずに空結果を返すこと"""
        _, mock_cursor, _ = mock_db
        mock_cursor.fetchone.return_value = (0,)

        with patch.object(vectorstore_module, "generate_embedding") as mock_gen:
            result = vectorstore_module.search("テストクエリ")

        mock_gen.assert_not_called()
        assert result == {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    def test_returns_results_when_chunks_exist(self, mock_db):
        """通常系: ヒットした行がdocuments/metadatas/distancesに正しく整形されること"""
        _, mock_cursor, _ = mock_db
        mock_cursor.fetchone.return_value = (3,)
        mock_cursor.fetchall.return_value = [
            ("内容1", "faq.txt", "faq", 0.1),
            ("内容2", "manual.txt", "manual", 0.3),
        ]

        with patch.object(
            vectorstore_module, "generate_embedding", return_value=[0.1] * 1536
        ):
            result = vectorstore_module.search("返品について", n_results=5)

        assert result["documents"][0] == ["内容1", "内容2"]
        assert result["metadatas"][0][0] == {
            "document_name": "faq.txt",
            "category": "faq",
        }
        assert result["distances"][0] == [0.1, 0.3]


class TestDeleteDocument:
    def test_deletes_existing_document(self, mock_db):
        """該当チャンクがある場合はDELETEが実行され、削除件数が返ること"""
        _, mock_cursor, _ = mock_db
        mock_cursor.fetchone.return_value = (4,)

        result = vectorstore_module.delete_document("doc-1")

        assert result == 4
        delete_calls = [
            c for c in mock_cursor.execute.call_args_list if "DELETE" in c.args[0]
        ]
        assert len(delete_calls) == 1

    def test_returns_zero_when_document_not_found(self, mock_db):
        """該当チャンクがない場合はDELETEを実行せず0を返すこと"""
        _, mock_cursor, _ = mock_db
        mock_cursor.fetchone.return_value = (0,)

        result = vectorstore_module.delete_document("not-exist")

        assert result == 0
        delete_calls = [
            c for c in mock_cursor.execute.call_args_list if "DELETE" in c.args[0]
        ]
        assert len(delete_calls) == 0


class TestGetDocumentStats:
    def test_returns_empty_list(self, mock_db):
        _, mock_cursor, _ = mock_db
        mock_cursor.fetchall.return_value = []

        result = vectorstore_module.get_document_stats()

        assert result == []

    def test_formats_rows_into_dicts(self, mock_db):
        """uploaded_at が datetime の場合は isoformat() で文字列化されること"""
        _, mock_cursor, _ = mock_db
        fake_ts = MagicMock()
        fake_ts.isoformat.return_value = "2026-07-26T00:00:00+00:00"
        mock_cursor.fetchall.return_value = [
            ("id1", "a.txt", "faq", fake_ts, 3),
        ]

        result = vectorstore_module.get_document_stats()

        assert result == [
            {
                "id": "id1",
                "name": "a.txt",
                "category": "faq",
                "uploaded_at": "2026-07-26T00:00:00+00:00",
                "chunk_count": 3,
            }
        ]

    def test_uploaded_at_empty_string_when_none(self, mock_db):
        """uploaded_at が None の場合は空文字列になること"""
        _, mock_cursor, _ = mock_db
        mock_cursor.fetchall.return_value = [
            ("id1", "a.txt", "faq", None, 0),
        ]

        result = vectorstore_module.get_document_stats()

        assert result[0]["uploaded_at"] == ""


class TestGetChunkCount:
    def test_returns_count(self, mock_db):
        _, mock_cursor, _ = mock_db
        mock_cursor.fetchone.return_value = (7,)

        result = vectorstore_module.get_chunk_count()

        assert result == 7


class TestMigrate:
    def test_creates_extension_tables_and_index(self, mock_db):
        """pgvector拡張・2テーブル・1インデックスの計4回executeされること"""
        _, mock_cursor, _ = mock_db

        vectorstore_module.migrate()

        assert mock_cursor.execute.call_count == 4
