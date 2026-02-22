import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="RAG Document Preprocessor")
    subparsers = parser.add_subparsers(dest="command")

    # ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Ingest documents")
    ingest_parser.add_argument("--file", help="Ingest a single file (absolute path)")
    ingest_parser.add_argument("--dir", help="Ingest all files in a directory")

    # sync command
    subparsers.add_parser("sync", help="Run change detection sync on watch directory")

    # scan command
    scan_parser = subparsers.add_parser("scan", help="Scan directory for processable files")
    scan_parser.add_argument("--dir", help="Directory to scan (default: DOC_WATCH_DIR)")
    scan_parser.add_argument("--pattern", help="Glob pattern (e.g. **/*.pdf, report_*.xlsx)")
    scan_parser.add_argument("--ext", help="Extension filter, comma-separated (e.g. pdf,docx)")
    scan_parser.add_argument("--ingest", action="store_true", help="Ingest all scanned files")

    # status command
    subparsers.add_parser("status", help="Show system status")

    args = parser.parse_args()

    if args.command == "ingest":
        from app.pipeline.ingest import ingest_document
        from app.pipeline.sync import run_sync

        if args.file:
            doc_id = ingest_document(args.file)
            print(f"Ingested: doc_id={doc_id}")
        elif args.dir:
            from app.pipeline.scanner import scan_and_ingest
            result = scan_and_ingest(args.dir)
            print(f"Ingestion complete: {result['success']} success, {result['failed']} failed, {result['skipped']} skipped")
        else:
            stats = run_sync()
            print(f"Ingestion complete: {stats}")

    elif args.command == "sync":
        from app.pipeline.sync import run_sync

        stats = run_sync()
        print(f"Sync complete: {stats}")

    elif args.command == "scan":
        from app.config import settings
        from app.pipeline.scanner import scan_files, scan_and_ingest

        scan_dir = args.dir or settings.doc_watch_dir
        ext_set = None
        if args.ext:
            ext_set = {f".{e.strip().lstrip('.')}" for e in args.ext.split(",")}

        if args.ingest:
            result = scan_and_ingest(scan_dir, extensions=ext_set, pattern=args.pattern)
            print(f"Ingest complete: {result['success']} success, {result['failed']} failed, {result['skipped']} skipped")
        else:
            result = scan_files(scan_dir, extensions=ext_set, pattern=args.pattern, compute_hash=False)
            print(f"\nDirectory: {result.directory}")
            print(f"Total files: {result.total_files}")
            print(f"By type: {result.by_type}\n")
            for f in result.files:
                size_kb = f.size / 1024
                print(f"  {f.extension:6s}  {size_kb:>8.1f} KB  {f.name}")

    elif args.command == "status":
        from app.db.postgres import get_session
        from app.db.models import Document, DocChunk

        with get_session() as session:
            total = session.query(Document).count()
            indexed = session.query(Document).filter(Document.status == "indexed").count()
            failed = session.query(Document).filter(Document.status == "failed").count()
            pending = session.query(Document).filter(Document.status == "pending").count()
            chunks = session.query(DocChunk).count()

        print(f"Documents: total={total}, indexed={indexed}, failed={failed}, pending={pending}")
        print(f"Chunks: total={chunks}")

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
