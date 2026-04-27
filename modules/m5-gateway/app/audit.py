import hashlib
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger("m5-gateway.audit")


def hash_value(value: str) -> str:
    salt = os.getenv("M5_AUDIT_HASH_SALT", "m5-gateway")
    return hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()


def log_audit(action: str, user: Optional[dict[str, Any]] = None, **fields: Any) -> None:
    payload = {
        "action": action,
        "user_id": (user or {}).get("sub"),
        **fields,
    }
    logger.info(json.dumps(payload, ensure_ascii=False, sort_keys=True))
