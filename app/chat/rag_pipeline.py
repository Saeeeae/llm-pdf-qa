"""RAG pipeline: query -> vector search -> prompt build -> vLLM streaming."""
import json
import logging
from typing import Generator

import httpx
from sqlalchemy import text

from app.config import settings
from app.db.models import LLMConfig
from app.db.postgres import get_session
from app.db.vector_store import search_similar
from app.processing.embedder import embed_query

logger = logging.getLogger(__name__)


def get_accessible_folder_ids(user_id: int) -> list[int]:
    with get_session() as session:
        rows = session.execute(
            text(
                "SELECT folder_id FROM folder_access "
                "WHERE user_id = :uid AND is_active = TRUE "
                "AND (expires_at IS NULL OR expires_at > NOW())"
            ),
            {"uid": user_id},
        ).fetchall()
        return [r.folder_id for r in rows]


def get_active_llm_config() -> LLMConfig:
    with get_session() as session:
        config = session.query(LLMConfig).filter(LLMConfig.is_active == True).first()
        if config:
            session.expunge(config)
            return config
    # Fallback default
    fallback = LLMConfig()
    fallback.model_name = settings.vllm_model_name
    fallback.vllm_url = settings.vllm_api_url
    fallback.system_prompt = "당신은 사내 문서를 기반으로 답변하는 AI 어시스턴트입니다. 제공된 문서 내용을 바탕으로 정확하고 도움이 되는 답변을 제공하세요."
    fallback.max_tokens = 4096
    fallback.temperature = 0.7
    fallback.top_p = 0.9
    fallback.context_chunks = 5
    return fallback


def retrieve_context(
    query: str,
    user_id: int,
    user_dept_id: int,
    user_auth_level: int,
    search_scope: str = "all",
    limit: int = 5,
) -> list[dict]:
    query_vector = embed_query(query).tolist()
    accessible_folders = get_accessible_folder_ids(user_id)
    return search_similar(
        query_vector=query_vector,
        limit=limit,
        user_dept_id=user_dept_id,
        user_auth_level=user_auth_level,
        accessible_folder_ids=accessible_folders,
        search_scope=search_scope,
    )


def build_messages(
    system_prompt: str,
    context_chunks: list[dict],
    chat_history: list[dict],
    user_message: str,
) -> list[dict]:
    if context_chunks:
        context_parts = []
        for i, chunk in enumerate(context_chunks, 1):
            page_info = f" p.{chunk['page_number']}" if chunk.get("page_number") else ""
            context_parts.append(f"[문서 {i}: {chunk['file_name']}{page_info}]\n{chunk['text']}")
        context_text = "\n\n".join(context_parts)
        system_with_context = (
            f"{system_prompt}\n\n"
            f"=== 관련 문서 ===\n{context_text}\n=== 문서 끝 ===\n\n"
            "위 문서를 참고하여 답변하세요. 문서에 없는 내용은 모른다고 알려주세요."
        )
    else:
        system_with_context = system_prompt

    messages = [{"role": "system", "content": system_with_context}]
    for msg in chat_history[-20:]:
        messages.append(msg)
    messages.append({"role": "user", "content": user_message})
    return messages


def stream_llm_response(messages: list[dict], config: LLMConfig) -> Generator[str, None, None]:
    payload = {
        "model": config.model_name,
        "messages": messages,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "top_p": config.top_p,
        "stream": True,
    }
    with httpx.Client(timeout=120.0) as client:
        with client.stream("POST", f"{config.vllm_url}/chat/completions", json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    try:
                        chunk = json.loads(line[6:])
                        content = chunk["choices"][0]["delta"].get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError):
                        continue
