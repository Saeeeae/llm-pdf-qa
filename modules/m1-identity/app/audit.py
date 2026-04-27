from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from .models import AuditLog


async def log_event(
    db: AsyncSession,
    user_id: Optional[int],
    action: str,
    resource: Optional[str] = None,
    metadata: Optional[dict] = None,
    ip: Optional[str] = None,
) -> None:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        meta=metadata,
        ip=ip,
    )
    db.add(entry)
    await db.commit()
