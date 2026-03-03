"""VLM (Vision Language Model) client for image description generation.

Sends images to an OpenAI-compatible vLLM server and returns text descriptions.
"""

import base64
import logging
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

VLM_PROMPT = (
    "이 이미지의 내용을 상세히 설명해주세요. "
    "표가 있다면 데이터를 정확히 추출해주세요."
)

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}


def describe_image(image_path: str, prompt: str = VLM_PROMPT) -> str | None:
    """Send an image to the VLM server and return its text description.

    Returns None if the VLM call fails or is disabled.
    """
    if not settings.enable_image_embedding:
        return None

    path = Path(image_path)
    if not path.exists():
        logger.warning("Image file not found: %s", image_path)
        return None

    image_data = base64.b64encode(path.read_bytes()).decode("utf-8")
    media_type = _MEDIA_TYPES.get(path.suffix.lower(), "image/png")

    payload = {
        "model": settings.vlm_model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_data}",
                        },
                    },
                ],
            }
        ],
        "max_tokens": 1024,
    }

    try:
        response = httpx.post(
            f"{settings.vlm_api_url}/chat/completions",
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("VLM description failed for %s: %s", image_path, e)
        return None


def describe_images_batch(image_paths: list[str]) -> list[str | None]:
    """Describe multiple images sequentially.

    Returns list of descriptions (None for failures).
    """
    return [describe_image(p) for p in image_paths]
