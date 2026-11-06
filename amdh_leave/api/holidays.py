"""Endpoints للعطل الرسمية."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..db import Database
from .main import get_db, get_current_user

router = APIRouter()


@router.get("/holidays")
def list_holidays(year: int | None = None, db: Database = Depends(get_db),
                  _user: str = Depends(get_current_user)):
    """قائمة العطل الرسمية."""
    holidays = db.list_holidays(year=year)
    return [{"id": h.id, "day": h.day.isoformat() if h.day else None,
             "name": h.name, "recurring": h.recurring} for h in holidays]


@router.post("/holidays")
def add_holiday(day: str, name: str = "", recurring: bool = False,
                db: Database = Depends(get_db), user: str = Depends(get_current_user)):
    """إضافة عطلة رسمية."""
    db.add_holiday(day, name, recurring=recurring)
    return {"status": "ok"}


@router.delete("/holidays/{holiday_id}")
def delete_holiday(holiday_id: int, db: Database = Depends(get_db),
                   user: str = Depends(get_current_user)):
    """حذف عطلة رسمية."""
    db.delete_holiday(holiday_id)
    return {"status": "ok"}
