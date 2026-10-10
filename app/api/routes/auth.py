import traceback
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.security import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from ...db.session import get_db
from ...models.employee import Employee
from ...schemas.employee import EmployeeCreate, EmployeeOut, LoginRequest

router = APIRouter()


@router.post("/register")
def register(payload: EmployeeCreate, request: Request, db: Session = Depends(get_db), admin=Depends(require_admin)):
    try:
        print(f"[REGISTER] Attempt: {payload.email}, role={payload.role}, by admin={admin.email if admin else 'None'}")

        if settings.SSO_ENFORCE and not payload.emp_code.startswith("SSO"):
            raise HTTPException(400, "SSO enforced - manual registration disabled")

        existing = (
            db.query(Employee)
            .filter((Employee.email == payload.email) | (Employee.emp_code == payload.emp_code))
            .first()
        )
        if existing:
            raise HTTPException(400, f"Employee exists: {existing.email} / {existing.emp_code}")

        if payload.manager_id:
            mgr = db.query(Employee).filter(Employee.id == payload.manager_id).first()
            if not mgr:
                raise HTTPException(
                    400,
                    f"Manager id {payload.manager_id} not found. Existing ids: {[e.id for e in db.query(Employee).all()]}",
                )

        role_str = payload.role.value if hasattr(payload.role, "value") else str(payload.role)
        print(f"[REGISTER] Creating with role={role_str}")

        emp = Employee(
            emp_code=payload.emp_code,
            name=payload.name,
            email=payload.email,
            password_hash=hash_password(payload.password) if payload.password else None,
            role=role_str,
            department=payload.department,
            manager_id=payload.manager_id,
        )
        db.add(emp)
        db.commit()
        db.refresh(emp)
        print(f"[REGISTER] Success id={emp.id}")

        return {"message": "Employee created", "employee": EmployeeOut.model_validate(emp)}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[REGISTER] ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(500, f"Internal error: {str(e)} - {traceback.format_exc()[:500]}")


@router.post("/register-first-admin")
def register_first_admin(payload: EmployeeCreate, request: Request, db: Session = Depends(get_db)):
    try:
        count = db.query(Employee).count()
        print(f"[FIRST ADMIN] Count={count}, trying {payload.email}")
        if count > 0:
            raise HTTPException(400, f"First admin exists ({count} users). Delete attendance.db to reset.")

        existing = (
            db.query(Employee)
            .filter((Employee.email == payload.email) | (Employee.emp_code == payload.emp_code))
            .first()
        )
        if existing:
            raise HTTPException(400, "Employee exists")

        print(f"[FIRST ADMIN] Creating {payload.email}")
        emp = Employee(
            emp_code=payload.emp_code,
            name=payload.name,
            email=payload.email,
            password_hash=hash_password(payload.password) if payload.password else hash_password("admin123"),
            role="admin",
            department=payload.department,
            manager_id=None,
        )
        db.add(emp)
        db.commit()
        db.refresh(emp)
        print(f"[FIRST ADMIN] Success id={emp.id}")
        return {"message": "First admin created! Now login", "employee": EmployeeOut.model_validate(emp)}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[FIRST ADMIN] ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(500, f"Internal error: {str(e)}")


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    try:
        print(f"[LOGIN] Attempt {payload.email}")
        user = db.query(Employee).filter(Employee.email == payload.email).first()
        if not user:
            print(f"[LOGIN] User not found {payload.email}")
            raise HTTPException(401, "Invalid credentials - user not found")
        if not user.password_hash:
            print(f"[LOGIN] No password hash for {payload.email}")
            raise HTTPException(401, "Invalid credentials - no password set (SSO user?)")
        if not verify_password(payload.password, user.password_hash):
            print(f"[LOGIN] Password mismatch for {payload.email}")
            raise HTTPException(401, "Invalid credentials - wrong password")
        if not user.is_active:
            raise HTTPException(403, "Account disabled")

        user.last_login = datetime.utcnow()
        if getattr(payload, "device_fingerprint", None):
            user.device_fingerprint = payload.device_fingerprint
        db.commit()

        token = create_access_token({"sub": user.email, "role": user.role, "emp_id": user.id})
        refresh = create_refresh_token({"sub": user.email})
        print(f"[LOGIN] Success {payload.email}")
        return {
            "access_token": token,
            "refresh_token": refresh,
            "token_type": "bearer",
            "user": EmployeeOut.model_validate(user),
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[LOGIN] ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(500, f"Login error: {str(e)}")


@router.get("/oidc/login")
def oidc_login():
    if not settings.OIDC_ENABLED:
        raise HTTPException(400, "OIDC disabled")
    url = f"{settings.OIDC_ISSUER}/authorize?client_id={settings.OIDC_CLIENT_ID}&redirect_uri={settings.OIDC_REDIRECT_URI}&scope={settings.OIDC_SCOPES}&response_type=code"
    return {"auth_url": url}


@router.post("/oidc/callback")
def oidc_callback(code: str, request: Request, db: Session = Depends(get_db)):
    try:
        email = code
        user = db.query(Employee).filter(Employee.email == email).first()
        if not user:
            user = Employee(
                emp_code=f"SSO-{email.split('@')[0]}",
                name=email.split("@")[0],
                email=email,
                role="employee",
                oidc_sub=email,
                sso_provider="mock",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        user.last_login = datetime.utcnow()
        db.commit()
        token = create_access_token({"sub": user.email, "role": user.role, "oidc": True})
        return {"access_token": token, "token_type": "bearer", "user": EmployeeOut.model_validate(user)}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(400, f"OIDC failed: {e}")


@router.get("/me", response_model=EmployeeOut)
def me(user=Depends(get_current_user)):
    return user


@router.get("/debug/count")
def debug_count(db: Session = Depends(get_db)):
    count = db.query(Employee).count()
    users = db.query(Employee).all()
    return {
        "count": count,
        "users": [{"id": u.id, "email": u.email, "role": u.role, "emp_code": u.emp_code} for u in users],
    }
