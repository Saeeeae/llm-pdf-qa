"""Multi-scheme password verification with auto-upgrade to argon2."""
from typing import Optional

from passlib.context import CryptContext

# Schemes ordered by preference; argon2 is the upgrade target.
# bcrypt and sha256_crypt handle legacy hashes imported from external MySQL.
pwd_ctx = CryptContext(
    schemes=["argon2", "bcrypt", "sha256_crypt", "pbkdf2_sha256"],
    default="argon2",
    deprecated="auto",
)


def verify_password(plain: str, hashed: str) -> tuple[bool, Optional[str]]:
    """Verify plain against hashed. Returns (ok, new_hash_if_upgraded_else_None).

    If the hash uses a legacy scheme, returns a fresh argon2 hash so the
    caller can persist the upgrade.
    """
    try:
        ok, new_hash = pwd_ctx.verify_and_update(plain, hashed)
        return ok, new_hash  # new_hash is None when no upgrade needed
    except Exception:
        return False, None
