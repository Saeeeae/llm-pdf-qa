import os
os.environ.setdefault("SMOKE_TEST_MODE", "true")

from rag_pipeline.pipeline.chunker import chunk_parse_blocks, token_length


class FakeBlock:
    def __init__(self, source_text, block_type="table", **kwargs):
        self.source_text = source_text
        self.block_type = block_type
        self.page_number = kwargs.get("page_number")
        self.sheet_name = kwargs.get("sheet_name")
        self.slide_number = kwargs.get("slide_number")
        self.section_path = kwargs.get("section_path")
        self.language = kwargs.get("language")


def _make_large_table(rows: int = 60) -> str:
    header = "| Col A | Col B | Col C |"
    separator = "| --- | --- | --- |"
    data_rows = [f"| val{i}_a | val{i}_b | val{i}_c |" for i in range(rows)]
    return "\n".join([header, separator] + data_rows)


def test_table_header_propagated_to_continuation_chunks():
    table_text = _make_large_table(60)
    block = FakeBlock(source_text=table_text, block_type="table")
    chunks = chunk_parse_blocks([block], chunk_size=64)
    assert len(chunks) > 1, "Table should be split into multiple chunks"
    header_line = "| Col A | Col B | Col C |"
    for chunk in chunks:
        assert chunk["text"].startswith(header_line), (
            f"Chunk {chunk['chunk_idx']} missing header: {chunk['text'][:80]}"
        )


def test_small_table_not_modified():
    table_text = "| A | B |\n| --- | --- |\n| 1 | 2 |"
    block = FakeBlock(source_text=table_text, block_type="table")
    chunks = chunk_parse_blocks([block], chunk_size=512)
    assert len(chunks) == 1
    assert chunks[0]["text"] == table_text
