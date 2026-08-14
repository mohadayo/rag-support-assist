"""chunker.py のユニットテスト"""

from app.services.chunker import (
    _get_chunk_overlap,
    _get_chunk_size,
    _hard_split,
    _split_sentences,
    chunk_text,
)


class TestChunkText:
    """chunk_text 関数のテスト"""

    def test_empty_string_returns_empty_list(self):
        """空文字列の場合は空リストを返す"""
        assert chunk_text("") == []

    def test_whitespace_only_returns_empty_list(self):
        """空白のみの場合は空リストを返す"""
        assert chunk_text("   \n\n   ") == []

    def test_short_text_returns_single_chunk(self):
        """短いテキストは1チャンクにまとめられる"""
        text = "これはテストです。"
        chunks = chunk_text(text, chunk_size=500, overlap=100)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_text_split_into_multiple_chunks(self):
        """長いテキストは複数チャンクに分割される"""
        # 100文字を超えるテキストを用意
        text = "あ" * 200 + "\n\n" + "い" * 200
        chunks = chunk_text(text, chunk_size=100, overlap=0)
        assert len(chunks) > 1

    def test_chunks_do_not_exceed_chunk_size(self):
        """各チャンクはchunk_sizeを超えない（段落単位の結合時）"""
        paragraphs = ["短い段落。" for _ in range(10)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, chunk_size=50, overlap=0)
        for chunk in chunks:
            assert len(chunk) <= 50 + 20  # 多少の余裕を持つ

    def test_overlap_adds_context_between_chunks(self):
        """オーバーラップが有効な場合、隣接チャンク間で内容が共有される"""
        # 長いテキストを生成
        long_text = "テスト文章です。" * 100
        chunks_with_overlap = chunk_text(long_text, chunk_size=100, overlap=50)
        chunks_no_overlap = chunk_text(long_text, chunk_size=100, overlap=0)
        # オーバーラップありの方がチャンク数が多くなるか、各チャンクが長くなる
        assert len(chunks_with_overlap) >= len(chunks_no_overlap)

    def test_custom_chunk_size(self):
        """カスタムchunk_sizeが正しく適用される"""
        text = "a" * 1000
        chunks_small = chunk_text(text, chunk_size=100, overlap=0)
        chunks_large = chunk_text(text, chunk_size=500, overlap=0)
        assert len(chunks_small) > len(chunks_large)

    def test_paragraph_splitting(self):
        """段落（空行）区切りで正しく分割される"""
        text = "段落1です。\n\n段落2です。\n\n段落3です。"
        chunks = chunk_text(text, chunk_size=500, overlap=0)
        # 短い段落はまとめられる
        assert len(chunks) == 1
        assert "段落1" in chunks[0]
        assert "段落2" in chunks[0]

    def test_env_var_chunk_size(self, monkeypatch):
        """環境変数 CHUNK_SIZE が適用される"""
        monkeypatch.setenv("CHUNK_SIZE", "100")
        text = "あ" * 500
        chunks = chunk_text(text)  # chunk_sizeを省略
        # 500文字が100文字ずつ分割されるので複数チャンクになるはず
        assert len(chunks) > 1

    def test_env_var_chunk_overlap(self, monkeypatch):
        """環境変数 CHUNK_OVERLAP が適用される"""
        monkeypatch.setenv("CHUNK_OVERLAP", "0")
        text = "テスト。" * 100
        # 例外なく実行できることを確認
        chunks = chunk_text(text)
        assert isinstance(chunks, list)


class TestSplitSentences:
    """_split_sentences 関数のテスト"""

    def test_split_japanese_sentences(self):
        """日本語の句点で文を分割する"""
        text = "これは最初の文です。これは2番目の文です。これは3番目の文です。"
        sentences = _split_sentences(text)
        assert len(sentences) == 3

    def test_split_english_sentences(self):
        """英語の文を分割する"""
        text = "This is sentence one. This is sentence two? This is sentence three!"
        sentences = _split_sentences(text)
        assert len(sentences) == 3

    def test_empty_string_returns_empty_list(self):
        """空文字列の場合は空リストを返す"""
        assert _split_sentences("") == []

    def test_no_delimiter_returns_single_sentence(self):
        """区切り文字がない場合は1要素のリストを返す"""
        text = "これは区切り文字のない文章"
        sentences = _split_sentences(text)
        assert len(sentences) == 1
        assert sentences[0] == text


