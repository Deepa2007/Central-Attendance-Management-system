"""
Enterprise Attendance Service
FIXED: offset-naive vs aware datetime bug + weekly stats
"""

import math
from datetime import date, datetime, timedelta

import pytz
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.attendance import Attendance, Holiday, Leave, WFHRequest
from ..models.employee import Employee

IST = pytz.timezone("Asia/Kolkata")


def ensure_naive_ist(dt: datetime) -> datetime:
    """Convert any datetime (aware or naive) to naive IST for DB storage and comparison"""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        # Convert aware to IST then make naive
        return dt.astimezone(IST).replace(tzinfo=None)
    # Already naive, assume it's IST
    return dt


def distance_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def is_ip_allowed(employee: Employee, client_ip: str) -> tuple[bool, str]:
    if not employee.allowed_ips:
        return True, "No IP restriction"
    allowed = employee.allowed_ips
    if isinstance(allowed, list):
        for allowed_ip in allowed:
            if client_ip == allowed_ip or client_ip.startswith(allowed_ip):
                return True, f"IP {client_ip} matches allowed {allowed_ip}"
        return False, f"IP {client_ip} not in allowed list {allowed}"
    return True, "No IP restriction"


def verify_geofence(
    lat: float, lng: float, office_lat: float = None, office_lng: float = None, radius_km: float = None
):
    if lat is None or lng is None or lat == 0 or lng == 0:
        return False, None, office_lat, office_lng, radius_km, "No location provided"
    o_lat = office_lat if office_lat is not None else settings.OFFICE_LAT
    o_lng = office_lng if office_lng is not None else settings.OFFICE_LNG
    r_km = radius_km if radius_km is not None else settings.GEOFENCE_RADIUS_KM
    dist = distance_km(o_lat, o_lng, lat, lng)
    is_verified = dist <= r_km
    reason = f"{dist:.3f}km from office (radius {r_km}km) - {'INSIDE' if is_verified else 'OUTSIDE'}"
    return is_verified, dist, o_lat, o_lng, r_km, reason


