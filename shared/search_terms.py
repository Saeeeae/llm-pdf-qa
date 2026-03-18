import re
from collections import defaultdict

BUILTIN_ALIAS_ROWS = [
    {"canonical_name": "milestone", "alias": "milestone", "alias_type": "business", "language": "en", "boost": 1.15},
    {"canonical_name": "milestone", "alias": "마일스톤", "alias_type": "business", "language": "ko", "boost": 1.15},
    {"canonical_name": "upfront", "alias": "upfront", "alias_type": "business", "language": "en", "boost": 1.15},
    {"canonical_name": "upfront", "alias": "계약금", "alias_type": "business", "language": "ko", "boost": 1.15},
    {"canonical_name": "term sheet", "alias": "term sheet", "alias_type": "business", "language": "en", "boost": 1.1},
    {"canonical_name": "term sheet", "alias": "텀싯", "alias_type": "business", "language": "ko", "boost": 1.1},
    {"canonical_name": "preclinical", "alias": "preclinical", "alias_type": "drug_dev", "language": "en", "boost": 1.1},
    {"canonical_name": "preclinical", "alias": "비임상", "alias_type": "drug_dev", "language": "ko", "boost": 1.1},
    {"canonical_name": "clinical", "alias": "clinical", "alias_type": "drug_dev", "language": "en", "boost": 1.05},
    {"canonical_name": "clinical", "alias": "임상", "alias_type": "drug_dev", "language": "ko", "boost": 1.05},
    {"canonical_name": "efficacy", "alias": "efficacy", "alias_type": "drug_dev", "language": "en", "boost": 1.1},
    {"canonical_name": "efficacy", "alias": "유효성", "alias_type": "drug_dev", "language": "ko", "boost": 1.1},
    {"canonical_name": "safety", "alias": "safety", "alias_type": "drug_dev", "language": "en", "boost": 1.1},
    {"canonical_name": "safety", "alias": "안전성", "alias_type": "drug_dev", "language": "ko", "boost": 1.1},
    {"canonical_name": "target", "alias": "target", "alias_type": "drug_dev", "language": "en", "boost": 1.1},
    {"canonical_name": "target", "alias": "타깃", "alias_type": "drug_dev", "language": "ko", "boost": 1.1},
    {"canonical_name": "target", "alias": "타겟", "alias_type": "drug_dev", "language": "ko", "boost": 1.1},
    {"canonical_name": "indication", "alias": "indication", "alias_type": "drug_dev", "language": "en", "boost": 1.1},
    {"canonical_name": "indication", "alias": "적응증", "alias_type": "drug_dev", "language": "ko", "boost": 1.1},
    {"canonical_name": "nsclc", "alias": "NSCLC", "alias_type": "drug_dev", "language": "en", "boost": 1.2},
    {"canonical_name": "nsclc", "alias": "비소세포폐암", "alias_type": "drug_dev", "language": "ko", "boost": 1.2},
    {"canonical_name": "cmc", "alias": "CMC", "alias_type": "drug_dev", "language": "en", "boost": 1.05},
    {"canonical_name": "cmc", "alias": "제조품질", "alias_type": "drug_dev", "language": "ko", "boost": 1.05},
]

SEARCH_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "were", "have",
    "대한", "관련", "대한한", "에서", "입니다", "있습니다", "하는", "및", "등", "자료",
    "문서", "내용", "요약", "설명", "정리", "해줘", "주세요",
}

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+\-/]{1,63}|[가-힣]{2,20}")


def normalize_search_text(text: str) -> str:
    if not text:
        return ""
    normalized = text.lower()
    normalized = re.sub(r"[^0-9a-z가-힣\s._+\-/]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def extract_candidate_terms(text: str) -> list[str]:
    normalized = normalize_search_text(text)
    seen = set()
    terms = []
    for match in TOKEN_RE.finditer(normalized):
        term = match.group(0).strip()
        if len(term) < 2 or term in SEARCH_STOPWORDS:
            continue
        if term not in seen:
            seen.add(term)
            terms.append(term)
    return terms


def get_alias_rows(session=None) -> list[dict]:
    rows = [dict(row) for row in BUILTIN_ALIAS_ROWS]
    if session is None:
        return rows

    from shared.models.orm import EntityAlias

    db_rows = session.query(EntityAlias).all()
    for row in db_rows:
        rows.append({
            "canonical_name": row.canonical_name,
            "alias": row.alias,
            "alias_type": row.alias_type,
            "language": row.language,
            "boost": row.boost,
        })
    return rows


def expand_terms(base_terms: list[str], alias_rows: list[dict]) -> list[str]:
    groups: dict[str, set[str]] = defaultdict(set)
    alias_to_canonical: dict[str, str] = {}

    for row in alias_rows:
        canonical_norm = normalize_search_text(row["canonical_name"])
        alias_norm = normalize_search_text(row["alias"])
        if not canonical_norm or not alias_norm:
            continue
        groups[canonical_norm].add(row["canonical_name"])
        groups[canonical_norm].add(row["alias"])
        alias_to_canonical[alias_norm] = canonical_norm
        alias_to_canonical[canonical_norm] = canonical_norm

    expanded = []
    seen = set()
    for term in base_terms:
        term_norm = normalize_search_text(term)
        if not term_norm:
            continue
        canonical_norm = alias_to_canonical.get(term_norm)
        variants = groups.get(canonical_norm, {term}) if canonical_norm else {term}
        variants.add(term)
        for variant in sorted(variants, key=lambda value: (len(value), value), reverse=True):
            variant_norm = normalize_search_text(variant)
            if variant_norm and variant_norm not in seen:
                seen.add(variant_norm)
                expanded.append(variant)
    return expanded


def extract_keywords(text: str, alias_rows: list[dict] | None = None, max_keywords: int = 48) -> list[dict]:
    normalized = normalize_search_text(text)
    if not normalized:
        return []

    alias_rows = alias_rows or [dict(row) for row in BUILTIN_ALIAS_ROWS]
    keyword_map: dict[str, dict] = {}

    for term in extract_candidate_terms(normalized):
        keyword_map[term] = {
            "keyword": term,
            "normalized_keyword": term,
            "keyword_type": "token",
            "weight": 1.0 if re.search(r"[가-힣]", term) else 0.9,
        }

    for row in alias_rows:
        alias = row["alias"]
        alias_norm = normalize_search_text(alias)
        canonical = row["canonical_name"]
        canonical_norm = normalize_search_text(canonical)
        if alias_norm and alias_norm in normalized:
            keyword_map[alias_norm] = {
                "keyword": alias,
                "normalized_keyword": alias_norm,
                "keyword_type": row.get("alias_type", "alias"),
                "weight": float(row.get("boost", 1.1)),
            }
            if canonical_norm:
                keyword_map[canonical_norm] = {
                    "keyword": canonical,
                    "normalized_keyword": canonical_norm,
                    "keyword_type": "canonical",
                    "weight": float(row.get("boost", 1.1)) + 0.05,
                }

    ranked = sorted(
        keyword_map.values(),
        key=lambda item: (item["weight"], len(item["normalized_keyword"])),
        reverse=True,
    )
    return ranked[:max_keywords]
