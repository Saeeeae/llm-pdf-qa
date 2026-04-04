import logging
import re
from neo4j import GraphDatabase
from shared.config import shared_settings
from shared.db import get_session
from shared.models.orm import GraphEntity
from rag_pipeline.config import pipeline_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for rule-based NER (no external NLP dependencies)
# ---------------------------------------------------------------------------

# Korean organisation suffixes — order matters: longer suffixes first
_ORG_SUFFIXES = (
    "유한책임회사", "주식회사", "유한회사", "합자회사", "합명회사",
    "사회적협동조합", "협동조합", "재단법인", "사단법인",
    "법인", "주식", "그룹", "홀딩스", "코퍼레이션",
    "본부", "사업부", "부서", "센터", "연구소", "연구원",
    "팀", "실", "부", "과", "처", "국", "원", "원",
)

# Prefix patterns (주식회사 삼성전자, 재단법인 카카오 등)
_ORG_PREFIXES = ("주식회사", "유한회사", "재단법인", "사단법인", "협동조합")

# Korean Hangul + optional latin tail, 2-15 chars, followed by an org suffix
_ORG_SUFFIX_RE = re.compile(
    r"[가-힣A-Za-z0-9&\s]{1,14}(?:" + "|".join(re.escape(s) for s in _ORG_SUFFIXES) + r")"
)

# Prefix form: 주식회사 <name>
_ORG_PREFIX_RE = re.compile(
    r"(?:" + "|".join(re.escape(p) for p in _ORG_PREFIXES) + r")\s+[가-힣A-Za-z][가-힣A-Za-z0-9\s]{1,20}"
)

# Korean person name: 성(1 char) + 이름(1–3 chars), followed by a role/title indicator
_PERSON_TITLE_RE = re.compile(
    r"[가-힣]{1}[가-힣]{1,3}"
    r"(?:씨|님|대표|이사|부장|차장|과장|팀장|실장|본부장|사장|회장|대리|사원|주임|교수|박사|선생|원장|소장|연구원)"
)

# Dates — various Korean/ISO formats
_DATE_PATTERNS = [
    re.compile(r"\d{4}년\s*\d{1,2}월(?:\s*\d{1,2}일)?"),   # 2024년 3월 15일
    re.compile(r"\d{4}[-./]\d{1,2}[-./]\d{1,2}"),           # 2024-03-15
    re.compile(r"\d{1,2}월\s*\d{1,2}일"),                    # 3월 15일
    re.compile(r"\d{4}년도?"),                               # 2024년 / 2024년도
    re.compile(r"(?:1분기|2분기|3분기|4분기|상반기|하반기)\s*\d{4}년?"),  # 1분기 2024년
    re.compile(r"\d{4}년?\s*(?:1분기|2분기|3분기|4분기|상반기|하반기)"),
]

# Technical terms — ALL-CAPS acronyms (≥2 chars) and CamelCase identifiers
_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")
_CAMEL_RE = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b")

# Version / product codes: alphanumeric tokens that look like product names
_PRODUCT_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9\-]{2,}\s*[vV]?\d+(?:\.\d+)*\b")


def get_neo4j_driver():
    """Create a Neo4j driver using shared settings."""
    return GraphDatabase.driver(
        shared_settings.neo4j_url,
        auth=(shared_settings.neo4j_user, shared_settings.neo4j_password),
    )


def _deduplicate(entities: list[dict]) -> list[dict]:
    """Remove exact duplicates (same name+type), keeping first occurrence."""
    seen: set[tuple[str, str]] = set()
    result = []
    for ent in entities:
        key = (ent["name"].strip(), ent["type"])
        if key not in seen:
            seen.add(key)
            result.append(ent)
    return result


def _compute_cooccurrence_pairs(entities: list[dict]) -> list[tuple[str, str]]:
    """Return sorted entity name pairs for co-occurrence edges."""
    names = sorted(set(e["name"].strip() for e in entities))
    return [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]


