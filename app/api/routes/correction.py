from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ...core.security import get_current_user, require_roles
from ...db.session import get_db
from ...models.attendance import Attendance, AttendanceCorrection
from ...schemas.attendance import CorrectionCreate, CorrectionOut
from ...services.audit_service import log_audit

router = APIRouter()


@router.post("/", response_model=CorrectionOut)
def request_correction(
    payload: CorrectionCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    request: Request = None,
):
    att = db.query(Attendance).filter(Attendance.id == payload.attendance_id, Attendance.employee_id == user.id).first()
    if not att:
        raise HTTPException(404, "Attendance not found")
    if att.correction_status == "pending":
        raise HTTPException(400, "Correction already pending")
    corr = AttendanceCorrection(
        attendance_id=att.id,
        employee_id=user.id,
        requested_entry=payload.requested_entry,
        requested_exit=payload.requested_exit,
        reason=payload.reason,
    )
    att.correction_status = "pending"
    db.add(corr)
    db.commit()
    db.refresh(corr)
    log_audit(
        db,
        user.id,
        "request_correction",
        "correction",
        corr.id,
        user.id,
        {"attendance_id": att.id, "reason": payload.reason},
        request,
    )
    return corr


@router.get("/", response_model=list[CorrectionOut])
def list_corrections(db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role in ["admin", "hr", "manager"]:
        return db.query(AttendanceCorrection).filter(AttendanceCorrection.status == "pending").all()
    return db.query(AttendanceCorrection).filter(AttendanceCorrection.employee_id == user.id).all()


@router.post("/{corr_id}/approve")
def approve_correction(
    corr_id: int,
    db: Session = Depends(get_db),
    manager=Depends(require_roles(["manager", "hr", "admin"])),
    request: Request = None,
):
    corr = db.query(AttendanceCorrection).filter(AttendanceCorrection.id == corr_id).first()
    if not corr:
        raise HTTPException(404, "Not found")
    att = db.query(Attendance).filter(Attendance.id == corr.attendance_id).first()
    if corr.requested_entry:
        att.entry_time = corr.requested_entry
    if corr.requested_exit:
        att.exit_time = corr.requested_exit
    if att.entry_time and att.exit_time:
        delta = (att.exit_time.replace(tzinfo=None) - att.entry_time.replace(tzinfo=None)).total_seconds() / 3600
        att.hours_worked = max(0, round(delta, 2))
        att.is_present = att.hours_worked >= 0.5
        att.is_stale = False
    att.correction_status = "approved"
    corr.status = "approved"
    corr.reviewed_by = manager.id
    corr.reviewed_at = datetime.utcnow()
    db.commit()
    log_audit(db, manager.id, "approve_correction", "correction", corr.id, corr.employee_id, {}, request)
    return {"message": "Approved"}


@router.post("/{corr_id}/reject")
def reject_correction(
    corr_id: int,
    db: Session = Depends(get_db),
    manager=Depends(require_roles(["manager", "hr", "admin"])),
    request: Request = None,
):
    corr = db.query(AttendanceCorrection).filter(AttendanceCorrection.id == corr_id).first()
    if not corr:
        raise HTTPException(404, "Not found")
    att = db.query(Attendance).filter(Attendance.id == corr.attendance_id).first()
    att.correction_status = "rejected"
    corr.status = "rejected"
    corr.reviewed_by = manager.id
    corr.reviewed_at = datetime.utcnow()
    db.commit()
    log_audit(db, manager.id, "reject_correction", "correction", corr.id, corr.employee_id, {}, request)
    return {"message": "Rejected"}
