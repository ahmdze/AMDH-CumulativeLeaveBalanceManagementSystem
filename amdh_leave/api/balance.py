"""Endpoints لحساب الرصيد وأثر العلاوة والترفيع."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..db import Database
from ..services import balance as B
from ..services.security import Session
from .main import get_current_session, get_db

router = APIRouter()


@router.get("/balance/{emp_id}")
def get_balance(
    emp_id: str,
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """حساب رصيد موظف مع أثر الإجازات المستبعدة على العلاوة والترفيع."""
    emp = db.get_employee(emp_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    scope = session.scoped_institution
    if scope and emp.institution != scope and emp.secondment_to != scope:
        raise HTTPException(status_code=403, detail="الموظف لا يتبع لمؤسستك")
    policy = db.policy()
    bal = B.compute_balance(emp, emp.leaves, policy)
    impact = B.promotion_impact(emp, emp.leaves, policy)
    return {
        "emp_id": emp.emp_id,
        "name": emp.name,
        "raw_days": bal.raw_days,
        "outside": bal.outside,
        "net_days": bal.net_days,
        "earned": bal.earned,
        "taken": bal.taken,
        "balance": bal.balance,
        "promotion_delay_days": impact.total_excluded_days,
        "effective_increment_date": (
            impact.effective_increment_date.isoformat() if impact.effective_increment_date else None
        ),
        "promotion_summary": impact.summary_text,
    }
