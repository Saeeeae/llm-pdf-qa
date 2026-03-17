"""Local package alias for the hyphenated ``rag-sync-monitor`` source tree."""

from pathlib import Path

_SOURCE_DIR = Path(__file__).resolve().parent.parent / "rag-sync-monitor"
__path__ = [str(_SOURCE_DIR)]
