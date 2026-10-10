from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..core.config import get_db_url

url = get_db_url()
connect_args = {"check_same_thread": False} if "sqlite" in url else {}
if "postgres" in url or "postgresql" in url:
    engine = create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)
else:
    engine = create_engine(url, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
