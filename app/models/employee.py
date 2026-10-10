import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..db.base import Base


class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    emp_code = Column(String, unique=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String, nullable=True)
    role = Column(String, default="employee")
    department = Column(String, default="General")
    manager_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    oidc_sub = Column(String, unique=True, nullable=True, index=True)
    sso_provider = Column(String, nullable=True)
    last_login = Column(DateTime, nullable=True)
    device_fingerprint = Column(String, nullable=True)
    shift_start = Column(String, default="09:30")
    shift_end = Column(String, default="18:30")
    work_mode = Column(String, default="hybrid")
    office_lat = Column(Float, nullable=True)
    office_lng = Column(Float, nullable=True)
    allowed_ips = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    manager = relationship("Employee", remote_side=[id], backref="reports")
