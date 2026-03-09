import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

from shared.db import get_session
from shared.models.orm import User, SyncLog

logger = logging.getLogger(__name__)


def sync_users_from_csv(csv_path: str) -> int:
    """Sync users from a CSV file.

    Expected CSV columns: email, usr_name, dept_id, role_id.
    Existing users (matched by email) are updated; new users are created
    with a default password that must be changed on first login.
    """
    path = Path(csv_path)
    if not path.is_file():
        logger.warning("User CSV not found: %s", csv_path)
        return 0

    added = 0

    with get_session() as session:
        sync_log = SyncLog(sync_type="user", status="running")
        session.add(sync_log)
        session.flush()
        log_id = sync_log.id

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            with get_session() as session:
                for row in reader:
                    existing = (
                        session.query(User)
                        .filter(User.email == row["email"])
                        .first()
                    )
                    if existing:
                        existing.usr_name = row.get("usr_name", existing.usr_name)
                        existing.dept_id = int(row.get("dept_id", existing.dept_id))
                        existing.role_id = int(row.get("role_id", existing.role_id))
                        existing.updated_at = datetime.now(timezone.utc)
                    else:
                        session.add(User(
                            email=row["email"],
                            usr_name=row["usr_name"],
                            pwd=_default_password_hash(),
                            dept_id=int(row["dept_id"]),
                            role_id=int(row["role_id"]),
                        ))
                        added += 1

        with get_session() as session:
            log = session.query(SyncLog).filter(SyncLog.id == log_id).first()
            if log:
                log.status = "success"
                log.finished_at = datetime.now(timezone.utc)
                log.users_added = added

        logger.info("User sync complete: %d added", added)

    except Exception as e:
        with get_session() as session:
            log = session.query(SyncLog).filter(SyncLog.id == log_id).first()
            if log:
                log.status = "failed"
                log.finished_at = datetime.now(timezone.utc)
                log.error_message = str(e)[:1000]
        logger.error("User sync failed: %s", e)
        raise

    return added


def _default_password_hash() -> str:
    """Generate a bcrypt hash for the default temporary password."""
    from passlib.context import CryptContext

    ctx = CryptContext(schemes=["bcrypt"])
    return ctx.hash("changeme123!")
