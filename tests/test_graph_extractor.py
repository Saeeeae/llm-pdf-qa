import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("SMOKE_TEST_MODE", "true")

# Mock unavailable native dependencies before importing
for mod in ["neo4j", "pgvector", "pgvector.sqlalchemy", "numpy"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from rag_pipeline.pipeline.graph_extractor import extract_entities, _deduplicate


def test_extract_org_suffix():
    entities = extract_entities("삼성전자주식회사가 발표한 내용입니다")
    org_names = [e["name"] for e in entities if e["type"] == "ORG"]
    assert any("삼성전자" in n for n in org_names)


def test_extract_org_prefix():
    entities = extract_entities("주식회사 카카오에서 발표했습니다")
    org_names = [e["name"] for e in entities if e["type"] == "ORG"]
    assert any("카카오" in n for n in org_names)


def test_extract_person():
    # Regex requires name+title without space (e.g., 김철수대표)
    entities = extract_entities("김철수대표가 발표했습니다")
    person_names = [e["name"] for e in entities if e["type"] == "PERSON"]
    assert any("김철수" in n for n in person_names)


def test_extract_date_korean():
    entities = extract_entities("2024년 3월 15일에 발표되었습니다")
    dates = [e["name"] for e in entities if e["type"] == "DATE"]
    assert any("2024년" in d for d in dates)


def test_extract_date_iso():
    entities = extract_entities("날짜: 2024-03-15 기준")
    dates = [e["name"] for e in entities if e["type"] == "DATE"]
    assert any("2024-03-15" in d for d in dates)


def test_extract_tech_acronym():
    entities = extract_entities("HBM 기술이 GPU 시장을 견인")
    tech_names = [e["name"] for e in entities if e["type"] == "TECH"]
    assert "HBM" in tech_names
    assert "GPU" in tech_names


def test_extract_tech_camelcase():
    entities = extract_entities("GraphRag 기술을 활용합니다")
    tech_names = [e["name"] for e in entities if e["type"] == "TECH"]
    assert any("GraphRag" in n for n in tech_names)


def test_deduplicate():
    entities = [
        {"name": "삼성전자", "type": "ORG"},
        {"name": "삼성전자", "type": "ORG"},
        {"name": "삼성전자", "type": "TECH"},
    ]
    result = _deduplicate(entities)
    assert len(result) == 2


def test_empty_input():
    assert extract_entities("") == []


def test_whitespace_input():
    assert extract_entities("   ") == []


def test_extract_product_version():
    entities = extract_entities("Model V2.1 버전이 출시되었습니다")
    tech_names = [e["name"] for e in entities if e["type"] == "TECH"]
    assert any("V2.1" in n or "Model" in n for n in tech_names)


def test_entity_has_required_fields():
    entities = extract_entities("삼성전자주식회사 HBM 기술")
    for ent in entities:
        assert "name" in ent
        assert "type" in ent
        assert "start_char" in ent
        assert "end_char" in ent
        assert ent["type"] in {"ORG", "PERSON", "DATE", "TECH"}


def test_compute_cooccurrence_pairs():
    from rag_pipeline.pipeline.graph_extractor import _compute_cooccurrence_pairs
    entities = [
        {"name": "A", "type": "ORG"},
        {"name": "B", "type": "TECH"},
        {"name": "C", "type": "PERSON"},
    ]
    pairs = _compute_cooccurrence_pairs(entities)
    assert ("A", "B") in pairs
    assert ("A", "C") in pairs
    assert ("B", "C") in pairs
    assert len(pairs) == 3
    for a, b in pairs:
        assert a < b


def test_compute_cooccurrence_pairs_single():
    from rag_pipeline.pipeline.graph_extractor import _compute_cooccurrence_pairs
    entities = [{"name": "Only", "type": "ORG"}]
    assert _compute_cooccurrence_pairs(entities) == []


def test_compute_cooccurrence_pairs_empty():
    from rag_pipeline.pipeline.graph_extractor import _compute_cooccurrence_pairs
    assert _compute_cooccurrence_pairs([]) == []


def test_canonicalize_entities():
    from rag_pipeline.pipeline.graph_extractor import canonicalize_entities
    entities = [
        {"name": "삼성전자주식회사", "type": "ORG"},
        {"name": "Samsung", "type": "ORG"},
    ]
    alias_map = {"삼성전자주식회사": "삼성전자", "samsung": "삼성전자"}
    result = canonicalize_entities(entities, alias_map)
    assert result[0]["canonical_name"] == "삼성전자"
    assert result[1]["canonical_name"] == "삼성전자"


def test_canonicalize_no_alias():
    from rag_pipeline.pipeline.graph_extractor import canonicalize_entities
    entities = [{"name": "Unknown Corp", "type": "ORG"}]
    result = canonicalize_entities(entities, {})
    assert result[0]["canonical_name"] == "Unknown Corp"


def test_build_relationship_prompt():
    from rag_pipeline.pipeline.graph_extractor import _build_relationship_prompt
    entities = [{"name": "삼성전자", "type": "ORG"}, {"name": "HBM", "type": "TECH"}]
    text = "삼성전자가 HBM 메모리를 생산합니다"
    prompt = _build_relationship_prompt(text, entities)
    assert "삼성전자" in prompt
    assert "HBM" in prompt
    assert "PRODUCES" in prompt


def test_parse_relationship_response_valid():
    from rag_pipeline.pipeline.graph_extractor import _parse_relationship_response
    raw = '[{"subject": "삼성전자", "predicate": "PRODUCES", "object": "HBM"}]'
    result = _parse_relationship_response(raw)
    assert len(result) == 1
    assert result[0]["predicate"] == "PRODUCES"


def test_parse_relationship_response_invalid_predicate():
    from rag_pipeline.pipeline.graph_extractor import _parse_relationship_response
    raw = '[{"subject": "A", "predicate": "INVALID_PRED", "object": "B"}]'
    result = _parse_relationship_response(raw)
    assert len(result) == 0


def test_parse_relationship_response_malformed():
    from rag_pipeline.pipeline.graph_extractor import _parse_relationship_response
    assert _parse_relationship_response("not json") == []
    assert _parse_relationship_response("") == []


def test_parse_relationship_response_with_surrounding_text():
    from rag_pipeline.pipeline.graph_extractor import _parse_relationship_response
    raw = 'Here are the results: [{"subject": "A", "predicate": "USES", "object": "B"}] done.'
    result = _parse_relationship_response(raw)
    assert len(result) == 1
    assert result[0]["predicate"] == "USES"