def mark_attendance(
    db: Session,
    employee_id: int,
    entry_time: datetime = None,
    exit_time: datetime = None,
    ip: str = "",
    lat: float = None,
    lng: float = None,
    device_fingerprint: str = None,
    source: str = "manual",
    enforce_geofence: bool = False,
    enforce_ip: bool = False,
):
    now_ist = datetime.now(IST)
    now_naive = now_ist.replace(tzinfo=None)

    # FIX: Convert all incoming datetimes to naive IST for comparison
    entry_time_naive = ensure_naive_ist(entry_time)
    exit_time_naive = ensure_naive_ist(exit_time)

    target_date = (
        entry_time_naive.date()
        if entry_time_naive
        else (exit_time_naive.date() if exit_time_naive else now_naive.date())
    )

    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise ValueError(f"Employee {employee_id} not found")

    if enforce_ip and ip:
        allowed, reason = is_ip_allowed(employee, ip)
        if not allowed:
            raise ValueError(f"IP not allowed: {reason}. Your IP: {ip}, Allowed: {employee.allowed_ips}")

    if enforce_geofence and lat and lng:
        is_verified, dist, o_lat, o_lng, r_km, reason = verify_geofence(
            lat, lng, employee.office_lat, employee.office_lng
        )
        if not is_verified:
            raise ValueError(
                f"Geofence violation: {reason}. You are {dist:.2f}km away from office ({o_lat}, {o_lng}), max allowed {r_km}km."
            )

    rec = (
        db.query(Attendance)
        .filter(Attendance.employee_id == employee_id, Attendance.date == target_date)
        .with_for_update()
        .first()
    )

    if not rec:
        rec = Attendance(employee_id=employee_id, date=target_date, hours_worked=0.0, is_present=False, source=source)
        db.add(rec)
        db.flush()

    # Prevent duplicate open sessions - FIXED with naive comparison
    if entry_time_naive and rec.entry_time and not rec.exit_time:
        # Both are naive now, safe to compare
        rec_entry_naive = ensure_naive_ist(rec.entry_time)
        hours_since_entry = (now_naive - rec_entry_naive).total_seconds() / 3600 if rec_entry_naive else 0
        if hours_since_entry < 12:
            raise ValueError(
                f"Already checked in at {rec.entry_time}, checkout required first. Open session exists for {hours_since_entry:.1f} hrs."
            )

    geofence_info = None
    if lat and lng and lat != 0 and lng != 0:
        is_verified, dist, o_lat, o_lng, r_km, reason = verify_geofence(
            lat, lng, employee.office_lat, employee.office_lng
        )
        geofence_info = {
            "lat": lat,
            "lng": lng,
            "verified": is_verified,
            "distance_km": round(dist, 3),
            "office_lat": o_lat,
            "office_lng": o_lng,
            "radius_km": r_km,
            "reason": reason,
            "source": source,
        }
        rec.location = geofence_info
        print(f"[GEOFENCE] Employee {employee_id}: {reason} - Verified: {is_verified}")

    # FIXED: All comparisons with naive datetimes
    if entry_time_naive:
        if rec.exit_time:
            rec_exit_naive = ensure_naive_ist(rec.exit_time)
            if entry_time_naive < rec_exit_naive:
                print(
                    f"[ATTENDANCE] Warning: entry {entry_time_naive} before previous exit {rec_exit_naive}, allowing overwrite"
                )
        rec.entry_time = entry_time_naive
        rec.is_present = True
        rec.ip_address = ip
        rec.device_info = device_fingerprint
        rec.source = source
        if not rec.exit_time:
            rec.hours_worked = 0.0

    if exit_time_naive:
        if not rec.entry_time:
            raise ValueError(f"Cannot checkout without check-in on {target_date}. Please check-in first.")
        rec_entry_naive = ensure_naive_ist(rec.entry_time)
        # FIXED: Compare naive vs naive
        if exit_time_naive < rec_entry_naive:
            raise ValueError(f"Exit time {exit_time_naive} cannot be before entry time {rec_entry_naive}")
        rec.exit_time = exit_time_naive
        # Calculate hours - both naive
        delta = rec.exit_time - rec_entry_naive
        hours = delta.total_seconds() / 3600
        if hours < 0:
            hours = 0
        rec.hours_worked = round(hours, 2)
        rec.is_present = True

    db.commit()
    db.refresh(rec)
    print(
        f"[ATTENDANCE] Marked: emp={employee_id} date={target_date} entry={rec.entry_time} exit={rec.exit_time} hours={rec.hours_worked} geofence={geofence_info}"
    )
    return rec


def get_week_range(ref_date: date):
    start = ref_date - timedelta(days=ref_date.weekday())
    end = start + timedelta(days=6)
    return start, end


def get_approved_exceptions(db: Session, employee_id: int, week_start: date, week_end: date):
    leaves = (
        db.query(Leave)
        .filter(
            Leave.employee_id == employee_id,
            Leave.status == "approved",
            Leave.start_date <= week_end,
            Leave.end_date >= week_start,
        )
        .all()
    )
    wfhs = (
        db.query(WFHRequest)
        .filter(
            WFHRequest.employee_id == employee_id,
            WFHRequest.status == "approved",
            WFHRequest.date >= week_start,
            WFHRequest.date <= week_end,
        )
        .all()
    )
    holidays = db.query(Holiday).filter(Holiday.date >= week_start, Holiday.date <= week_end).all()
    return leaves, wfhs, holidays


