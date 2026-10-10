"""
Enterprise Notification Service
- DB notifications (for frontend bell icon)
- Email notifications (SMTP)
- Scheduler jobs: daily reminder, Friday violation, stale detection
"""

from datetime import date, datetime, timedelta

import pytz
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.attendance import Attendance, Notification
from ..models.employee import Employee
from .attendance_service import flag_stale_sessions, get_week_range, get_weekly_stats
from .email_service import (
    email_template_daily_reminder,
    email_template_stale_alert,
    email_template_violation,
    email_template_weekly_violation_enhanced,
    send_email,
)

IST = pytz.timezone("Asia/Kolkata")


def send_notification(
    db: Session,
    employee_id: int,
    title: str,
    message: str,
    type: str = "info",
    send_email_flag: bool = True,
):
    """Create DB notification + optionally send email."""
    n = Notification(employee_id=employee_id, title=title, message=message, type=type)
    db.add(n)
    db.commit()
    db.refresh(n)

    if send_email_flag:
        try:
            emp = db.query(Employee).filter(Employee.id == employee_id).first()
            if emp and emp.email:
                subject = f"[{type.upper()}] {title}"
                body_text = f"{message}\n\nLogin to dashboard to view details."
                send_email(emp.email, subject, body_text=body_text)
        except Exception:  # noqa: BLE001
            print(f"Email notification failed for {employee_id}")

    print(f"[NOTIF {type}] To {employee_id}: {title}")
    return n


def daily_reminder_job(db: Session):
    """Daily 10 AM IST: Remind employees who haven't checked in today."""
    today = datetime.now(IST).date()
    print(f"[SCHEDULER] Running daily_reminder_job for {today}")
    employees = db.query(Employee).filter(Employee.is_active == True).all()  # noqa: E712
    count = 0
    for emp in employees:
        rec = db.query(Attendance).filter(Attendance.employee_id == emp.id, Attendance.date == today).first()
        if not rec or not rec.entry_time:
            send_notification(
                db,
                emp.id,
                "Check-in Reminder",
                f"Hi {emp.name}, you haven't checked in today {today}. "
                f"Required: {settings.REQUIRED_DAYS} days/{settings.REQUIRED_HOURS} hrs this week.",
                "reminder",
                send_email_flag=True,
            )
            try:
                subject, text, _ = email_template_daily_reminder(emp.name, today)
                send_email(emp.email, subject, body_text=text)
            except Exception:  # noqa: BLE001
                print(f"Daily reminder email failed for {emp.email}")
            count += 1

    print(f"[SCHEDULER] daily_reminder_job: {count} reminders sent")
    return count


def violation_check_job(db: Session):
    """Friday 6 PM IST: Check weekly compliance, notify violators."""
    today = date.today()
    if today.weekday() != 4:
        print(f"[SCHEDULER] violation_check_job: Not Friday ({today.weekday()}), skipping")
        return 0

    week_start, week_end = get_week_range(today)
    print(f"[SCHEDULER] Running violation_check_job for week {week_start} to {week_end}")
    employees = db.query(Employee).filter(Employee.is_active == True).all()  # noqa: E712
    violations = 0
    for emp in employees:
        stats = get_weekly_stats(db, emp.id, today)
        if not stats["is_compliant"]:
            send_notification(
                db,
                emp.id,
                "Weekly Compliance Violation",
                f"Week {week_start} to {week_end}: {stats['days_present']}/{stats['effective_required_days']} days, "
                f"{stats['total_hours']}/{stats['effective_required_hours']} hrs. "
                f"Deficit: {stats['effective_required_days'] - stats['days_present']} days, "
                f"{stats['effective_required_hours'] - stats['total_hours']:.1f} hrs",
                "violation",
                send_email_flag=True,
            )
            try:
                subject, text, html = email_template_weekly_violation_enhanced(emp.name, week_start, week_end, stats)
                send_email(emp.email, subject, body_text=text, body_html=html)
                print(f"[VIOLATION EMAIL] Sent enhanced violation to {emp.email}: {subject}")
            except Exception:  # noqa: BLE001
                print(f"Violation email failed for {emp.email}")
                try:
                    subject, text, _ = email_template_violation(
                        emp.name,
                        week_start,
                        week_end,
                        stats["days_present"],
                        stats["effective_required_days"],
                        stats["total_hours"],
                        stats["effective_required_hours"],
                    )
                    send_email(emp.email, subject, body_text=text)
                except Exception:  # noqa: BLE001
                    print("Fallback also failed")
            violations += 1

    print(f"[SCHEDULER] violation_check_job: {violations} violations notified")
    return violations


def stale_session_job(db: Session):
    """Every hour: Flag sessions open > STALE_SESSION_HOURS and notify."""
    print("[SCHEDULER] Running stale_session_job")
    count = flag_stale_sessions(db)
    if count:
        print(f"[SCHEDULER] Flagged {count} stale sessions")
        cutoff = datetime.now(IST) - timedelta(hours=settings.STALE_SESSION_HOURS)
        stale_recs = (
            db.query(Attendance)
            .filter(
                Attendance.is_stale == True,  # noqa: E712
                Attendance.stale_flagged_at != None,  # noqa: E711
                Attendance.entry_time >= cutoff - timedelta(hours=1),
            )
            .all()
        )

        for rec in stale_recs:
            emp = db.query(Employee).filter(Employee.id == rec.employee_id).first()
            if emp:
                hours_open = (
                    (datetime.now(IST).replace(tzinfo=None) - rec.entry_time.replace(tzinfo=None)).total_seconds()
                    / 3600
                    if rec.entry_time
                    else 0
                )
                send_notification(
                    db,
                    emp.id,
                    "Missing Check-out - Action Required",
                    f"Your session from {rec.entry_time} is still open ({hours_open:.1f}hrs). "
                    "Please check-out or request correction. This will NOT count until corrected.",
                    "stale",
                    send_email_flag=True,
                )
                try:
                    subject, text, _ = email_template_stale_alert(emp.name, rec.entry_time, hours_open)
                    send_email(emp.email, subject, body_text=text)
                except Exception:  # noqa: BLE001
                    print("Stale alert email failed")

    return count
