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

# ストリーミング読み込み時の1回あたりの読み込みサイズ（1MB）
_READ_CHUNK_SIZE = 1024 * 1024


async def _read_file_with_limit(file: UploadFile, max_bytes: int, max_mb: int) -> bytes:
    """アップロードファイルをチャンク単位で読み込み、上限超過時に早期中断する。

    `await file.read()` で一度に全体を読み込んでからサイズを検査すると、
    上限チェックは読み込みが完了した後にしか機能しない。そのため、
    MAX_UPLOAD_SIZE_MB による上限設定があっても、悪意あるクライアントが
    巨大なファイル（数GB等）を送信した場合にサーバー側のメモリを
    圧迫してしまう（DoS の原因になりうる）。

    本関数は一定サイズ（`_READ_CHUNK_SIZE`）ずつ読み込み、累計サイズが
    上限を超えた時点で残りを読み切る前に即座に 413 を送出する。
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"ファイルサイズが上限({max_mb}MB)を超えています",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/documents/upload", response_model=DocumentInfo)
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form("faq"),
):
    """文書ファイルをアップロードしてベクトルDBに登録する

    対応形式: .txt, .md, .csv
    カテゴリ: faq, terms, manual, history
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="ファイル名が必要です")

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

    # ファイル読み込み（チャンク単位・上限超過時は即座に中断）
    content = await _read_file_with_limit(file, _MAX_UPLOAD_SIZE_BYTES, _MAX_UPLOAD_SIZE_MB)

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
