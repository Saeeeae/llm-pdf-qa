"""Local package alias for the hyphenated ``rag-pipeline`` source tree.

This keeps local development commands such as
``uvicorn rag_pipeline.api.main:app`` working without Docker.
"""

from pathlib import Path

_SOURCE_DIR = Path(__file__).resolve().parent.parent / "rag-pipeline"
__path__ = [str(_SOURCE_DIR)]
