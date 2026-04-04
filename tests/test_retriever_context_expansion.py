import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("SMOKE_TEST_MODE", "true")

# Mock unavailable native dependencies
for mod in ["neo4j", "pgvector", "pgvector.sqlalchemy", "numpy"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from rag_serving.api.rag.retriever import _expand_with_parents


def test_expand_replaces_child_with_parent():
    chunks = [
        {"chunk_id": 10, "parent_chunk_id": 5, "content": "child text", "doc_id": 1},
        {"chunk_id": 20, "parent_chunk_id": None, "content": "standalone", "doc_id": 2},
    ]
    parent_map = {5: {"chunk_id": 5, "content": "full parent text with more context", "doc_id": 1}}
    result = _expand_with_parents(chunks, parent_map)
    assert result[0]["content"] == "full parent text with more context"
    assert result[0]["expanded_from_child"] == 10
    assert result[1]["content"] == "standalone"


def test_expand_deduplicates_parents():
    """Multiple children from same parent should result in one parent entry."""
    chunks = [
        {"chunk_id": 10, "parent_chunk_id": 5, "content": "child1", "doc_id": 1},
        {"chunk_id": 11, "parent_chunk_id": 5, "content": "child2", "doc_id": 1},
    ]
    parent_map = {5: {"chunk_id": 5, "content": "parent text", "doc_id": 1}}
    result = _expand_with_parents(chunks, parent_map)
    assert len(result) == 1
    assert result[0]["content"] == "parent text"


def test_expand_empty():
    assert _expand_with_parents([], {}) == []


def test_expand_no_parents_available():
    """If parent not in map, keep the child chunk as-is (graceful fallback)."""
    chunks = [
        {"chunk_id": 10, "parent_chunk_id": 99, "content": "orphan", "doc_id": 1},
    ]
    result = _expand_with_parents(chunks, {})
    assert len(result) == 1
    assert result[0]["content"] == "orphan"
