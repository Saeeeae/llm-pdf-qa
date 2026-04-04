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
        self.section_path = kwargs.get("section_path", "")
        self.language = kwargs.get("language")


def test_contextual_prefix_added():
    block = FakeBlock(source_text="매출이 증가했습니다", section_path="매출 분석")
    chunks = chunk_parse_blocks([block], doc_context="삼성전자_2024_연간보고서.pdf")
    assert chunks[0]["text"].startswith("[문서: 삼성전자_2024_연간보고서.pdf")
    assert "매출 분석" in chunks[0]["text"]
    assert chunks[0]["display_text"] == "매출이 증가했습니다"


def test_no_prefix_when_no_context():
    block = FakeBlock(source_text="plain text")
    chunks = chunk_parse_blocks([block])  # no doc_context
    assert not chunks[0]["text"].startswith("[문서:")
    assert "display_text" not in chunks[0]


def test_prefix_without_section():
    block = FakeBlock(source_text="some content", section_path="")
    chunks = chunk_parse_blocks([block], doc_context="report.pdf")
    assert chunks[0]["text"].startswith("[문서: report.pdf]")
    assert "섹션" not in chunks[0]["text"]