def canonicalize_entities(entities: list[dict], alias_map: dict[str, str]) -> list[dict]:
    """Resolve entity surface forms to canonical names via alias lookup."""
    for ent in entities:
        name = ent["name"].strip()
        normalized = name.lower().strip()
        canonical = alias_map.get(normalized) or alias_map.get(name) or name
        ent["canonical_name"] = canonical
    return entities


VALID_PREDICATES = {
    "PRODUCES", "ACQUIRES", "COMPETES_WITH", "REPORTS_TO",
    "LOCATED_IN", "PART_OF", "USES", "SUPPLIES_TO", "PARTNERS_WITH",
}


def _build_relationship_prompt(text: str, entities: list[dict]) -> str:
    entity_list = ", ".join(f"{e['name']}({e['type']})" for e in entities[:20])
    return (
        "주어진 텍스트에서 엔티티 간의 관계를 추출하세요.\n\n"
        f"엔티티: {entity_list}\n\n"
        f"텍스트: {text[:2000]}\n\n"
        f"유효한 관계 유형: {', '.join(sorted(VALID_PREDICATES))}\n\n"
        'JSON 배열로 응답하세요: [{"subject": "...", "predicate": "...", "object": "..."}]\n'
        "관계가 없으면 빈 배열 []을 반환하세요."
    )


def _parse_relationship_response(raw: str) -> list[dict]:
    import json
    if not raw or not raw.strip():
        return []
    try:
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start < 0 or end <= start:
            return []
        data = json.loads(raw[start:end])
    except (json.JSONDecodeError, ValueError):
        return []
    result = []
    for item in data:
        if (
            isinstance(item, dict)
            and item.get("subject")
            and item.get("predicate") in VALID_PREDICATES
            and item.get("object")
        ):
            result.append(item)
    return result


