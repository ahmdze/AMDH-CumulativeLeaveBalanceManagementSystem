"""Endpoints للتقارير."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..db import Database
from ..services import balance as B
from ..services import reports as R
from .main import get_db, get_current_user

router = APIRouter()


@router.get("/reports/global")
def global_report(institution: str = "", db: Database = Depends(get_db),
                  _user: str = Depends(get_current_user)):
    """تقرير شامل للأرصدة."""
    employees = db.list_employees(institution=institution, with_leaves=True)
    policy = db.policy()
    rows = R.build_global_report_rows(employees, policy)
    return {"rows": rows, "total": len(rows)}


@router.get("/reports/alerts")
def alerts(db: Database = Depends(get_db), _user: str = Depends(get_current_user)):
    """التنبيهات."""
    employees = db.list_employees(with_leaves=True)
    policy = db.policy()
    alerts = R.collect_alerts(employees, policy)
    return [{"emp_id": a.emp_id, "name": a.name, "severity": a.severity,
             "message": a.message} for a in alerts]
