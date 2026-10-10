from fastapi import Request
from sqlalchemy.orm import Session

from ..models.attendance import AuditLog


def log_audit(
    db: Session,
    actor_id: int,
    action: str,
    entity: str,
    entity_id: int = None,
    target_employee_id: int = None,
    details: dict = None,
    request: Request = None,
):
    ip = request.client.host if request else None
    ua = request.headers.get("user-agent") if request else None
    log = AuditLog(
        employee_id=actor_id,
        target_employee_id=target_employee_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        details=details,
        ip=ip,
        user_agent=ua,
    )
    db.add(log)
    db.commit()
    return log
