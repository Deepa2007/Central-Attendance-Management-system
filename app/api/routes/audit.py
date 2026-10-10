from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.security import require_roles
from ...db.session import get_db
from ...models.attendance import AuditLog

router = APIRouter()


@router.get("/")
def list_audit(limit: int = 100, db: Session = Depends(get_db), admin=Depends(require_roles(["admin", "hr"]))):
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
