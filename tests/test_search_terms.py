from shared.search_terms import (
    BUILTIN_ALIAS_ROWS,
    expand_terms,
    extract_candidate_terms,
    extract_keywords,
    normalize_search_text,
)


def test_normalize_search_text_keeps_ko_en_terms():
    assert normalize_search_text("Project Atlas / EGFR 적응증") == "project atlas / egfr 적응증"


def test_expand_terms_includes_korean_and_english_aliases():
    expanded = expand_terms(["마일스톤", "적응증"], BUILTIN_ALIAS_ROWS)
    normalized = {normalize_search_text(term) for term in expanded}
    assert "마일스톤" in normalized
    assert "milestone" in normalized
    assert "적응증" in normalized
    assert "indication" in normalized


def test_extract_candidate_terms_filters_short_noise():
    terms = extract_candidate_terms("EGFR 관련 적응증 및 milestone 요약")
    assert "egfr" in terms
    assert "적응증" in terms
    assert "milestone" in terms
    assert "및" not in terms


def test_extract_keywords_promotes_alias_hits():
    keywords = extract_keywords("Project Atlas의 적응증은 NSCLC이고 milestone status는 pending 입니다.")
    normalized = {item["normalized_keyword"] for item in keywords}
    assert "적응증" in normalized
    assert "indication" in normalized
    assert "nsclc" in normalized
    assert "milestone" in normalized
