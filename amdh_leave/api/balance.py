"""Endpoints لحساب الرصيد."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..db import Database
from ..services import balance as B
from .main import get_current_user, get_db

router = APIRouter()


@router.get("/balance/{emp_id}")
def get_balance(emp_id: str, db: Database = Depends(get_db), _user: str = Depends(get_current_user)):
    """حساب رصيد موظف."""
    emp = db.get_employee(emp_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    policy = db.policy()
    bal = B.compute_balance(emp, emp.leaves, policy)
    return {
        "emp_id": emp.emp_id,
        "name": emp.name,
        "raw_days": bal.raw_days,
        "outside": bal.outside,
        "net_days": bal.net_days,
        "earned": bal.earned,
        "taken": bal.taken,
        "balance": bal.balance,
    }
