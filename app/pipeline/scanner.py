import logging
import os
from dataclasses import dataclass, field
from glob import glob
from pathlib import Path

from app.pipeline.ingest import compute_file_hash

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".xls", ".pptx",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff",
}


@dataclass
class FileInfo:
    path: str
    name: str
    extension: str
    size: int
    hash: str


@dataclass
class ScanResult:
    directory: str
    total_files: int
    files: list[FileInfo] = field(default_factory=list)
    by_type: dict[str, int] = field(default_factory=dict)


def scan_files(
    directory: str,
    extensions: set[str] | None = None,
    pattern: str | None = None,
    recursive: bool = True,
    compute_hash: bool = True,
) -> ScanResult:
    """디렉토리를 스캔하여 지원되는 파일 목록을 반환.

    Args:
        directory: 스캔할 디렉토리 경로
        extensions: 필터링할 확장자 ({".pdf", ".docx"} 등). None이면 전체 지원 확장자
        pattern: glob 패턴 (예: "**/*.pdf", "report_*.xlsx"). None이면 전체 파일
        recursive: 하위 디렉토리 포함 여부
        compute_hash: SHA-256 해시 계산 여부 (대량 파일 시 False로 빠르게 스캔)

    Returns:
        ScanResult: 파일 목록 + 타입별 집계
    """
    target_exts = extensions or SUPPORTED_EXTENSIONS
    files: list[FileInfo] = []
    by_type: dict[str, int] = {}

    if pattern:
        # glob 패턴 사용
        full_pattern = os.path.join(directory, pattern)
        matched_paths = glob(full_pattern, recursive=recursive)
        candidates = [Path(p) for p in matched_paths if Path(p).is_file()]
    else:
        # 전체 디렉토리 스캔
        candidates = []
        if recursive:
            for root, _, filenames in os.walk(directory):
                for fname in filenames:
                    candidates.append(Path(root) / fname)
        else:
            candidates = [p for p in Path(directory).iterdir() if p.is_file()]

    for fpath in candidates:
        ext = fpath.suffix.lower()
        if ext not in target_exts:
            continue

        file_hash = compute_file_hash(str(fpath)) if compute_hash else ""
        file_size = fpath.stat().st_size

        files.append(FileInfo(
            path=str(fpath),
            name=fpath.name,
            extension=ext,
            size=file_size,
            hash=file_hash,
        ))

        ext_key = ext.lstrip(".")
        by_type[ext_key] = by_type.get(ext_key, 0) + 1

    # 이름순 정렬
    files.sort(key=lambda f: f.name)

    logger.info("Scanned %s: %d files found", directory, len(files))

    return ScanResult(
        directory=directory,
        total_files=len(files),
        files=files,
        by_type=by_type,
    )


def scan_and_ingest(
    directory: str,
    extensions: set[str] | None = None,
    pattern: str | None = None,
    recursive: bool = True,
) -> dict:
    """디렉토리 스캔 후 전체 파일 인제스트.

    Returns:
        {"total": int, "success": int, "failed": int, "skipped": int, "details": [...]}
    """
    from app.pipeline.ingest import ingest_document

    scan = scan_files(directory, extensions=extensions, pattern=pattern, recursive=recursive)

    results = {"total": scan.total_files, "success": 0, "failed": 0, "skipped": 0, "details": []}

    for f in scan.files:
        try:
            doc_id = ingest_document(f.path)
            results["success"] += 1
            results["details"].append({"file": f.name, "status": "ok", "doc_id": doc_id})
        except Exception as e:
            if "already indexed" in str(e).lower():
                results["skipped"] += 1
                results["details"].append({"file": f.name, "status": "skipped"})
            else:
                results["failed"] += 1
                results["details"].append({"file": f.name, "status": "error", "error": str(e)[:200]})
                logger.error("Failed to ingest %s: %s", f.name, e)

    logger.info(
        "Batch ingest: total=%d, success=%d, failed=%d, skipped=%d",
        results["total"], results["success"], results["failed"], results["skipped"],
    )
    return results
