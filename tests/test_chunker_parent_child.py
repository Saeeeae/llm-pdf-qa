import os
os.environ.setdefault("SMOKE_TEST_MODE", "true")

from rag_pipeline.pipeline.chunker import chunk_parse_blocks


class FakeBlock:
    def __init__(self, source_text, block_type="text", **kwargs):
        self.source_text = source_text
        self.block_type = block_type
        self.page_number = kwargs.get("page_number")
        self.sheet_name = kwargs.get("sheet_name")
        self.slide_number = kwargs.get("slide_number")
        self.section_path = kwargs.get("section_path")
        self.language = kwargs.get("language")


def test_parent_child_chunks_emitted():
    """Large blocks should produce a parent chunk + child chunks."""
    text = " ".join(f"sentence{i} content here" for i in range(200))
    block = FakeBlock(source_text=text, block_type="text")
    chunks = chunk_parse_blocks([block], chunk_size=64)

    parents = [c for c in chunks if c.get("is_parent")]
    children = [c for c in chunks if not c.get("is_parent")]

    assert len(parents) >= 1, "Should have at least one parent chunk"
    assert len(children) >= 2, "Should have multiple child chunks"
    for child in children:
        assert "parent_chunk_idx" in child, "Child must reference parent"


def test_small_block_no_parent():
    """Blocks that fit in chunk_size should not get parent chunks."""
    block = FakeBlock(source_text="short text", block_type="text")
    chunks = chunk_parse_blocks([block], chunk_size=512)
    assert len(chunks) == 1
    assert not chunks[0].get("is_parent")


def test_parent_contains_full_text():
    """Parent chunk should contain the full block text."""
    text = " ".join(f"word{i}" for i in range(100))
    block = FakeBlock(source_text=text, block_type="text")
    chunks = chunk_parse_blocks([block], chunk_size=20)

    parents = [c for c in chunks if c.get("is_parent")]
    assert len(parents) >= 1
    assert parents[0]["text"] == text


def test_oversized_block_no_parent():
    """Blocks exceeding parent_size should not get parent chunks."""
    # Create text larger than default parent_size (1536 tokens)
    text = " ".join(f"word{i}" for i in range(2000))
    block = FakeBlock(source_text=text, block_type="text")
    chunks = chunk_parse_blocks([block], chunk_size=64)

    parents = [c for c in chunks if c.get("is_parent")]
    assert len(parents) == 0, "Oversized blocks should not have parent chunks"
