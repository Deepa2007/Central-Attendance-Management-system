from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def placeholder():
    return {"message": "Attendance routes - use main.py endpoints for now"}
