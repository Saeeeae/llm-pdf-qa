"""Multi-scheme password verification with auto-upgrade to argon2."""
import hashlib
import re
from typing import Optional

from passlib.context import CryptContext

# argon2 is the upgrade target. bcrypt / sha256_crypt / pbkdf2_sha256 cover
# common imports. Raw SHA1 hex (in-house USER_INFO.LOGIN_PWD format) is
# handled below — passlib's hex_sha1 handler exists but its hash format is
# inconsistent with the bare 40-char hex we get from the source DB, so we
# match it ourselves with hashlib.
pwd_ctx = CryptContext(
    schemes=["argon2", "bcrypt", "sha256_crypt", "pbkdf2_sha256"],
    default="argon2",
    deprecated="auto",
)

_SHA1_HEX_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _is_sha1_hex(hashed: str) -> bool:
    return bool(hashed) and bool(_SHA1_HEX_RE.match(hashed))


def _verify_sha1_hex(plain: str, hashed: str) -> bool:
    return hashlib.sha1(plain.encode("utf-8")).hexdigest().lower() == hashed.lower()


def hash_password(plain: str) -> str:
    """Hash a plaintext password with the default scheme (argon2)."""
    return pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> tuple[bool, Optional[str]]:
    """Verify plain against hashed. Returns (ok, new_hash_if_upgraded_else_None).

    Legacy SHA1-hex hashes (in-house LOGIN_PWD) are matched directly; on
    success an argon2 hash is returned so the caller can persist the upgrade.
    Other (modern) schemes go through passlib's verify_and_update.
    """
    if not hashed:
        return False, None

    if _is_sha1_hex(hashed):
        if _verify_sha1_hex(plain, hashed):
            return True, pwd_ctx.hash(plain)
        return False, None

    try:
        ok, new_hash = pwd_ctx.verify_and_update(plain, hashed)
        return ok, new_hash  # new_hash is None when no upgrade needed
    except Exception:
        return False, None
