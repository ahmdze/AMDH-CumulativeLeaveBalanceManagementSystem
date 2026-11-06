"""Endpoints للوحة المؤشرات."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..db import Database
from .main import get_current_user, get_db

router = APIRouter()


@router.get("/dashboard")
def dashboard(institution: str = "", db: Database = Depends(get_db), _user: str = Depends(get_current_user)):
    """بيانات لوحة المؤشرات."""
    from ..services import reports as R

    employees = db.list_employees(institution=institution, with_leaves=True)
    policy = db.policy()
    data = R.dashboard_data(employees, policy)
    return data
