"""文書管理API"""

import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from ..models import DocumentInfo, DocumentListResponse
from ..services.chunker import chunk_text
from ..services.vectorstore import add_documents, delete_document, get_document_stats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["documents"])


def _parse_max_upload_size_mb() -> int:
    raw = os.getenv("MAX_UPLOAD_SIZE_MB", "10")
    try:
        value = int(raw)
    except (ValueError, TypeError):
        logger.warning("Invalid MAX_UPLOAD_SIZE_MB=%r, falling back to 10", raw)
        return 10
    if value <= 0:
        logger.warning("MAX_UPLOAD_SIZE_MB=%r must be positive, falling back to 10", raw)
        return 10
    return value


# ファイルサイズ上限（環境変数 MAX_UPLOAD_SIZE_MB で設定可能、デフォルト10MB）
_MAX_UPLOAD_SIZE_MB = _parse_max_upload_size_mb()
_MAX_UPLOAD_SIZE_BYTES = _MAX_UPLOAD_SIZE_MB * 1024 * 1024

# ストリーミング読み込みの 1 回あたりバッファサイズ（1MB）。
# 上限を超えた瞬間に検出できる粒度を保ちつつ、per-chunk のオーバーヘッドを抑える。
_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024

# アップロードされるファイル名の最大長。DB `documents.name` 列は TEXT で
# 上限が無いため、ここで防御的に長さを制限する。POSIX のファイル名長 (NAME_MAX)
# の慣例値である 255 を採用。
_MAX_FILENAME_LENGTH = 255


def _validate_filename(filename: str) -> None:
    """アップロードファイル名を検証し、危険な値を弾く。

    以下のケースを 400 で拒否する:

    - 空文字・空白のみ (前段で `if not file.filename` を通っても、` ` 一文字などは
      通過してしまうため basename 化後にもう一度チェック)
    - パス区切り文字 (`/`, `\\`) を含む → パストラバーサル対策。現時点では
      filename をファイルシステムパスとして直接使用していないが、DB の
      `documents.name` 列やレスポンス、ログ、将来的なダウンロード API 等で
      再利用されうるため、入り口で拒否しておく（多層防御）。
    - NUL バイト・制御文字を含む → ログ改ざん / ヘッダー分割 / パス処理での
      truncation 攻撃対策。
    - `.` / `..` のみ → 相対パス扱いされうる特殊値。
    - 255 文字を超える → DB 肥大化・ログ肥大化・攻撃者による資源消費対策。
    """
    if not filename or not filename.strip():
        raise HTTPException(status_code=400, detail="ファイル名が必要です")

    if len(filename) > _MAX_FILENAME_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"ファイル名は{_MAX_FILENAME_LENGTH}文字以内で指定してください",
        )

    if "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=400,
            detail="ファイル名にパス区切り文字は使用できません",
        )

    # NUL バイトおよび C0 制御文字 (0x00-0x1F) と DEL (0x7F)。
    # タブ・改行等を含めて全て禁止 — ファイル名として意味を持たず、
    # ログ/レスポンスに混入すると副作用が大きい。
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in filename):
        raise HTTPException(
            status_code=400,
            detail="ファイル名に制御文字は使用できません",
        )

    if filename in (".", ".."):
        raise HTTPException(
            status_code=400,
            detail="ファイル名として '.' や '..' は使用できません",
        )


async def _read_upload_with_size_limit(file: UploadFile, max_bytes: int) -> bytes:
    """UploadFile をチャンク単位でストリーミング読み込みし、上限超過時に即座に打ち切る。

    従来の `await file.read()` は引数なしでファイル全体を一度に読み込むため、
    上限チェックが実行される時点で既に全体がメモリ（またはスプールファイル読出し）
    に載っており、`MAX_UPLOAD_SIZE_MB` の意図に反して DoS ベクタとして機能して
    しまう。本ヘルパーは累計サイズが上限を超えた瞬間に残りを読まずに例外を
    送出することで、`MAX_UPLOAD_SIZE_MB` の意図通りに読み込み量そのものを
    制限する。
    """
    buffer = bytearray()
    while True:
        chunk = await file.read(_UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"ファイルサイズが上限({_MAX_UPLOAD_SIZE_MB}MB)を超えています",
            )
    return bytes(buffer)


@router.post("/documents/upload", response_model=DocumentInfo)
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form("faq"),
):
    """文書ファイルをアップロードしてベクトルDBに登録する

    対応形式: .txt, .md, .csv
    カテゴリ: faq, terms, manual, history
    """
    # ファイル名の入り口バリデーション。以降のログ出力・DB 登録より前に実行することで、
    # 制御文字を含むファイル名でログ改ざんを試みる攻撃を早期に遮断する。
    _validate_filename(file.filename or "")

    allowed_extensions = {".txt", ".md", ".csv"}
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"対応形式: {', '.join(allowed_extensions)}",
        )

    allowed_categories = {"faq", "terms", "manual", "history"}
    if category not in allowed_categories:
        raise HTTPException(
            status_code=400,
            detail=f"カテゴリは次のいずれか: {', '.join(allowed_categories)}",
        )

    logger.info("ドキュメントアップロード開始: filename=%s, category=%s", file.filename, category)

    # ストリーミング読み込み。上限を超えた瞬間に 413 を送出し、残りを読まないため
    # `MAX_UPLOAD_SIZE_MB` を超える巨大ファイルが送られてきてもメモリ使用量を制限できる。
    content = await _read_upload_with_size_limit(file, _MAX_UPLOAD_SIZE_BYTES)

    text = content.decode("utf-8", errors="ignore")

    if not text.strip():
        raise HTTPException(status_code=400, detail="ファイルが空です")

    # チャンク化
    chunks = chunk_text(text)

    # ベクトルDBに登録
    doc_id = str(uuid.uuid4())
    chunk_count = add_documents(
        doc_id=doc_id,
        chunks=chunks,
        document_name=file.filename,
        category=category,
    )

    uploaded_at = datetime.now(timezone.utc).isoformat()

    logger.info(
        "ドキュメントアップロード完了: doc_id=%s, filename=%s, chunks=%d",
        doc_id, file.filename, chunk_count,
    )
    return DocumentInfo(
        id=doc_id,
        name=file.filename,
        category=category,
        chunk_count=chunk_count,
        uploaded_at=uploaded_at,
    )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents():
    """登録済み文書の一覧を返す"""
    logger.info("ドキュメント一覧取得")
    stats = get_document_stats()
    documents = [
        DocumentInfo(
            id=s["id"],
            name=s["name"],
            category=s["category"],
            chunk_count=s["chunk_count"],
            uploaded_at=s.get("uploaded_at", ""),
        )
        for s in stats
    ]
    return DocumentListResponse(documents=documents, total=len(documents))


@router.delete("/documents/{doc_id}")
async def remove_document(doc_id: str):
    """文書を削除する"""
    logger.info("ドキュメント削除リクエスト: doc_id=%s", doc_id)
    deleted = delete_document(doc_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="ドキュメントが見つかりません")
    return {"deleted_chunks": deleted, "document_id": doc_id}
