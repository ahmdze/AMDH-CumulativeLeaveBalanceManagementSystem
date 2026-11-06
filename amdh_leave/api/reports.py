"""Endpoints للتقارير."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..db import Database
from ..services import reports as R
from ..services.security import Session
from .main import get_current_session, get_db

router = APIRouter()


@router.get("/reports/global")
def global_report(
    institution: str = "",
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """تقرير شامل للأرصدة."""
    eff_inst = session.scoped_institution or institution
    employees = db.list_employees(institution=eff_inst, with_leaves=True)
    policy = db.policy()
    rows = R.global_report(employees, policy)
    return {"rows": rows, "total": len(rows)}


@router.get("/reports/alerts")
def alerts(
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """التنبيهات."""
    employees = db.list_employees(institution=session.scoped_institution, with_leaves=True)
    policy = db.policy()
    items = R.collect_alerts(employees, policy)
    return [
        {"emp_id": a.emp_id, "name": a.name, "severity": a.severity, "message": a.message} for a in items
    ]
