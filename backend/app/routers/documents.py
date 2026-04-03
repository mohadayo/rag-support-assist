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

MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", str(10 * 1024 * 1024)))  # デフォルト10MB

router = APIRouter(prefix="/api", tags=["documents"])

# アップロード日時を保持する簡易ストア（MVPではインメモリ）
_upload_times: dict[str, str] = {}


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

    # ファイル読み込み
    content = await file.read()

    # ファイルサイズ検証
    if len(content) > MAX_FILE_SIZE:
        logger.warning(
            "ファイルサイズ超過: filename=%s, size=%d bytes, max=%d bytes",
            file.filename, len(content), MAX_FILE_SIZE,
        )
        raise HTTPException(
            status_code=400,
            detail=f"ファイルサイズが上限({MAX_FILE_SIZE // (1024 * 1024)}MB)を超えています",
        )

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
    _upload_times[doc_id] = uploaded_at

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
            uploaded_at=_upload_times.get(s["id"], ""),
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
    _upload_times.pop(doc_id, None)
    return {"deleted_chunks": deleted, "document_id": doc_id}
