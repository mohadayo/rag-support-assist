"""テキストのチャンク化処理"""

import os


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

    # `overlap` は chunk 境界の末尾を次 chunk の冒頭に持ち込む長さ。
    # `overlap >= chunk_size` を許すと `temp[-overlap:]` / `current_chunk[-overlap:]`
    # がバッファ全体を返し、「flush して新しい chunk を開始する」経路が事実上 no-op
    # になる。結果として個々の chunk が chunk_size を無制限に超過し、下流の
    # Embedding API のトークン上限超過や検索精度低下を招く。ここで安全側に
    # クランプすることで overlap の意図（境界コンテキスト保持）を残しつつ、
    # 各 chunk のサイズ上限を守る。
    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 2)

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
    import re
    # 。.！？!? や改行で分割（区切り文字は保持）
    parts = re.split(r'(?<=[。.！？!?\n])', text)
    return [p for p in parts if p.strip()]
