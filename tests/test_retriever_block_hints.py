from rag_serving.api.rag.retriever import apply_exact_match_boost, infer_block_type_preferences


def test_infer_block_type_preferences_detects_table_queries():
    preferences = infer_block_type_preferences("표 형태로 EGFR 적응증 보여줘", ["EGFR", "적응증"])
    assert preferences["table"] > 0
    assert preferences["caption"] >= 0


def test_apply_exact_match_boost_prefers_table_block_for_table_query():
    results = [
        {
            "chunk_id": 1,
            "doc_id": 1,
            "file_name": "summary.xlsx",
            "content": "| Target | Value |\n| EGFR | NSCLC |",
            "block_type": "table",
            "chunk_type": "table",
            "sheet_name": "Sheet1",
            "page_number": 1,
            "rrf_score": 0.5,
        },
        {
            "chunk_id": 2,
            "doc_id": 1,
            "file_name": "summary.xlsx",
            "content": "EGFR 적응증 설명 문장",
            "block_type": "text",
            "chunk_type": "text",
            "page_number": 1,
            "rrf_score": 0.5,
        },
    ]

    ranked = apply_exact_match_boost("표로 EGFR 적응증 보여줘", ["EGFR", "적응증"], results)
    assert ranked[0]["chunk_id"] == 1