def extract_relationships_llm(doc_id: int, text: str, entities: list[dict]):
    """Extract typed relationships between entities using LLM (opt-in)."""
    if not entities or len(entities) < 2:
        return

    import httpx
    from shared.config import shared_settings

    prompt = _build_relationship_prompt(text, entities)

    try:
        response = httpx.post(
            f"{shared_settings.vllm_base_url}/v1/chat/completions",
            json={
                "model": shared_settings.vllm_model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1024,
                "temperature": 0.1,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("LLM relationship extraction failed: %s", e)
        return

    relationships = _parse_relationship_response(raw)
    if not relationships:
        return

    try:
        driver = get_neo4j_driver()
        with driver.session() as neo_session:
            for rel in relationships:
                neo_session.run(
                    "MATCH (a:Entity {name: $subject}), (b:Entity {name: $object}) "
                    "MERGE (a)-[r:RELATES {type: $predicate}]->(b) "
                    "ON CREATE SET r.weight = 1 "
                    "ON MATCH SET r.weight = r.weight + 1",
                    subject=rel["subject"], object=rel["object"], predicate=rel["predicate"],
                )
        driver.close()
        logger.info("Stored %d typed relationships for doc_id=%d", len(relationships), doc_id)
    except Exception as e:
        logger.warning("Neo4j relationship storage failed (non-fatal): %s", e)


def _strip_noise(text: str) -> str:
    """Collapse excessive whitespace for cleaner matching."""
    return re.sub(r"\s+", " ", text).strip()


def extract_entities(text: str) -> list[dict]:
    """
    Regex + heuristic NER for Korean/mixed-language corporate documents.

    Returns a list of dicts with keys:
        name       (str)  — surface form of the entity
        type       (str)  — ORG | PERSON | DATE | TECH
        start_char (int)  — byte offset in the original text
        end_char   (int)  — exclusive byte offset
    """
    if not text:
        return []

    text = _strip_noise(text)
    entities: list[dict] = []

    def _add(match: re.Match, label: str) -> None:
        name = match.group(0).strip()
        if len(name) < 2:
            return
        entities.append({
            "name": name,
            "type": label,
            "start_char": match.start(),
            "end_char": match.end(),
        })

    # --- ORG: suffix form ---
    for m in _ORG_SUFFIX_RE.finditer(text):
        name = m.group(0).strip()
        if len(name) >= 3:  # avoid single-char suffix matches
            entities.append({"name": name, "type": "ORG",
                              "start_char": m.start(), "end_char": m.end()})

    # --- ORG: prefix form ---
    for m in _ORG_PREFIX_RE.finditer(text):
        _add(m, "ORG")

    # --- PERSON ---
    for m in _PERSON_TITLE_RE.finditer(text):
        _add(m, "PERSON")

    # --- DATE ---
    for pattern in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            _add(m, "DATE")

    # --- TECH: acronyms ---
    # Skip very common English stopwords that happen to be all-caps
    _SKIP_ACRONYMS = {
        "THE", "AND", "FOR", "NOT", "BUT", "ARE", "WAS", "HAS",
        "PDF", "URL", "FAQ", "TBD", "ETC", "VS", "RE",
    }
    for m in _ACRONYM_RE.finditer(text):
        name = m.group(0)
        if name not in _SKIP_ACRONYMS and len(name) >= 2:
            entities.append({"name": name, "type": "TECH",
                              "start_char": m.start(), "end_char": m.end()})

    # --- TECH: CamelCase ---
    for m in _CAMEL_RE.finditer(text):
        _add(m, "TECH")

    # --- TECH: product/version tokens ---
    for m in _PRODUCT_RE.finditer(text):
        _add(m, "TECH")

    entities = _deduplicate(entities)
    logger.debug("extract_entities: found %d entities in %d chars", len(entities), len(text))
    return entities


def store_entities(doc_id: int, entities: list[dict]):
    if not entities:
        return

    if pipeline_settings.graph_enable_canonicalization:
        from shared.search_terms import get_alias_rows
        with get_session() as db_session:
            alias_rows = get_alias_rows(db_session)
        alias_map = {row.normalized_alias: row.canonical_name for row in alias_rows}
        entities = canonicalize_entities(entities, alias_map)

    with get_session() as session:
        session.query(GraphEntity).filter(GraphEntity.doc_id == doc_id).delete()
        for ent in entities:
            session.add(GraphEntity(
                doc_id=doc_id,
                entity_name=ent["name"],
                entity_type=ent["type"],
                canonical_name=ent.get("canonical_name"),
            ))

    try:
        driver = get_neo4j_driver()
        with driver.session() as neo_session:
            for ent in entities:
                entity_key = ent.get("canonical_name") or ent["name"]
                result = neo_session.run(
                    "MERGE (e:Entity {name: $name}) "
                    "SET e.type = $type, e.surface_forms = "
                    "CASE WHEN $surface IN coalesce(e.surface_forms, []) THEN e.surface_forms "
                    "ELSE coalesce(e.surface_forms, []) + [$surface] END "
                    "RETURN elementId(e) AS node_id",
                    name=entity_key, type=ent["type"], surface=ent["name"],
                )
                record = result.single()
                if record:
                    ent["neo4j_node_id"] = record["node_id"]
            for ent in entities:
                entity_key = ent.get("canonical_name") or ent["name"]
                neo_session.run(
                    "MATCH (e:Entity {name: $name}) "
                    "MERGE (d:Document {doc_id: $doc_id}) "
                    "MERGE (e)-[:APPEARS_IN]->(d)",
                    name=entity_key, doc_id=doc_id,
                )
            if len(entities) > 1:
                pairs = _compute_cooccurrence_pairs(entities)
                for name_a, name_b in pairs:
                    neo_session.run(
                        "MATCH (a:Entity {name: $a}), (b:Entity {name: $b}) "
                        "MERGE (a)-[r:CO_OCCURS]->(b) "
                        "ON CREATE SET r.weight = 1, r.doc_count = 1 "
                        "ON MATCH SET r.weight = r.weight + 1, r.doc_count = r.doc_count + 1",
                        a=name_a, b=name_b,
                    )
        driver.close()
    except Exception as e:
        logger.warning("Neo4j storage failed (non-fatal): %s", e)

    logger.info("Stored %d entities for doc_id=%d", len(entities), doc_id)
