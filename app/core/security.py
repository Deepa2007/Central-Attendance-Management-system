import traceback
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.session import get_db
from ..models.employee import Employee

pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
security = HTTPBearer()


def hash_password(p: str):
    return pwd_context.hash(p)


def verify_password(p: str, h: str):
    try:
        return pwd_context.verify(p, h)
    except Exception as e:
        print(f"[VERIFY PASSWORD ERROR] {e}")
        return False


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iss": settings.COMPANY_NAME})
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    print(f"[TOKEN CREATED] sub={data.get('sub')} role={data.get('role')} exp={expire}")
    return token


def create_refresh_token(data: dict):
    return create_access_token(data, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db), request: Request = None
):
    token = creds.credentials
    print(f"[AUTH] Token received: {token[:20]}... (length {len(token)})")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        print(f"[AUTH] Payload decoded: {payload}")
        email = payload.get("sub")
        if not email:
            print(f"[AUTH] No sub in payload: {payload}")
            raise HTTPException(401, "Invalid token - no email in token")
    except JWTError as e:
        print(f"[AUTH] JWTError: {e}")
        traceback.print_exc()
        print(f"[AUTH] SECRET_KEY used: {settings.SECRET_KEY[:10]}... ALGORITHM: {settings.ALGORITHM}")
        raise HTTPException(
            401,
            f"Invalid token - JWT error: {str(e)}. Try login again to get fresh token. If SECRET_KEY changed in .env, delete attendance.db and recreate admin.",
        )
    except Exception as e:
        print(f"[AUTH] Unexpected error: {e}")
        traceback.print_exc()
        raise HTTPException(401, f"Invalid token - {str(e)}")

    user = db.query(Employee).filter(Employee.email == email, Employee.is_active == True).first()
    if not user:
        print(f"[AUTH] User not found or inactive: {email}")
        # Debug: list all users
        all_users = db.query(Employee).all()
        print(f"[AUTH] All users in DB: {[(u.email, u.is_active) for u in all_users]}")
        raise HTTPException(
            401,
            f"User not found or inactive: {email}. Did you delete attendance.db? Please register-first-admin and login again.",
        )

    # Device fingerprint check ONLY if SSO_ENFORCE and fingerprint was previously set and request provides fingerprint
    # Don't fail if no fingerprint in request - just log
    if request and settings.SSO_ENFORCE:
        fp = request.headers.get("X-Device-Fingerprint")
        print(f"[AUTH] SSO_ENFORCE enabled, checking fingerprint: stored={user.device_fingerprint}, request={fp}")
        if user.device_fingerprint and fp and user.device_fingerprint != fp:
            print("[AUTH] Device mismatch!")
            raise HTTPException(401, "Device mismatch - SSO violation")

    print(f"[AUTH] Success: {user.email} role={user.role}")
    return user


def require_roles(allowed: list):
    def checker(user=Depends(get_current_user)):
        if user.role not in allowed:
            print(f"[RBAC] Denied: user role {user.role} not in {allowed}")
            raise HTTPException(403, f"Requires one of {allowed}, got {user.role}")
        print(f"[RBAC] Allowed: {user.role} in {allowed}")
        return user

    return checker


require_admin = require_roles(["admin"])
require_manager = require_roles(["manager", "admin"])
require_hr = require_roles(["hr", "admin"])
require_hr_manager = require_roles(["hr", "manager", "admin"])


def verify_oidc_token(id_token: str):
    try:
        payload = jwt.decode(id_token, options={"verify_signature": False})
        return payload
    except Exception:
        raise HTTPException(401, "Invalid OIDC token")
