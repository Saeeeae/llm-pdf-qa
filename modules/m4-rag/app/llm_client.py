import os
import json
import time
from typing import AsyncIterator, List, Dict

import httpx

VLLM_URL = os.getenv("VLLM_URL", "http://vllm:8000/v1")
VLLM_MODEL = os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "6000"))


# B2.5 — simple fail-counter circuit breaker
class CB:
    def __init__(self, threshold: int = 5, recovery: int = 30):
        self.fails = 0
        self.opened_at: float = 0.0
        self.threshold = threshold
        self.recovery = recovery

    def can_call(self) -> bool:
        if self.fails >= self.threshold:
            return time.time() - self.opened_at > self.recovery
        return True

    def record(self, ok: bool) -> None:
        if ok:
            self.fails = 0
        else:
            self.fails += 1
            if self.fails >= self.threshold:
                self.opened_at = time.time()


_cb = CB()


async def generate_stream(
    messages: List[Dict], max_tokens: int = 1024
) -> AsyncIterator[str]:
    """Stream tokens from vLLM OpenAI-compatible endpoint."""
    if not _cb.can_call():
        raise RuntimeError("vllm circuit open")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as c:
            async with c.stream(
                "POST",
                f"{VLLM_URL}/chat/completions",
                json={
                    "model": VLLM_MODEL,
                    "messages": messages,
                    "stream": True,
                    "max_tokens": max_tokens,
                },
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        delta = (
                            json.loads(data)["choices"][0]["delta"].get("content", "")
                        )
                        if delta:
                            yield delta
                    except (KeyError, json.JSONDecodeError):
                        continue
        _cb.record(True)
    except Exception:
        _cb.record(False)
        raise
