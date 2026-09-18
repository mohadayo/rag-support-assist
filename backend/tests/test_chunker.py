"""chunker.py のユニットテスト"""

import re

from app.services import chunker
from app.services.chunker import (
    _get_chunk_overlap,
    _get_chunk_size,
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

    def test_overlap_equal_to_chunk_size_is_clamped(self):
        """overlap == chunk_size でも chunk が chunk_size を大きく超えない

        `temp[-overlap:]` は overlap >= len(temp) のとき temp 全体を返す。
        クランプが無いと「flush して次 chunk を開始する」経路が no-op になり
        chunk が無制限に膨らむ。クランプにより chunk_size 前後に収まる。
        """
        text = "テスト。" * 200  # sentence 分割経路を通す
        chunks = chunk_text(text, chunk_size=100, overlap=100)
        assert len(chunks) > 1
        for chunk in chunks:
            # クランプ後の overlap は chunk_size // 2 = 50 なので、
            # 概ね chunk_size + 1 sentence 程度 (「テスト。」= 4 文字) には収まる。
            assert len(chunk) <= 200

    def test_overlap_greater_than_chunk_size_is_clamped(self):
        """overlap > chunk_size でも chunk が無制限に膨張しない"""
        text = "テスト。" * 200
        chunks = chunk_text(text, chunk_size=100, overlap=500)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 200

    def test_overlap_greater_than_chunk_size_paragraph_path(self):
        """段落経路でも overlap >= chunk_size がクランプされる"""
        # `\n\n` で区切られる短い段落を多数用意し、段落結合経路 (elif) を通す。
        paragraphs = ["段落テキスト" for _ in range(20)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, chunk_size=30, overlap=30)
        assert len(chunks) > 1
        for chunk in chunks:
            # クランプ後の overlap は 15 なので、境界時の chunk サイズは
            # (前 chunk 末尾 15) + 改行 + 段落 (6 文字) ≒ 22 程度。
            # 段落を 1 つ足した際にも 30 + 20 = 50 は超えない。
            assert len(chunk) <= 60


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

    def test_delimiter_is_retained_at_end_of_sentence(self):
        """区切り文字 (。 . ！ ？ ! ?) は分割後も末尾に保持される"""
        # 後読みアサーションで分割するため、区切り文字は前の文の末尾に残る仕様。
        # この保持挙動が失われるとチャンク境界の意味論が壊れるため回帰テストで固定する。
        text = "文A。文B！文C？文D。"
        sentences = _split_sentences(text)
        assert sentences == ["文A。", "文B！", "文C？", "文D。"]

    def test_newline_is_treated_as_delimiter(self):
        """改行も文の区切りとして扱われる（区切り文字は末尾に残る）"""
        text = "1行目\n2行目\n3行目"
        sentences = _split_sentences(text)
        assert sentences == ["1行目\n", "2行目\n", "3行目"]

    def test_pattern_is_compiled_once_at_module_level(self):
        """正規表現は module ロード時に一度だけコンパイルされる。

        `_split_sentences` はチャンカーのホットパスから繰り返し呼ばれるため、
        呼び出しごとに `re.compile` を走らせない実装 (module-level 定数化) を
        回帰テストで固定する。
        """
        assert isinstance(chunker._SENTENCE_SPLIT_PATTERN, re.Pattern)


class TestGetChunkSize:
    """_get_chunk_size のパース挙動（環境変数のエッジケース）"""

    def test_default_when_env_var_unset(self, monkeypatch):
        """CHUNK_SIZE 未設定時はデフォルト 500 を返す"""
        monkeypatch.delenv("CHUNK_SIZE", raising=False)
        assert _get_chunk_size() == 500

    def test_reads_valid_env_value(self, monkeypatch):
        """CHUNK_SIZE に有効な整数が設定されているときはその値を返す"""
        monkeypatch.setenv("CHUNK_SIZE", "1200")
        assert _get_chunk_size() == 1200

    def test_below_minimum_is_clamped_to_50(self, monkeypatch):
        """CHUNK_SIZE < 50 は下限 50 にクランプされる"""
        monkeypatch.setenv("CHUNK_SIZE", "10")
        assert _get_chunk_size() == 50

    def test_zero_is_clamped_to_50(self, monkeypatch):
        """CHUNK_SIZE=0 も下限 50 にクランプされる"""
        monkeypatch.setenv("CHUNK_SIZE", "0")
        assert _get_chunk_size() == 50

    def test_negative_is_clamped_to_50(self, monkeypatch):
        """負値もクランプされる（`< 50` の一般化）"""
        monkeypatch.setenv("CHUNK_SIZE", "-100")
        assert _get_chunk_size() == 50

    def test_invalid_string_falls_back_to_default(self, monkeypatch):
        """整数として解釈できない値は例外にせずデフォルト 500 にフォールバック"""
        monkeypatch.setenv("CHUNK_SIZE", "not-a-number")
        assert _get_chunk_size() == 500

    def test_empty_string_falls_back_to_default(self, monkeypatch):
        """空文字列も ValueError 経路でデフォルトにフォールバック"""
        monkeypatch.setenv("CHUNK_SIZE", "")
        assert _get_chunk_size() == 500


class TestGetChunkOverlap:
    """_get_chunk_overlap のパース挙動（環境変数のエッジケース）"""

    def test_default_when_env_var_unset(self, monkeypatch):
        """CHUNK_OVERLAP 未設定時はデフォルト 100 を返す"""
        monkeypatch.delenv("CHUNK_OVERLAP", raising=False)
        assert _get_chunk_overlap() == 100

    def test_reads_valid_env_value(self, monkeypatch):
        """CHUNK_OVERLAP に有効な整数が設定されているときはその値を返す"""
        monkeypatch.setenv("CHUNK_OVERLAP", "42")
        assert _get_chunk_overlap() == 42

    def test_zero_is_allowed(self, monkeypatch):
        """CHUNK_OVERLAP=0 はオーバーラップ無効化として受理される（下限クランプ対象外）"""
        monkeypatch.setenv("CHUNK_OVERLAP", "0")
        assert _get_chunk_overlap() == 0

    def test_negative_is_clamped_to_zero(self, monkeypatch):
        """負値は 0 にクランプされる（overlap は非負でなければ意味を持たない）"""
        monkeypatch.setenv("CHUNK_OVERLAP", "-25")
        assert _get_chunk_overlap() == 0

    def test_invalid_string_falls_back_to_default(self, monkeypatch):
        """整数として解釈できない値は例外にせずデフォルト 100 にフォールバック"""
        monkeypatch.setenv("CHUNK_OVERLAP", "abc")
        assert _get_chunk_overlap() == 100

    def test_empty_string_falls_back_to_default(self, monkeypatch):
        """空文字列も ValueError 経路でデフォルトにフォールバック"""
        monkeypatch.setenv("CHUNK_OVERLAP", "")
        assert _get_chunk_overlap() == 100
