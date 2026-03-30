"""テキストのチャンク化処理"""


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """テキストを指定サイズのチャンクに分割する。

    Args:
        text: 分割対象のテキスト
        chunk_size: チャンクの最大文字数
        overlap: チャンク間のオーバーラップ文字数

    Returns:
        チャンクのリスト
    """
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
    # 。！？!? や改行で分割（区切り文字は保持）
    parts = re.split(r'(?<=[。！？!?\n])', text)
    return [p for p in parts if p.strip()]
