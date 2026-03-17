"""Local package alias for the hyphenated ``rag-serving`` source tree."""

from pathlib import Path

_SOURCE_DIR = Path(__file__).resolve().parent.parent / "rag-serving"
__path__ = [str(_SOURCE_DIR)]
