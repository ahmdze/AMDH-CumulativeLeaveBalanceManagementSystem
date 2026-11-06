"""Endpoints للعطل الرسمية."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..db import Database
from ..services.security import Session
from .main import get_current_session, get_db

router = APIRouter()


@router.get("/holidays")
def list_holidays(
    year: int | None = None,
    db: Database = Depends(get_db),
    _session: Session = Depends(get_current_session),
):
    """قائمة العطل الرسمية."""
    holidays = db.list_holidays(year=year)
    return [
        {"id": h.id, "day": h.day.isoformat() if h.day else None, "name": h.name, "recurring": h.recurring}
        for h in holidays
    ]


@router.post("/holidays")
def add_holiday(
    day: str,
    name: str = "",
    recurring: bool = False,
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """إضافة عطلة رسمية."""
    if not session.can("manage_holidays"):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية إدارة العطل الرسمية")
    db.add_holiday(day, name, recurring=recurring)
    return {"status": "ok"}


@router.delete("/holidays/{holiday_id}")
def delete_holiday(
    holiday_id: int,
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """حذف عطلة رسمية."""
    if not session.can("manage_holidays"):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية إدارة العطل الرسمية")
    db.delete_holiday(holiday_id)
    return {"status": "ok"}
