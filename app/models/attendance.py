import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from ..db.base import Base


class Attendance(Base):
    __tablename__ = "attendances"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    date = Column(Date, index=True, nullable=False)
    entry_time = Column(DateTime, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    hours_worked = Column(Float, default=0.0)
    is_present = Column(Boolean, default=False)
    is_stale = Column(Boolean, default=False)
    stale_flagged_at = Column(DateTime, nullable=True)
    is_half_day = Column(Boolean, default=False)
    source = Column(String, default="manual")
    ip_address = Column(String, nullable=True)
    location = Column(JSON, nullable=True)
    device_info = Column(String, nullable=True)
    correction_status = Column(String, default="none")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_employee_date"),
        Index("ix_attendance_emp_date", "employee_id", "date"),
    )


class Holiday(Base):
    __tablename__ = "holidays"
    id = Column(Integer, primary_key=True)
    date = Column(Date, unique=True, nullable=False)
    name = Column(String, nullable=False)
    is_recurring = Column(Boolean, default=False)


class Leave(Base):
    __tablename__ = "leaves"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    type = Column(String, default="casual")
    reason = Column(String)
    status = Column(String, default="pending")
    approved_by = Column(Integer, nullable=True)
    waives_day = Column(Boolean, default=False)
    waives_hours = Column(Boolean, default=False)
    hours_credited = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class WFHRequest(Base):
    __tablename__ = "wfh_requests"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    date = Column(Date, nullable=False)
    reason = Column(String)
    status = Column(String, default="pending")
    waives_day = Column(Boolean, default=True)
    waives_hours = Column(Boolean, default=False)
    hours_credited = Column(Float, default=0.0)


class AttendanceCorrection(Base):
    __tablename__ = "attendance_corrections"
    id = Column(Integer, primary_key=True)
    attendance_id = Column(Integer, ForeignKey("attendances.id"), index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    requested_entry = Column(DateTime, nullable=True)
    requested_exit = Column(DateTime, nullable=True)
    reason = Column(String, nullable=False)
    status = Column(String, default="pending")
    reviewed_by = Column(Integer, ForeignKey("employees.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, nullable=True)
    target_employee_id = Column(Integer, nullable=True)
    action = Column(String, nullable=False)
    entity = Column(String)
    entity_id = Column(Integer, nullable=True)
    details = Column(JSON)
    ip = Column(String)
    user_agent = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)
    title = Column(String)
    message = Column(String)
    type = Column(String, default="info")
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
