from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ...core.security import get_current_user, require_roles
from ...db.session import get_db
from ...models.attendance import Leave
from ...schemas.attendance import LeaveCreate, LeaveOut
from ...services.audit_service import log_audit

router = APIRouter()

LEAVE_POLICY = {
    "casual": {"waives_day": True, "waives_hours": False, "hours": 0},
    "sick": {"waives_day": True, "waives_hours": True, "hours": 8},
    "earned": {"waives_day": True, "waives_hours": True, "hours": 8},
    "wfh": {"waives_day": True, "waives_hours": False, "hours": 0},
    "bereavement": {"waives_day": True, "waives_hours": True, "hours": 8},
}


@router.post("/", response_model=LeaveOut)
def create_leave(
    payload: LeaveCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    request: Request = None,
):
    policy = LEAVE_POLICY.get(payload.type, LEAVE_POLICY["casual"])
    leave = Leave(
        employee_id=user.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        type=payload.type,
        reason=payload.reason,
        waives_day=policy["waives_day"],
        waives_hours=policy["waives_hours"],
        hours_credited=(
            policy["hours"] * ((payload.end_date - payload.start_date).days + 1) if policy["waives_hours"] else 0
        ),
    )
    db.add(leave)
    db.commit()
    db.refresh(leave)
    log_audit(
        db,
        user.id,
        "request_leave",
        "leave",
        leave.id,
        user.id,
        {"type": payload.type, "dates": f"{payload.start_date} to {payload.end_date}"},
        request,
    )
    return leave


@router.get("/", response_model=list[LeaveOut])
def list_leaves(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role in ["admin", "hr", "manager"]:
        return db.query(Leave).order_by(Leave.created_at.desc()).limit(100).all()
    return db.query(Leave).filter(Leave.employee_id == user.id).all()


@router.post("/{leave_id}/approve")
def approve_leave(
    leave_id: int,
    db: Session = Depends(get_db),
    hr=Depends(require_roles(["hr", "admin", "manager"])),
    request: Request = None,
):
    leave = db.query(Leave).filter(Leave.id == leave_id).first()
    if not leave:
        raise HTTPException(404, "Leave not found")
    leave.status = "approved"
    leave.approved_by = hr.id
    db.commit()
    log_audit(
        db,
        hr.id,
        "approve_leave",
        "leave",
        leave.id,
        leave.employee_id,
        {"waives_day": leave.waives_day, "waives_hours": leave.waives_hours},
        request,
    )
    return {"message": "Approved", "leave": LeaveOut.model_validate(leave)}


@router.post("/{leave_id}/reject")
def reject_leave(
    leave_id: int,
    db: Session = Depends(get_db),
    hr=Depends(require_roles(["hr", "admin", "manager"])),
    request: Request = None,
):
    leave = db.query(Leave).filter(Leave.id == leave_id).first()
    if not leave:
        raise HTTPException(404, "Leave not found")
    leave.status = "rejected"
    leave.approved_by = hr.id
    db.commit()
    log_audit(db, hr.id, "reject_leave", "leave", leave.id, leave.employee_id, {}, request)
    return {"message": "Rejected"}
