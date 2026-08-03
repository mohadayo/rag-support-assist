"""app.services.vectorstore のユニットテスト。

psycopg2 接続と OpenAI 呼び出しはすべて monkeypatch でスタブ化し、
実際のデータベースや外部 API に依存せずローカル実行のみで完結させる。
"""

import datetime as _dt

import pytest

from app.services import vectorstore


class _FakeCursor:
    """psycopg2 のカーソルを模したフェイク。

    `execute` の呼び出し履歴を `executed` に記録し、
    `fetchone` / `fetchall` の返り値は `fetchone_results` / `fetchall_result` から取り出す。
    """

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self.fetchone_results: list = []
        self.fetchall_result: list = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        if not self.fetchone_results:
            raise AssertionError("fetchone が想定外に呼ばれた")
        return self.fetchone_results.pop(0)

    def fetchall(self):
        return self.fetchall_result


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.commit_called = False
        self.rollback_called = False
        self.close_called = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commit_called = True

    def rollback(self):
        self.rollback_called = True

    def close(self):
        self.close_called = True


@pytest.fixture
def fake_conn(monkeypatch):
    """psycopg2.connect を差し替え、DATABASE_URL の要件も満たすフィクスチャ。"""
    monkeypatch.setenv("DATABASE_URL", "postgres://localhost/test")
    cursor = _FakeCursor()
    connection = _FakeConnection(cursor)
    monkeypatch.setattr(vectorstore.psycopg2, "connect", lambda url: connection)
    return connection, cursor


