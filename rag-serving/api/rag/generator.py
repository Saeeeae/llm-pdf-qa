import json
import logging
from typing import Generator

import httpx

logger = logging.getLogger(__name__)


def build_messages(system_prompt: str, context_chunks: list[dict], graph_context: str,
                   chat_history: list[dict], user_message: str,
                   web_results: list[dict] | None = None) -> list[dict]:
    parts = [system_prompt]
    if graph_context:
        parts.append(graph_context)
    if context_chunks:
        chunk_parts = []
        for i, chunk in enumerate(context_chunks, 1):
            page = f" p.{chunk['page_number']}" if chunk.get("page_number") else ""
            chunk_parts.append(f"[문서 {i}: {chunk['file_name']}{page}]\n{chunk['content'][:500]}")
        parts.append("=== 관련 문서 ===\n" + "\n\n".join(chunk_parts) + "\n=== 문서 끝 ===")
        parts.append("위 문서를 참고하여 답변하세요. 문서에 없는 내용은 모른다고 알려주세요.")
    if web_results:
        web_parts = []
        for i, result in enumerate(web_results, 1):
            title = result.get("title", "")
            url = result.get("url", "")
            snippet = result.get("snippet", "")
            web_parts.append(f"[웹 {i}: {title}]\nURL: {url}\n{snippet}")
        parts.append("=== 웹 검색 결과 ===\n" + "\n\n".join(web_parts) + "\n=== 웹 검색 끝 ===")
        parts.append("위 웹 검색 결과도 참고하여 답변하세요.")
    messages = [{"role": "system", "content": "\n\n".join(parts)}]
    for msg in chat_history[-20:]:
        messages.append(msg)
    messages.append({"role": "user", "content": user_message})
    return messages


def stream_response(messages: list[dict], vllm_url: str, model_name: str,
                    max_tokens: int = 4096, temperature: float = 0.7,
                    top_p: float = 0.9) -> Generator[str, None, None]:
    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "stream": True,
    }
    with httpx.Client(timeout=120.0) as client:
        with client.stream("POST", f"{vllm_url}/chat/completions", json=payload) as response:
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
