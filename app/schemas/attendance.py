from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel


class AttendanceMark(BaseModel):
    employee_id: Optional[int] = None
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    device_fingerprint: Optional[str] = None


class AttendanceOut(BaseModel):
    id: int
    employee_id: int
    date: date
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    hours_worked: float
    is_present: bool
    is_stale: bool = False
    location: Optional[Any] = None
    ip_address: Optional[str] = None
    correction_status: str = "none"

    class Config:
        from_attributes = True


class ReportRequest(BaseModel):
    type: str
    send_email: bool = False
    employee_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    department: Optional[str] = None


class LeaveCreate(BaseModel):
    start_date: date
    end_date: date
    type: str = "casual"
    reason: str


class LeaveOut(BaseModel):
    id: int
    employee_id: int
    start_date: date
    end_date: date
    type: str
    status: str
    waives_day: bool
    waives_hours: bool
    hours_credited: float

    class Config:
        from_attributes = True


class CorrectionCreate(BaseModel):
    attendance_id: int
    requested_entry: Optional[datetime] = None
    requested_exit: Optional[datetime] = None
    reason: str


class CorrectionOut(BaseModel):
    id: int
    attendance_id: int
    employee_id: int
    status: str
    reason: str

    class Config:
        from_attributes = True
