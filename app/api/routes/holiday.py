from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core.security import require_roles
from ...db.session import get_db
from ...models.attendance import Holiday

router = APIRouter()


@router.get("/")
def list_holidays(db: Session = Depends(get_db)):
    return db.query(Holiday).order_by(Holiday.date).all()


@router.post("/")
def create_holiday(
    holiday_date: date,
    name: str,
    db: Session = Depends(get_db),
    admin=Depends(require_roles(["admin", "hr"])),
):
    if db.query(Holiday).filter(Holiday.date == holiday_date).first():
        raise HTTPException(400, "Holiday already exists")
    h = Holiday(date=holiday_date, name=name)
    db.add(h)
    db.commit()
    return h
