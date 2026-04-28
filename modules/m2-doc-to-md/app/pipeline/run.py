import logging
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from .converter import convert
from .dlq import pop_eligible, push as dlq_push
from .lock import acquire, release
from .scanner import scan
from .state import load_state, save_state
from app.metrics import conversion_duration, documents_processed, m3_trigger_latency

MODULE_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = MODULE_ROOT.parents[1]

# In Docker we mount /data2 (read-only sources) and /data/markdown (output).
# For local dev fall back to repo-relative paths under PROJECT_ROOT/data/.
SOURCE_DIR = Path(os.getenv("M2_SOURCE_DIR") or (PROJECT_ROOT / "data" / "documents"))
OUTPUT_DIR = Path(os.getenv("M2_OUTPUT_DIR") or (PROJECT_ROOT / "data" / "markdown"))
LOG_DIR = Path(os.getenv("M2_LOG_DIR") or (MODULE_ROOT / "logs"))
M3_URL = os.getenv("M3_API_URL")


def _setup_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"doc_to_md_{datetime.now().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
    )
    return logging.getLogger("m2")


def _trigger_m3(doc_id: str, md_path: Path, logger: logging.Logger) -> None:
    if not M3_URL:
        logger.info("M3 mock trigger")
        return
    import httpx

    for attempt in range(3):
        t0 = time.time()
        try:
            r = httpx.post(
                f"{M3_URL}/chunk-embed",
                json={"doc_id": doc_id, "markdown_path": str(md_path)},
                headers={"X-Idempotency-Key": doc_id},
                timeout=10,
            )
            r.raise_for_status()
            m3_trigger_latency.observe(time.time() - t0)
            logger.info("M3 trigger %s ok (attempt %d)", doc_id, attempt + 1)
            return
        except Exception as e:
            wait = 2 ** attempt
            logger.warning(
                "M3 trigger fail %s (attempt %d/3): %s, retry in %ds",
                doc_id, attempt + 1, e, wait,
            )
            if attempt < 2:
                time.sleep(wait)
    dlq_push({
        "type": "m3_trigger",
        "doc_id": doc_id,
        "md_path": str(md_path),
        "retry_count": 0,
        "next_retry": time.time() + 60,
    })


def _process_dlq_retries(logger: logging.Logger, new_files: dict, state: dict) -> None:
    """Re-process eligible DLQ entries before main scan."""
    entries = pop_eligible(time.time())
    if not entries:
        return
    logger.info("DLQ: %d entries eligible for retry", len(entries))
    for entry in entries:
        if entry.get("type") == "m3_trigger":
            md_path = Path(entry["md_path"])
            doc_id = entry["doc_id"]
            logger.info("DLQ retry m3_trigger doc_id=%s", doc_id)
            _trigger_m3(doc_id, md_path, logger)
        else:
            rel = entry.get("rel")
            if not rel:
                continue
            retry_count = entry.get("retry_count", 0) + 1
            meta = state.get("files", {}).get(rel, {})
            src = Path(entry.get("abs", ""))
            if not src.exists():
                logger.warning("DLQ retry: source missing %s", rel)
                continue
            owner = uuid.uuid4().hex
            if not acquire(rel, owner):
                logger.warning("DLQ retry: locked %s", rel)
                dlq_push({**entry, "retry_count": retry_count, "next_retry": time.time() + (2 ** retry_count) * 60})
                continue
            try:
                with conversion_duration.time():
                    md_path, status = convert(src, rel, meta.get("hash", ""), OUTPUT_DIR)
                if status.startswith("fail") or status.startswith("error"):
                    documents_processed.labels(status="fail").inc()
                    if retry_count < 3:
                        dlq_push({
                            **entry,
                            "retry_count": retry_count,
                            "next_retry": time.time() + (2 ** retry_count) * 60,
                        })
                else:
                    documents_processed.labels(status="ok").inc()
                    new_files[rel] = {
                        "hash": meta.get("hash", ""),
                        "mtime": meta.get("mtime", 0),
                        "status": status,
                        "md_path": str(md_path.relative_to(OUTPUT_DIR)),
                    }
                    _trigger_m3(rel, md_path, logger)
            except Exception as e:
                logger.exception("DLQ retry FAIL %s: %s", rel, e)
                if retry_count < 3:
                    dlq_push({
                        **entry,
                        "retry_count": retry_count,
                        "next_retry": time.time() + (2 ** retry_count) * 60,
                    })
            finally:
                release(rel, owner)


def run() -> int:
    logger = _setup_logger()
    t0 = time.time()

    if not SOURCE_DIR.exists():
        logger.error("Source dir not found: %s", SOURCE_DIR)
        return 1

    state = load_state()
    mode = "full" if not state.get("files") else "incremental"
    logger.info("Pipeline start mode=%s source=%s output=%s", mode, SOURCE_DIR, OUTPUT_DIR)

    new_files = dict(state.get("files", {}))

    # DLQ retries first
    _process_dlq_retries(logger, new_files, state)

    diff = scan(SOURCE_DIR, state)
    todo = diff["new"] + diff["modified"]
    logger.info(
        "Diff: new=%d modified=%d deleted=%d unchanged=%d",
        len(diff["new"]), len(diff["modified"]), len(diff["deleted"]), len(diff["unchanged"]),
    )

    ok, fail = 0, 0

    for rel in todo:
        meta = diff["current"][rel]
        src = Path(meta["abs"])
        owner = uuid.uuid4().hex
        if not acquire(rel, owner):
            logger.warning("SKIP locked %s", rel)
            continue
        try:
            with conversion_duration.time():
                md_path, status = convert(src, rel, meta["hash"], OUTPUT_DIR)
            logger.info("CONVERT %s -> %s [%s]", rel, md_path.relative_to(OUTPUT_DIR), status)
            if status.startswith("fail"):
                fail += 1
                documents_processed.labels(status="fail").inc()
                new_files[rel] = {"hash": meta["hash"], "mtime": meta["mtime"], "status": status}
                dlq_push({
                    "type": "convert",
                    "rel": rel,
                    "abs": str(src),
                    "retry_count": 1,
                    "next_retry": time.time() + 2 ** 1 * 60,
                })
                continue
            ok += 1
            documents_processed.labels(status="ok").inc()
            new_files[rel] = {
                "hash": meta["hash"],
                "mtime": meta["mtime"],
                "status": status,
                "md_path": str(md_path.relative_to(OUTPUT_DIR)),
            }
            _trigger_m3(rel, md_path, logger)
        except Exception as e:
            logger.exception("CONVERT FAIL %s: %s", rel, e)
            fail += 1
            documents_processed.labels(status="fail").inc()
            new_files[rel] = {"hash": meta["hash"], "mtime": meta["mtime"], "status": f"error:{e}"}
            dlq_push({
                "type": "convert",
                "rel": rel,
                "abs": str(src),
                "retry_count": 1,
                "next_retry": time.time() + 2 ** 1 * 60,
            })
        finally:
            release(rel, owner)

    for rel in diff["deleted"]:
        md_rel = rel.rsplit(".", 1)[0] + ".md"
        md_path = OUTPUT_DIR / md_rel
        if md_path.exists():
            md_path.unlink()
            logger.info("DELETE %s", md_rel)
        new_files.pop(rel, None)

    state["files"] = new_files
    state["last_run"] = datetime.utcnow().isoformat()
    state["last_mode"] = mode
    save_state(state)

    elapsed = time.time() - t0
    logger.info(
        "Pipeline done mode=%s ok=%d fail=%d deleted=%d elapsed=%.2fs",
        mode, ok, fail, len(diff["deleted"]), elapsed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