def get_weekly_stats(db: Session, employee_id: int, ref_date: date):
    week_start, week_end = get_week_range(ref_date)
    records = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee_id,
            Attendance.date >= week_start,
            Attendance.date <= week_end,
            Attendance.is_present == True,
            Attendance.is_stale == False,
        )
        .all()
    )
    stale_records = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee_id,
            Attendance.date >= week_start,
            Attendance.date <= week_end,
            Attendance.is_stale == True,
        )
        .all()
    )
    leaves, wfhs, holidays = get_approved_exceptions(db, employee_id, week_start, week_end)
    waived_days = 0
    credited_hours = 0.0
    for leave in leaves:
        overlap_start = max(leave.start_date, week_start)
        overlap_end = min(leave.end_date, week_end)
        overlap_days = (overlap_end - overlap_start).days + 1 if overlap_end >= overlap_start else 0
        if leave.waives_day:
            waived_days += overlap_days
        if leave.waives_hours:
            credited_hours += leave.hours_credited or (overlap_days * 8)
    for wfh in wfhs:
        if wfh.waives_day:
            waived_days += 1
        credited_hours += wfh.hours_credited
    holiday_days = len(holidays)
    total_hours = sum([r.hours_worked for r in records]) + credited_hours
    days_present = len(records)
    effective_required_days = max(0, settings.REQUIRED_DAYS - waived_days - holiday_days)
    effective_required_hours = max(0, settings.REQUIRED_HOURS - credited_hours)
    return {
        "total_hours": round(total_hours, 2),
        "actual_hours": round(sum([r.hours_worked for r in records]), 2),
        "credited_hours": round(credited_hours, 2),
        "days_present": days_present,
        "waived_days": waived_days,
        "holiday_days": holiday_days,
        "week_start": str(week_start),
        "week_end": str(week_end),
        "is_compliant": days_present >= effective_required_days and total_hours >= effective_required_hours,
        "required_days": settings.REQUIRED_DAYS,
        "effective_required_days": effective_required_days,
        "required_hours": settings.REQUIRED_HOURS,
        "effective_required_hours": round(effective_required_hours, 2),
        "stale_sessions": len(stale_records),
        "stale_dates": [str(r.date) for r in stale_records],
        "exceptions": {"leaves": len(leaves), "wfh": len(wfhs), "holidays": len(holidays)},
        "geofence": {
            "office_lat": settings.OFFICE_LAT,
            "office_lng": settings.OFFICE_LNG,
            "radius_km": settings.GEOFENCE_RADIUS_KM,
        },
    }


def get_compliance_report(db: Session, department: str = None):
    from datetime import date as date_type

    today = date_type.today()
    query = db.query(Employee).filter(Employee.is_active == True)
    if department:
        query = query.filter(Employee.department == department)
    employees = query.all()
    result = []
    for emp in employees:
        weekly = get_weekly_stats(db, emp.id, today)
        result.append(
            {
                "employee_id": emp.id,
                "emp_code": emp.emp_code,
                "name": emp.name,
                "email": emp.email,
                "department": emp.department,
                "days_present": weekly["days_present"],
                "total_hours": weekly["total_hours"],
                "actual_hours": weekly["actual_hours"],
                "credited_hours": weekly["credited_hours"],
                "is_compliant": weekly["is_compliant"],
                "effective_required_days": weekly["effective_required_days"],
                "effective_required_hours": weekly["effective_required_hours"],
                "stale_sessions": weekly["stale_sessions"],
                "deficit_hours": max(0, weekly["effective_required_hours"] - weekly["total_hours"]),
                "deficit_days": max(0, weekly["effective_required_days"] - weekly["days_present"]),
            }
        )
    return result


def flag_stale_sessions(db: Session):
    # FIXED: Use naive comparison
    cutoff = datetime.now(IST).replace(tzinfo=None) - timedelta(hours=settings.STALE_SESSION_HOURS)
    stale = (
        db.query(Attendance)
        .filter(
            Attendance.entry_time != None,
            Attendance.exit_time == None,
            Attendance.is_stale == False,
            Attendance.entry_time < cutoff,
        )
        .all()
    )
    for rec in stale:
        rec.is_stale = True
        rec.stale_flagged_at = datetime.now(IST).replace(tzinfo=None)
    db.commit()
    return len(stale)


def get_geofence_status(db: Session, employee_id: int, lat: float, lng: float):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise ValueError("Employee not found")
    o_lat = employee.office_lat if employee.office_lat else settings.OFFICE_LAT
    o_lng = employee.office_lng if employee.office_lng else settings.OFFICE_LNG
    is_verified, dist, _, _, r_km, reason = verify_geofence(lat, lng, o_lat, o_lng)
    return {
        "employee_id": employee_id,
        "provided": {"lat": lat, "lng": lng},
        "office": {"lat": o_lat, "lng": o_lng, "radius_km": r_km},
        "distance_km": round(dist, 3),
        "is_verified": is_verified,
        "is_inside": is_verified,
        "reason": reason,
        "allowed": is_verified,
        "strict_mode_enforced": False,
    }
