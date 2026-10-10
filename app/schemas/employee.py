from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr


class RoleEnum(str, Enum):
    employee = "employee"
    manager = "manager"
    hr = "hr"
    admin = "admin"


class EmployeeCreate(BaseModel):
    emp_code: str
    name: str
    email: EmailStr
    password: Optional[str] = None
    role: RoleEnum = RoleEnum.employee
    department: str = "General"
    manager_id: Optional[int] = None


class EmployeeOut(BaseModel):
    id: int
    emp_code: str
    name: str
    email: str
    role: str
    department: str
    is_active: bool

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_fingerprint: Optional[str] = None


class OIDCLoginRequest(BaseModel):
    code: str
    state: Optional[str] = None
