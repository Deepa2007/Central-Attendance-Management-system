from datetime import date, datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .auth import (
    create_access_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from .database import Base, SessionLocal, engine, get_db
from .email_service import daily_summary_email, non_compliance_email

IST = pytz.timezone("Asia/Kolkata")
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Central Attendance Management System - Enterprise",
    description="Real-time, policy-enforced attendance backend with 3days/15hrs rule, compliance, and single-report API",
    version="2.0.0",
)


# ---------- Auth ----------
@app.post("/api/auth/register", tags=["Auth"])
def register(payload: schemas.EmployeeCreate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    if (
        db.query(models.Employee)
        .filter((models.Employee.email == payload.email) | (models.Employee.emp_code == payload.emp_code))
        .first()
    ):
        raise HTTPException(400, "Employee already exists")
    emp = models.Employee(
        emp_code=payload.emp_code,
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role.value,
        department=payload.department,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return {"message": "Employee created", "employee": schemas.EmployeeOut.from_orm(emp)}


@app.post("/api/auth/login", tags=["Auth"])
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.Employee).filter(models.Employee.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    token = create_access_token({"sub": user.email, "role": user.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": schemas.EmployeeOut.from_orm(user),
    }


# ---------- Attendance Mark ----------
@app.post("/api/attendance/mark", tags=["Attendance"], response_model=schemas.AttendanceOut)
def mark_attendance_api(
    payload: schemas.AttendanceMark,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    emp_id = payload.employee_id if current_user.role == "admin" and payload.employee_id else current_user.id
    entry = payload.entry_time
    exit_time = payload.exit_time
    if not entry and not exit_time:
        today = datetime.now(IST).date()
        existing = (
            db.query(models.Attendance)
            .filter(models.Attendance.employee_id == emp_id, models.Attendance.date == today)
            .first()
        )
        if not existing or not existing.entry_time:
            entry = datetime.now(IST)
        else:
            exit_time = datetime.now(IST)

    rec = crud.mark_attendance(db, emp_id, entry_time=entry, exit_time=exit_time, ip=request.client.host)

    weekly = crud.get_weekly_stats(db, emp_id, rec.date)
    deficit_hours = max(0, 15 - weekly["total_hours"])
    if rec.exit_time:
        background.add_task(daily_summary_email, current_user.name, current_user.email, rec.hours_worked, deficit_hours)

    return rec


@app.get("/api/attendance/today", tags=["Attendance"])
def today_status(db: Session = Depends(get_db), user=Depends(get_current_user)):
    today = datetime.now(IST).date()
    rec = (
        db.query(models.Attendance)
        .filter(models.Attendance.employee_id == user.id, models.Attendance.date == today)
        .first()
    )
    weekly = crud.get_weekly_stats(db, user.id, today)
    needed = max(0, 15 - weekly["total_hours"])
    if not rec or not rec.entry_time:
        return {
            "status": "not_attended",
            "message": "Marked as not attended office - no entry",
            "weekly": weekly,
            "hours_needed": needed,
        }
    present = rec.hours_worked
    return {
        "status": "present" if rec.is_present else "not_attended",
        "entry": rec.entry_time,
        "exit": rec.exit_time,
        "present_hours_today": present,
        "weekly_total": weekly["total_hours"],
        "days_present_week": weekly["days_present"],
        "hours_needed_to_achieve_weekly": needed,
        "message": f"You were present {present:.2f} hrs today. You need {needed:.2f} hrs more this week to reach 15 hrs.",
    }


# ---------- THE SINGLE REPORT API ----------
@app.post("/api/reports", tags=["Reports - Single API for Everything"])
def get_reports(
    req: schemas.ReportRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    today = date.today()
    if req.type == "daily":
        start = end = req.start_date or today
    elif req.type == "weekly":
        ref = req.start_date or today
        start, end = crud.get_week_range(ref)
    elif req.type == "monthly":
        ref = req.start_date or today
        start = ref.replace(day=1)
        if ref.month == 12:
            end = ref.replace(day=31)
        else:
            end = ref.replace(month=ref.month + 1, day=1) - timedelta(days=1)
    elif req.type == "yearly":
        ref = req.start_date or today
        start = date(ref.year, 1, 1)
        end = date(ref.year, 12, 31)
    elif req.type == "custom":
        if not req.start_date or not req.end_date:
            raise HTTPException(400, "start_date and end_date required for custom")
        start, end = req.start_date, req.end_date
    elif req.type == "compliance":
        if user.role != "admin":
            raise HTTPException(403, "Compliance report requires admin")
        employees = db.query(models.Employee).filter(models.Employee.is_active == True)  # noqa: E712
        if req.department:
            employees = employees.filter(models.Employee.department == req.department)
        employees = employees.all()
        results = []
        ref = req.start_date or today
        for emp in employees:
            weekly = crud.get_weekly_stats(db, emp.id, ref)
            is_compliant = weekly["days_present"] >= 3 and weekly["total_hours"] >= 15
            deficit_days = max(0, 3 - weekly["days_present"])
            deficit_hours = max(0, 15 - weekly["total_hours"])
            results.append(
                {
                    "employee_id": emp.id,
                    "emp_code": emp.emp_code,
                    "name": emp.name,
                    "email": emp.email,
                    "department": emp.department,
                    "days_present": weekly["days_present"],
                    "total_hours": weekly["total_hours"],
                    "required_days": 3,
                    "required_hours": 15,
                    "is_compliant": is_compliant,
                    "deficit_hours": round(deficit_hours, 2),
                    "deficit_days": deficit_days,
                    "status_message": (
                        "Compliant" if is_compliant else f"Needs {deficit_days} more days and {deficit_hours:.2f} hrs"
                    ),
                    "week_start": str(weekly["week_start"]),
                    "week_end": str(weekly["week_end"]),
                }
            )
        non_compliant = [r for r in results if not r["is_compliant"]]
        return {
            "type": "compliance",
            "week": f"{crud.get_week_range(ref)[0]} to {crud.get_week_range(ref)[1]}",
            "total_employees": len(results),
            "compliant_count": len(results) - len(non_compliant),
            "non_compliant_count": len(non_compliant),
            "non_compliant": non_compliant,
            "all": results,
        }
    elif req.type == "leaderboard":
        employees = db.query(models.Employee).filter(models.Employee.is_active == True).all()  # noqa: E712
        board = []
        for emp in employees:
            weekly = crud.get_weekly_stats(db, emp.id, today)
            board.append({"name": emp.name, "hours": weekly["total_hours"], "days": weekly["days_present"]})
        board.sort(key=lambda x: x["hours"], reverse=True)
        return {"leaderboard": board}
    else:
        raise HTTPException(400, "type must be daily, weekly, monthly, yearly, custom, compliance, leaderboard")

    query = db.query(models.Attendance).filter(models.Attendance.date >= start, models.Attendance.date <= end)
    if user.role != "admin":
        query = query.filter(models.Attendance.employee_id == user.id)
    else:
        if req.employee_id:
            query = query.filter(models.Attendance.employee_id == req.employee_id)
        if req.department:
            query = query.join(models.Employee).filter(models.Employee.department == req.department)

    records = query.order_by(models.Attendance.date.desc()).all()
    total_hours = sum([r.hours_worked for r in records])
    present_days = len([r for r in records if r.is_present])
    absent_days = (end - start).days + 1 - present_days

    return {
        "type": req.type,
        "period": f"{start} to {end}",
        "total_records": len(records),
        "total_hours": round(total_hours, 2),
        "present_days": present_days,
        "absent_days": absent_days,
        "average_hours_per_day": round(total_hours / max(1, present_days), 2),
        "records": [schemas.AttendanceOut.from_orm(r) for r in records],
    }


# ---------- Admin: Employees ----------
@app.get("/api/employees", tags=["Admin"])
def list_employees(db: Session = Depends(get_db), admin=Depends(require_admin)):
    return db.query(models.Employee).all()


@app.get("/api/employees/{emp_id}/live", tags=["Real-time"])
def live_status(emp_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin" and user.id != emp_id:
        raise HTTPException(403, "Not allowed")
    today = datetime.now(IST).date()
    rec = (
        db.query(models.Attendance)
        .filter(models.Attendance.employee_id == emp_id, models.Attendance.date == today)
        .first()
    )
    if not rec or not rec.entry_time:
        return {"in_office": False, "status": "Not checked in"}
    if rec.entry_time and not rec.exit_time:
        now = datetime.now(IST)
        entry = rec.entry_time
        if entry.tzinfo is None:
            entry = IST.localize(entry)
        hours = (now - entry).total_seconds() / 3600
        weekly = crud.get_weekly_stats(db, emp_id, today)
        needed = max(0, 15 - weekly["total_hours"])
        return {
            "in_office": True,
            "entry_time": rec.entry_time,
            "current_hours_today": round(hours, 2),
            "weekly_total": weekly["total_hours"],
            "needs_more": round(needed, 2),
            "message": f"Present {hours:.2f} hrs today. Needs {needed:.2f} hrs more this week.",
        }
    return {"in_office": False, "last_exit": rec.exit_time, "hours_today": rec.hours_worked}


# ---------- Background Compliance Job ----------
def compliance_job():
    db = SessionLocal()
    try:
        today = date.today()
        if today.weekday() >= 5:
            return
        employees = (
            db.query(models.Employee)
            .filter(models.Employee.is_active == True, models.Employee.role == "employee")  # noqa: E712
            .all()
        )
        for emp in employees:
            weekly = crud.get_weekly_stats(db, emp.id, today)
            is_compliant = weekly["days_present"] >= 3 and weekly["total_hours"] >= 15
            if not is_compliant and today.weekday() == 4:
                deficit_days = max(0, 3 - weekly["days_present"])
                deficit_hours = max(0, 15 - weekly["total_hours"])
                non_compliance_email(
                    emp.name, emp.email, weekly["days_present"], weekly["total_hours"], deficit_hours, deficit_days
                )
    finally:
        db.close()


scheduler = BackgroundScheduler()
scheduler.add_job(compliance_job, "cron", hour=18, minute=0, timezone="Asia/Kolkata")
scheduler.start()


@app.get("/", tags=["Root"])
def root():
    return {
        "app": "Central Attendance Management - Enterprise",
        "status": "running - real time",
        "features": [
            "3 days / 15 hrs policy enforcement",
            "Entry/Exit tracking, empty=absent",
            "Real-time present hours + needed hours",
            "Single report API: daily/weekly/monthly/yearly/custom/compliance/leaderboard",
            "Admin single-call compliance for 10+ people",
            "Email alerts, JWT auth, holidays, leaderboard, late detection",
        ],
        "docs": "/docs",
    }
