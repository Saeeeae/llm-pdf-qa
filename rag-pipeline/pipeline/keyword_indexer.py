from shared.models.orm import DocKeyword
from shared.search_terms import extract_keywords, get_alias_rows


def sync_chunk_keywords(session, chunk_records: list) -> int:
    alias_rows = get_alias_rows(session)
    total = 0

    for chunk in chunk_records:
        for keyword in extract_keywords(chunk.content, alias_rows=alias_rows):
            session.add(DocKeyword(
                doc_id=chunk.doc_id,
                chunk_id=chunk.chunk_id,
                keyword=keyword["keyword"],
                normalized_keyword=keyword["normalized_keyword"],
                keyword_type=keyword["keyword_type"],
                weight=keyword["weight"],
            ))
            total += 1

    return total
