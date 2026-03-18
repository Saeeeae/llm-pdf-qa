from rag_pipeline.pipeline.chunker import chunk_parse_blocks
from rag_pipeline.pipeline.parser import ParseBlock


def test_chunk_parse_blocks_preserves_block_metadata():
    blocks = [
        ParseBlock(
            block_type="text",
            source_text="적응증 관련 요약 문장입니다.",
            page_number=2,
            section_path="Overview",
        ),
        ParseBlock(
            block_type="table",
            source_text="| Target | Value |\n| --- | --- |\n| EGFR | NSCLC |",
            page_number=3,
            sheet_name="Summary",
        ),
    ]

    chunks = chunk_parse_blocks(blocks, chunk_size=128, chunk_overlap=16)

    assert len(chunks) == 2
    assert chunks[0]["chunk_idx"] == 0
    assert chunks[0]["chunk_type"] == "text"
    assert chunks[0]["page_number"] == 2
    assert chunks[0]["section_path"] == "Overview"
    assert chunks[0]["block_idx"] == 0

    assert chunks[1]["chunk_idx"] == 1
    assert chunks[1]["chunk_type"] == "table"
    assert chunks[1]["page_number"] == 3
    assert chunks[1]["sheet_name"] == "Summary"
    assert chunks[1]["block_idx"] == 1
