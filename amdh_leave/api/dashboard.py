"""Endpoints للوحة المؤشرات."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..db import Database
from ..services.security import Session
from .main import get_current_session, get_db

router = APIRouter()


@router.get("/dashboard")
def dashboard(
    institution: str = "",
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """بيانات لوحة المؤشرات."""
    from ..services import reports as R

    eff_inst = session.scoped_institution or institution
    employees = db.list_employees(institution=eff_inst, with_leaves=True)
    policy = db.policy()
    data = R.dashboard_data(employees, policy)
    return data
