from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# FIX: Explicitly find .env file in project root
env_path = Path(__file__).parent.parent.parent / ".env"
print(f"[CONFIG] Looking for .env at: {env_path} exists={env_path.exists()}")
if env_path.exists():
    print(f"[CONFIG] .env found, size={env_path.stat().st_size} bytes")
    with open(env_path, "r") as f:
        lines = f.readlines()
        for line in lines[:10]:
            if "PASS" not in line and "SECRET" not in line:
                print(f"[CONFIG] .env line: {line.strip()}")
else:
    print(f"[CONFIG] .env NOT found at {env_path}, checking current dir .env")
    alt_path = Path(".env")
    print(f"[CONFIG] Alt .env at {alt_path.absolute()} exists={alt_path.exists()}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", env_file=".env", env_file_encoding="utf-8", env_file_verbosity="verbose"
    )
    DATABASE_URL: str = "postgresql+psycopg2://attendance:attendance@localhost:5432/attendance_db"
    DATABASE_URL_DEV: str = "sqlite:///./attendance.db"
    USE_POSTGRES: bool = False
    SECRET_KEY: str = "super-secret-change-me-prod-use-env"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    OIDC_ENABLED: bool = False
    OIDC_ISSUER: str = "https://auth.company.com"
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_REDIRECT_URI: str = "http://localhost:8000/api/auth/oidc/callback"
    OIDC_SCOPES: str = "openid email profile"
    SSO_ENFORCE: bool = False
    ROLES: List[str] = ["employee", "manager", "hr", "admin"]
    COMPANY_NAME: str = "YourCompany"
    OFFICE_TIMEZONE: str = "Asia/Kolkata"
    OFFICE_LAT: float = 17.3850
    OFFICE_LNG: float = 78.4867
    GEOFENCE_RADIUS_KM: float = 0.2
    REQUIRED_DAYS: int = 3
    REQUIRED_HOURS: float = 15.0
    MIN_DAILY_HOURS: float = 5.0  # NEW: Minimum hours per day to avoid early checkout warning
    STALE_SESSION_HOURS: int = 12
    MAX_OPEN_SESSIONS: int = 1
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str = ""
    ENABLE_SCHEDULER: bool = True
    RETENTION_DAYS_ATTENDANCE: int = 2555
    RETENTION_DAYS_AUDIT: int = 2555


settings = Settings()

print(
    f"[CONFIG LOADED] SMTP_HOST={settings.SMTP_HOST or 'EMPTY'} SMTP_USER={settings.SMTP_USER or 'EMPTY'} SMTP_FROM={settings.SMTP_FROM or 'EMPTY'} PASS_SET={bool(settings.SMTP_PASS)} COMPANY={settings.COMPANY_NAME}"
)

# FIX v3: For Gmail, FORCE FROM=USER ALWAYS - your bug was USER=deepaeswar@gmail.com FROM=deepaeswar414@gmail.com -> Connection closed
# Gmail SMTP does NOT allow sending FROM different account than authenticated USER
if settings.SMTP_USER and "@gmail.com" in settings.SMTP_USER.lower():
    if settings.SMTP_FROM and settings.SMTP_FROM.lower() != settings.SMTP_USER.lower():
        print(
            f"[CONFIG FIX v3] Gmail mismatch: USER={settings.SMTP_USER} != FROM={settings.SMTP_FROM} -> FORCING FROM=USER to fix Connection closed error"
        )
        print(
            "[CONFIG FIX v3] Your .env has USER=deepaeswar@gmail.com but FROM=deepaeswar414@gmail.com. Gmail blocks this. Forcing FROM=USER."
        )
        settings.SMTP_FROM = settings.SMTP_USER
    elif not settings.SMTP_FROM:
        settings.SMTP_FROM = settings.SMTP_USER
        print(f"[CONFIG] Set SMTP_FROM={settings.SMTP_FROM} from USER for Gmail")
    else:
        print(f"[CONFIG] Gmail USER and FROM match: {settings.SMTP_USER} - OK")
elif not settings.SMTP_FROM and settings.SMTP_USER:
    settings.SMTP_FROM = settings.SMTP_USER
    print(f"[CONFIG] Set SMTP_FROM={settings.SMTP_FROM} from USER")


def get_db_url():
    return settings.DATABASE_URL if settings.USE_POSTGRES else settings.DATABASE_URL_DEV
