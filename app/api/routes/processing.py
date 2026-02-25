import logging
import tempfile
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.parsers import get_parser
from app.processing.chunker import chunk_text
from app.processing.embedder import embed_chunks, embed_query
from app.pipeline.ingest import ingest_document

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


# === Response Models ===

class ParseResponse(BaseModel):
    file_name: str
    total_pages: int
    raw_text_length: int
    metadata: dict


class ChunkResult(BaseModel):
    chunk_idx: int
    text: str
    token_cnt: int


class ChunkResponse(BaseModel):
    file_name: str
    total_chunks: int
    chunk_size: int
    chunk_overlap: int
    chunks: list[ChunkResult]


class EmbedChunkResult(BaseModel):
    chunk_idx: int
    text: str
    token_cnt: int
    vector_dim: int


class EmbedResponse(BaseModel):
    file_name: str
    total_chunks: int
    embed_model: str
    chunks: list[EmbedChunkResult]


class FullPipelineResponse(BaseModel):
    doc_id: int
    file_name: str
    status: str
    total_chunks: int
    message: str


class SearchRequest(BaseModel):
    query: str
    limit: int = 5


class SearchResult(BaseModel):
    score: float
    doc_id: int
    chunk_idx: int
    text: str
    file_name: str


# === Endpoints ===

@router.post("/parse", response_model=ParseResponse)
async def parse_document(file: UploadFile = File(...)):
    """파일 업로드 → MinerU/Office 파서로 파싱만 수행. 결과 텍스트 반환."""
    _validate_extension(file.filename)

    with tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        parser = get_parser(tmp_path)
        result = parser.parse(tmp_path)
        return ParseResponse(
            file_name=file.filename,
            total_pages=result.total_pages,
            raw_text_length=len(result.raw_text),
            metadata=result.metadata,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/chunk", response_model=ChunkResponse)
async def chunk_document(
    file: UploadFile = File(...),
    chunk_size: int = Query(default=None, description="청크 크기 (tokens). 기본: 512"),
    chunk_overlap: int = Query(default=None, description="청크 오버랩 (tokens). 기본: 50"),
):
    """파일 업로드 → 파싱 → 청킹. 청크 목록 반환."""
    _validate_extension(file.filename)

    cs = chunk_size or settings.chunk_size
    co = chunk_overlap or settings.chunk_overlap

    with tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        parser = get_parser(tmp_path)
        result = parser.parse(tmp_path)
        chunks = chunk_text(result.raw_text, chunk_size=cs, chunk_overlap=co)

        return ChunkResponse(
            file_name=file.filename,
            total_chunks=len(chunks),
            chunk_size=cs,
            chunk_overlap=co,
            chunks=[
                ChunkResult(
                    chunk_idx=c["chunk_idx"],
                    text=c["text"],
                    token_cnt=c["token_cnt"],
                )
                for c in chunks
            ],
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/embed", response_model=EmbedResponse)
async def embed_document(
    file: UploadFile = File(...),
    chunk_size: int = Query(default=None),
    chunk_overlap: int = Query(default=None),
):
    """파일 업로드 → 파싱 → 청킹 → 임베딩. 벡터 차원 정보 반환 (벡터 자체는 미포함)."""
    _validate_extension(file.filename)

    cs = chunk_size or settings.chunk_size
    co = chunk_overlap or settings.chunk_overlap

    with tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        parser = get_parser(tmp_path)
        result = parser.parse(tmp_path)
        chunks = chunk_text(result.raw_text, chunk_size=cs, chunk_overlap=co)

        if not chunks:
            return EmbedResponse(
                file_name=file.filename,
                total_chunks=0,
                embed_model=settings.embed_model,
                chunks=[],
            )

        texts = [c["text"] for c in chunks]
        embeddings = embed_chunks(texts)

        return EmbedResponse(
            file_name=file.filename,
            total_chunks=len(chunks),
            embed_model=settings.embed_model,
            chunks=[
                EmbedChunkResult(
                    chunk_idx=c["chunk_idx"],
                    text=c["text"][:200],
                    token_cnt=c["token_cnt"],
                    vector_dim=embeddings.shape[1],
                )
                for c in chunks
            ],
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/full-pipeline", response_model=FullPipelineResponse)
async def full_pipeline(file: UploadFile = File(...)):
    """파일 업로드 → 파싱 → 청킹 → 임베딩 → PostgreSQL 저장 (벡터 포함).

    전체 파이프라인을 동기적으로 실행하여 결과를 바로 반환.
    """
    _validate_extension(file.filename)

    # 감시 폴더에 파일 저장
    save_dir = Path(settings.doc_watch_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / file.filename

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        doc_id = ingest_document(str(save_path))

        from app.db.postgres import get_session
        from app.db.models import Document, DocChunk

        with get_session() as session:
            doc = session.query(Document).filter(Document.doc_id == doc_id).first()
            chunk_count = session.query(DocChunk).filter(DocChunk.doc_id == doc_id).count()

        return FullPipelineResponse(
            doc_id=doc_id,
            file_name=file.filename,
            status=doc.status if doc else "unknown",
            total_chunks=chunk_count,
            message=f"Document processed: {chunk_count} chunks created",
        )
    except Exception as e:
        logger.error("Full pipeline failed for %s: %s", file.filename, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=list[SearchResult])
def search_vectors(request: SearchRequest):
    """쿼리 텍스트로 벡터 유사도 검색 (pgvector cosine similarity)."""
    from app.db.vector_store import search_similar

    query_vector = embed_query(request.query)
    results = search_similar(vector=query_vector.tolist(), limit=request.limit)

    return [
        SearchResult(
            score=r["score"],
            doc_id=r["doc_id"],
            chunk_idx=r["chunk_idx"],
            text=r["text"],
            file_name=r["file_name"],
        )
        for r in results
    ]


def _validate_extension(filename: str):
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
