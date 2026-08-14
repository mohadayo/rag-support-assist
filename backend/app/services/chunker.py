"""テキストのチャンク化処理"""

import os
import re

# 文の区切り文字（日本語の `。！？`、英語の `.!?`、改行）。区切り文字は保持する。
# module ロード時に一度だけコンパイルし、`_split_sentences` の呼び出しごとの
# 再コンパイルを避ける。
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。.！？!?\n])")


def _get_chunk_size() -> int:
    """環境変数 CHUNK_SIZE からチャンクサイズを取得する（デフォルト: 500）"""
    try:
        value = int(os.getenv("CHUNK_SIZE", "500"))
        if value < 50:
            return 50
        return value
    except (ValueError, TypeError):
        return 500


def _get_chunk_overlap() -> int:
    """環境変数 CHUNK_OVERLAP からオーバーラップサイズを取得する（デフォルト: 100）"""
    try:
        value = int(os.getenv("CHUNK_OVERLAP", "100"))
        if value < 0:
            return 0
        return value
    except (ValueError, TypeError):
        return 100


def _hard_split(text: str, chunk_size: int) -> list[str]:
    """デリミタが無いテキストを固定長で強制分割する。

    `_split_sentences` が「区切り文字が無い」と判定した長い連続文字列
    （例: 大量の連続する非区切り文字、URL、Base64 文字列など）は、
    そのままだと `chunk_text` 側で 1 チャンクにまとめられ、`chunk_size`
    上限を超過してしまう。埋め込みモデルのトークン上限や下流のプロンプト
    サイズを守るため、最終手段として文字単位で固定長分割する。
    """
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """テキストを指定サイズのチャンクに分割する。

    Args:
        text: 分割対象のテキスト
        chunk_size: チャンクの最大文字数。省略時は環境変数 CHUNK_SIZE を使用（デフォルト: 500）
        overlap: チャンク間のオーバーラップ文字数。省略時は環境変数 CHUNK_OVERLAP を使用（デフォルト: 100）

    Returns:
        チャンクのリスト
    """
    if chunk_size is None:
        chunk_size = _get_chunk_size()
    if overlap is None:
        overlap = _get_chunk_overlap()

    if not text.strip():
        return []

    # 段落単位で分割を試みる
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks: list[str] = []
    current_chunk = ""

    for para in paragraphs:
        # 段落自体がchunk_sizeを超える場合は文単位で分割
        if len(para) > chunk_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            sentences = _split_sentences(para)
            temp = ""
            for sentence in sentences:
                # 単一文が chunk_size を超える場合は固定長で強制分割する。
                # 区切り文字を持たない連続文字列（例: URL、長い識別子、Base64）が
                # そのまま 1 チャンクにまとめられて `chunk_size` 上限を突破する
                # 回帰を防ぐための保険。
                if len(sentence) > chunk_size:
                    if temp.strip():
                        chunks.append(temp.strip())
                        temp = ""
                    for piece in _hard_split(sentence, chunk_size):
                        if piece.strip():
                            chunks.append(piece.strip())
                    continue
                if len(temp) + len(sentence) > chunk_size and temp:
                    chunks.append(temp.strip())
                    # オーバーラップ: 末尾部分を保持
                    temp = temp[-overlap:] + sentence if overlap > 0 else sentence
                else:
                    temp += sentence
            if temp.strip():
                chunks.append(temp.strip())
        elif len(current_chunk) + len(para) + 1 > chunk_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
            # オーバーラップ
            current_chunk = current_chunk[-overlap:] + "\n" + para if overlap > 0 and current_chunk else para
        else:
            current_chunk = current_chunk + "\n" + para if current_chunk else para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def _split_sentences(text: str) -> list[str]:
    """日本語・英語の文を分割する"""
    parts = _SENTENCE_SPLIT_PATTERN.split(text)
    return [p for p in parts if p.strip()]
