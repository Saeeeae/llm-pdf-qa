import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db.models import Document, DocChunk
from app.db.postgres import get_session
from app.db.qdrant import QdrantManager
from app.pipeline.scanner import scan_files, scan_and_ingest
from app.pipeline.sync import run_sync
from app.tasks.ingest_tasks import ingest_file

logger = logging.getLogger(__name__)
router = APIRouter()


# === Response Models ===

class DocumentResponse(BaseModel):
    doc_id: int
    file_name: str
    path: str
    type: str
    hash: str
    size: Optional[int]
    status: str
    total_page_cnt: Optional[int]
    error_msg: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    total: int
    documents: list[DocumentResponse]


class ChunkResponse(BaseModel):
    chunk_id: int
    doc_id: int
    chunk_idx: int
    content: str
    token_cnt: int
    page_number: Optional[int]
    qdrant_id: Optional[str]

    class Config:
        from_attributes = True


class SyncResponse(BaseModel):
    new: int
    modified: int
    deleted: int
    unchanged: int
    errors: int


class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


# === Endpoints ===

@router.get("", response_model=DocumentListResponse)
def list_documents(
    status: Optional[str] = Query(None, description="Filter by status: pending, processing, indexed, failed"),
    type: Optional[str] = Query(None, description="Filter by file type: pdf, docx, xlsx, pptx, png, jpg"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """문서 목록 조회."""
    with get_session() as session:
        query = session.query(Document)
        if status:
            query = query.filter(Document.status == status)
        if type:
            query = query.filter(Document.type == type)

        total = query.count()
        docs = query.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()

        return DocumentListResponse(
            total=total,
            documents=[
                DocumentResponse(
                    doc_id=d.doc_id,
                    file_name=d.file_name,
                    path=d.path,
                    type=d.type,
                    hash=d.hash,
                    size=d.size,
                    status=d.status,
                    total_page_cnt=d.total_page_cnt,
                    error_msg=d.error_msg,
                    created_at=str(d.created_at),
                    updated_at=str(d.updated_at),
                )
                for d in docs
            ],
        )


@router.get("/{doc_id}")
def get_document(doc_id: int):
    """문서 상세 조회 (청크 포함)."""
    with get_session() as session:
        doc = session.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        chunks = (
            session.query(DocChunk)
            .filter(DocChunk.doc_id == doc_id)
            .order_by(DocChunk.chunk_idx)
            .all()
        )

        return {
            "document": DocumentResponse(
                doc_id=doc.doc_id,
                file_name=doc.file_name,
                path=doc.path,
                type=doc.type,
                hash=doc.hash,
                size=doc.size,
                status=doc.status,
                total_page_cnt=doc.total_page_cnt,
                error_msg=doc.error_msg,
                created_at=str(doc.created_at),
                updated_at=str(doc.updated_at),
            ),
            "chunks": [
                ChunkResponse(
                    chunk_id=c.chunk_id,
                    doc_id=c.doc_id,
                    chunk_idx=c.chunk_idx,
                    content=c.content,
                    token_cnt=c.token_cnt,
                    page_number=c.page_number,
                    qdrant_id=c.qdrant_id,
                )
                for c in chunks
            ],
            "chunk_count": len(chunks),
        }


@router.post("/ingest", response_model=TaskResponse)
def ingest_document_endpoint(file_path: str = Query(..., description="컨테이너 내 파일 경로")):
    """단일 파일 비동기 인제스트 (Celery task)."""
    task = ingest_file.delay(file_path)
    return TaskResponse(
        task_id=task.id,
        status="queued",
        message=f"Ingestion task queued for: {file_path}",
    )


@router.post("/sync", response_model=SyncResponse)
def sync_documents():
    """DOC_WATCH_DIR 기준 변경 감지 + 동기화 (동기 실행)."""
    stats = run_sync()
    if "error" in stats:
        raise HTTPException(status_code=500, detail=stats["error"])
    return SyncResponse(**stats)


@router.delete("/{doc_id}")
def delete_document(doc_id: int):
    """문서 및 관련 청크/벡터 삭제."""
    with get_session() as session:
        doc = session.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Qdrant에서 벡터 삭제
        try:
            qdrant = QdrantManager()
            qdrant.delete_by_doc_id(doc_id)
        except Exception as e:
            logger.warning("Failed to delete vectors from Qdrant: %s", e)

        # PostgreSQL에서 청크 + 문서 삭제
        session.query(DocChunk).filter(DocChunk.doc_id == doc_id).delete()
        session.delete(doc)

        return {"message": f"Document {doc_id} ({doc.file_name}) deleted"}


@router.get("/scan")
def scan_directory(
    directory: str = Query(None, description="스캔할 디렉토리 (기본: DOC_WATCH_DIR)"),
    pattern: str = Query(None, description="glob 패턴 (예: **/*.pdf, report_*.xlsx)"),
    extensions: str = Query(None, description="확장자 필터 (쉼표 구분: pdf,docx,xlsx)"),
    recursive: bool = Query(True, description="하위 디렉토리 포함"),
    compute_hash: bool = Query(False, description="SHA-256 해시 계산 (느릴 수 있음)"),
):
    """디렉토리 스캔 - 처리 가능한 파일 목록 조회.

    glob 패턴으로 특정 파일만 필터링 가능.
    """
    from app.config import settings

    scan_dir = directory or settings.doc_watch_dir

    ext_set = None
    if extensions:
        ext_set = {f".{e.strip().lstrip('.')}" for e in extensions.split(",")}

    result = scan_files(
        scan_dir,
        extensions=ext_set,
        pattern=pattern,
        recursive=recursive,
        compute_hash=compute_hash,
    )

    return {
        "directory": result.directory,
        "total_files": result.total_files,
        "by_type": result.by_type,
        "files": [
            {
                "path": f.path,
                "name": f.name,
                "extension": f.extension,
                "size": f.size,
                "hash": f.hash if f.hash else None,
            }
            for f in result.files
        ],
    }


@router.post("/scan/ingest")
def scan_and_ingest_endpoint(
    directory: str = Query(None, description="스캔할 디렉토리 (기본: DOC_WATCH_DIR)"),
    pattern: str = Query(None, description="glob 패턴 (예: **/*.pdf)"),
    extensions: str = Query(None, description="확장자 필터 (쉼표 구분: pdf,docx)"),
    recursive: bool = Query(True),
):
    """디렉토리 스캔 → 전체 파일 인제스트.

    특정 패턴의 파일만 골라서 일괄 처리 가능.
    """
    from app.config import settings

    scan_dir = directory or settings.doc_watch_dir

    ext_set = None
    if extensions:
        ext_set = {f".{e.strip().lstrip('.')}" for e in extensions.split(",")}

    result = scan_and_ingest(
        scan_dir,
        extensions=ext_set,
        pattern=pattern,
        recursive=recursive,
    )

    return result


@router.get("/stats/summary")
def document_stats():
    """문서 처리 현황 요약."""
    with get_session() as session:
        total = session.query(Document).count()
        indexed = session.query(Document).filter(Document.status == "indexed").count()
        failed = session.query(Document).filter(Document.status == "failed").count()
        pending = session.query(Document).filter(Document.status == "pending").count()
        processing = session.query(Document).filter(Document.status == "processing").count()

        total_chunks = session.query(DocChunk).count()

        return {
            "documents": {
                "total": total,
                "indexed": indexed,
                "failed": failed,
                "pending": pending,
                "processing": processing,
            },
            "chunks": {"total": total_chunks},
        }
