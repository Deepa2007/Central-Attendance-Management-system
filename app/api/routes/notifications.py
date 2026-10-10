from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core.security import get_current_user, require_roles
from ...db.session import get_db
from ...models.attendance import Notification
from ...services.email_service import send_email
from ...services.notification_service import (
    daily_reminder_job,
    stale_session_job,
    violation_check_job,
)

router = APIRouter()


@router.get("/")
def list_notifications(
    limit: int = 50,
    unread_only: bool = False,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    query = db.query(Notification).filter(Notification.employee_id == user.id).order_by(Notification.created_at.desc())
    if unread_only:
        query = query.filter(Notification.is_read == False)  # noqa: E712
    return query.limit(limit).all()


@router.post("/read/{notif_id}")
def mark_read(notif_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    notif = db.query(Notification).filter(Notification.id == notif_id, Notification.employee_id == user.id).first()
    if not notif:
        raise HTTPException(404, "Notification not found")
    notif.is_read = True
    db.commit()
    return {"message": "Marked as read"}


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), user=Depends(get_current_user)):
    db.query(Notification).filter(
        Notification.employee_id == user.id, Notification.is_read == False  # noqa: E712
    ).update({"is_read": True})
    db.commit()
    return {"message": "All marked as read"}


@router.post("/test-email")
def test_email(to: str = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    target = to or user.email
    result = send_email(
        target,
        "Test Email - Attendance System",
        body_text=f"Hi {user.name},\n\nThis is a test email from Central Attendance System.\n\n"
        f"If you received this, SMTP is configured correctly!\n\n{user.email}",
    )
    return result


@router.post("/trigger/daily-reminder")
def trigger_daily_reminder(db: Session = Depends(get_db), admin=Depends(require_roles(["admin"]))):
    count = daily_reminder_job(db)
    return {"message": f"Daily reminder triggered, {count} reminders sent", "count": count}


@router.post("/trigger/violation-check")
def trigger_violation_check(db: Session = Depends(get_db), admin=Depends(require_roles(["admin"]))):
    count = violation_check_job(db)
    return {"message": f"Violation check triggered, {count} violations", "count": count}


@router.post("/trigger/stale-check")
def trigger_stale_check(db: Session = Depends(get_db), admin=Depends(require_roles(["admin"]))):
    count = stale_session_job(db)
    return {"message": f"Stale check triggered, {count} flagged", "count": count}


@router.get("/stats")
def notification_stats(db: Session = Depends(get_db), user=Depends(get_current_user)):
    total = db.query(Notification).filter(Notification.employee_id == user.id).count()
    unread = (
        db.query(Notification)
        .filter(Notification.employee_id == user.id, Notification.is_read == False)  # noqa: E712
        .count()
    )
    by_type = {}
    for t in ["info", "reminder", "violation", "stale", "approval", "checkin", "checkout"]:
        by_type[t] = db.query(Notification).filter(Notification.employee_id == user.id, Notification.type == t).count()
    return {"total": total, "unread": unread, "by_type": by_type}