class TestGetDatabaseUrl:
    def test_returns_env_value(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://example/db")
        assert vectorstore._get_database_url() == "postgres://example/db"

    def test_raises_when_env_missing(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            vectorstore._get_database_url()


class TestGetConnection:
    def test_commits_and_closes_on_success(self, fake_conn):
        connection, _cursor = fake_conn
        with vectorstore._get_connection() as conn:
            assert conn is connection
        assert connection.commit_called is True
        assert connection.rollback_called is False
        assert connection.close_called is True

    def test_rolls_back_and_closes_on_exception(self, fake_conn):
        connection, _cursor = fake_conn
        with pytest.raises(RuntimeError, match="boom"):
            with vectorstore._get_connection():
                raise RuntimeError("boom")
        assert connection.commit_called is False
        assert connection.rollback_called is True
        assert connection.close_called is True


class TestMigrate:
    def test_executes_ddl_statements(self, fake_conn):
        _connection, cursor = fake_conn
        vectorstore.migrate()
        joined = " ".join(sql for sql, _ in cursor.executed)
        assert "CREATE EXTENSION IF NOT EXISTS vector" in joined
        assert "CREATE TABLE IF NOT EXISTS documents" in joined
        assert "CREATE TABLE IF NOT EXISTS document_chunks" in joined
        assert "CREATE INDEX IF NOT EXISTS idx_chunks_document_id" in joined


class TestAddDocuments:
    def test_returns_zero_for_empty_chunks(self, monkeypatch):
        # 空チャンクでは DB 接続も generate_embeddings も呼ばれない
        monkeypatch.setattr(
            vectorstore.psycopg2, "connect",
            lambda url: (_ for _ in ()).throw(AssertionError("connect が呼ばれた")),
        )
        monkeypatch.setattr(
            vectorstore, "generate_embeddings",
            lambda chunks: (_ for _ in ()).throw(AssertionError("generate_embeddings が呼ばれた")),
        )
        result = vectorstore.add_documents("doc1", [], "name", "cat")
        assert result == 0

    def test_inserts_document_and_chunks(self, fake_conn, monkeypatch):
        _connection, cursor = fake_conn
        embeds = [[0.1] * 3, [0.2] * 3]
        monkeypatch.setattr(vectorstore, "generate_embeddings", lambda chunks: embeds)

        result = vectorstore.add_documents(
            "doc1", ["hello", "world"], "Doc Name", "cat-a",
        )
        assert result == 2

        # documents への INSERT がまず1回
        assert cursor.executed[0][0].startswith("INSERT INTO documents")
        assert cursor.executed[0][1] == ("doc1", "Doc Name", "cat-a")

        # 続いて document_chunks への INSERT が chunks 数だけ
        chunk_inserts = [row for row in cursor.executed[1:]]
        assert len(chunk_inserts) == 2
        for i, (sql, params) in enumerate(chunk_inserts):
            assert "INSERT INTO document_chunks" in sql
            assert params[0] == f"doc1_chunk_{i}"
            assert params[1] == "doc1"
            assert params[2] == i
            assert params[3] == ["hello", "world"][i]
            assert params[4] == str(embeds[i])


class TestSearch:
    def test_returns_empty_when_table_empty(self, fake_conn):
        _connection, cursor = fake_conn
        cursor.fetchone_results = [(0,)]

        result = vectorstore.search("query", n_results=5)
        assert result == {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        # SELECT COUNT のみ実行され、類似検索クエリは走らない
        assert len(cursor.executed) == 1
        assert cursor.executed[0][0].startswith("SELECT COUNT(*) FROM document_chunks")

    def test_returns_matches(self, fake_conn, monkeypatch):
        _connection, cursor = fake_conn
        cursor.fetchone_results = [(3,)]
        cursor.fetchall_result = [
            ("chunk-1", "doc-a", "faq", 0.12),
            ("chunk-2", "doc-b", "manual", 0.34),
        ]
        monkeypatch.setattr(
            vectorstore, "generate_embedding", lambda q: [0.5, 0.6, 0.7],
        )

        result = vectorstore.search("question", n_results=2)

        assert result["documents"] == [["chunk-1", "chunk-2"]]
        assert result["metadatas"] == [[
            {"document_name": "doc-a", "category": "faq"},
            {"document_name": "doc-b", "category": "manual"},
        ]]
        assert result["distances"] == [[0.12, 0.34]]

        # 類似検索クエリの LIMIT には min(n_results, count) が渡る
        select_sql, select_params = cursor.executed[-1]
        assert "ORDER BY dc.embedding <=> %s::vector" in select_sql
        assert select_params[2] == 2

    def test_limit_clamped_to_count(self, fake_conn, monkeypatch):
        _connection, cursor = fake_conn
        cursor.fetchone_results = [(1,)]
        cursor.fetchall_result = [("only", "doc", "cat", 0.9)]
        monkeypatch.setattr(vectorstore, "generate_embedding", lambda q: [0.1])

        vectorstore.search("q", n_results=50)
        _, params = cursor.executed[-1]
        assert params[2] == 1


class TestDeleteDocument:
    def test_deletes_when_chunks_exist(self, fake_conn):
        _connection, cursor = fake_conn
        cursor.fetchone_results = [(4,)]

        result = vectorstore.delete_document("doc-x")
        assert result == 4
        # SELECT COUNT + DELETE の2回
        assert len(cursor.executed) == 2
        assert cursor.executed[1][0].startswith("DELETE FROM documents")
        assert cursor.executed[1][1] == ("doc-x",)

    def test_skips_delete_when_no_chunks(self, fake_conn):
        _connection, cursor = fake_conn
        cursor.fetchone_results = [(0,)]

        result = vectorstore.delete_document("doc-none")
        assert result == 0
        # SELECT COUNT のみで DELETE は発行されない
        assert len(cursor.executed) == 1


class TestGetDocumentStats:
    def test_returns_serialized_rows(self, fake_conn):
        _connection, cursor = fake_conn
        cursor.fetchall_result = [
            ("id-1", "docA", "faq", _dt.datetime(2026, 1, 2, 3, 4, 5), 10),
            ("id-2", "docB", "manual", None, 0),
        ]

        stats = vectorstore.get_document_stats()
        assert stats == [
            {
                "id": "id-1",
                "name": "docA",
                "category": "faq",
                "uploaded_at": "2026-01-02T03:04:05",
                "chunk_count": 10,
            },
            {
                "id": "id-2",
                "name": "docB",
                "category": "manual",
                "uploaded_at": "",
                "chunk_count": 0,
            },
        ]


class TestGetChunkCount:
    def test_returns_count(self, fake_conn):
        _connection, cursor = fake_conn
        cursor.fetchone_results = [(42,)]
        assert vectorstore.get_chunk_count() == 42
        assert cursor.executed[0][0].startswith("SELECT COUNT(*) FROM document_chunks")