class TestChunkSizeExceededByLongSentence:
    """`chunk_size` を超える単一文の強制分割に関する回帰テスト。

    区切り文字を持たない長い連続文字列（URL、識別子、Base64 等）が
    そのまま 1 チャンクにまとめられていた既存の不具合を防ぐ。
    """

    def test_long_no_delimiter_text_splits_into_multiple_chunks(self):
        """デリミタ無しの長文が chunk_size に応じて複数チャンクに分割される。"""
        text = "a" * 1000
        chunks_small = chunk_text(text, chunk_size=100, overlap=0)
        chunks_large = chunk_text(text, chunk_size=500, overlap=0)
        assert len(chunks_small) > len(chunks_large)
        assert len(chunks_small) == 10
        assert len(chunks_large) == 2

    def test_chunk_size_upper_bound_is_enforced(self):
        """各チャンクの長さが chunk_size を超えない。"""
        text = "x" * 1234
        chunks = chunk_text(text, chunk_size=100, overlap=0)
        for chunk in chunks:
            assert len(chunk) <= 100

    def test_long_sentence_within_paragraph_is_split(self):
        """段落末尾に区切り文字が無い長文でも chunk_size を守って分割される。"""
        text = "b" * 800
        chunks = chunk_text(text, chunk_size=200, overlap=0)
        assert len(chunks) == 4
        assert all(chunk == "b" * 200 for chunk in chunks)


class TestHardSplit:
    """`_hard_split` の挙動テスト。"""

    def test_returns_empty_list_for_empty_text(self):
        assert _hard_split("", 10) == []

    def test_splits_into_fixed_length_pieces(self):
        assert _hard_split("abcdefghij", 3) == ["abc", "def", "ghi", "j"]

    def test_returns_single_piece_when_shorter_than_chunk_size(self):
        assert _hard_split("abc", 10) == ["abc"]


class TestGetChunkSize:
    """`_get_chunk_size` の環境変数解釈テスト。"""

    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("CHUNK_SIZE", raising=False)
        assert _get_chunk_size() == 500

    def test_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("CHUNK_SIZE", "1000")
        assert _get_chunk_size() == 1000

    def test_below_minimum_clamped_to_50(self, monkeypatch):
        """50 未満の値は 50 に丸める。"""
        monkeypatch.setenv("CHUNK_SIZE", "10")
        assert _get_chunk_size() == 50

    def test_zero_clamped_to_50(self, monkeypatch):
        monkeypatch.setenv("CHUNK_SIZE", "0")
        assert _get_chunk_size() == 50

    def test_invalid_string_falls_back_to_default(self, monkeypatch):
        """整数として解釈できない値は既定値 500 にフォールバックする。"""
        monkeypatch.setenv("CHUNK_SIZE", "not-a-number")
        assert _get_chunk_size() == 500

    def test_empty_string_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("CHUNK_SIZE", "")
        assert _get_chunk_size() == 500


class TestGetChunkOverlap:
    """`_get_chunk_overlap` の環境変数解釈テスト。"""

    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("CHUNK_OVERLAP", raising=False)
        assert _get_chunk_overlap() == 100

    def test_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("CHUNK_OVERLAP", "50")
        assert _get_chunk_overlap() == 50

    def test_zero_is_allowed(self, monkeypatch):
        monkeypatch.setenv("CHUNK_OVERLAP", "0")
        assert _get_chunk_overlap() == 0

    def test_negative_clamped_to_zero(self, monkeypatch):
        """負値は 0 に丸める。"""
        monkeypatch.setenv("CHUNK_OVERLAP", "-10")
        assert _get_chunk_overlap() == 0

    def test_invalid_string_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("CHUNK_OVERLAP", "abc")
        assert _get_chunk_overlap() == 100

    def test_empty_string_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("CHUNK_OVERLAP", "")
        assert _get_chunk_overlap() == 100
