"""
Docker Secrets / environment variable helper.

Priority order:
1. Plain env var:        NAME=value
2. Secret-file env var:  NAME_FILE=/run/secrets/name  (Docker secrets pattern)
"""
import os


def from_env_or_file(name: str, required: bool = True) -> str | None:
    """Return the value of *name* from environment or from the file pointed to
    by *name*_FILE.

    Args:
        name:     Environment variable name (e.g. "JWT_SECRET").
        required: If True and the value cannot be resolved, raise RuntimeError.

    Returns:
        The secret string, or None when required=False and not set.
    """
    v = os.getenv(name)
    if v:
        return v

    f = os.getenv(f"{name}_FILE")
    if f and os.path.isfile(f):
        return open(f).read().strip()  # noqa: WPS515 (simple file read)

    if required:
        raise RuntimeError(
            f"Required secret '{name}' is not set. "
            f"Provide {name} or {name}_FILE environment variable."
        )
    return None
