"""Endpoints للإجازات (CRUD)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..db import Database
from .main import get_current_user, get_db

router = APIRouter()


@router.get("/leaves")
def list_leaves(emp_id: str = "", db: Database = Depends(get_db), _user: str = Depends(get_current_user)):
    """قائمة الإجازات."""
    if emp_id:
        leaves = db.list_leaves(emp_id)
    else:
        leaves = db.all_leaves()
    return [
        {
            "id": lv.id,
            "emp_id": lv.emp_id,
            "type": lv.type,
            "start_date": lv.start_date.isoformat() if lv.start_date else None,
            "end_date": lv.end_date.isoformat() if lv.end_date else None,
            "days_actual": lv.days_actual,
            "status": lv.status,
        }
        for lv in leaves
    ]


@router.get("/leaves/{leave_id}")
def get_leave(leave_id: int, db: Database = Depends(get_db), _user: str = Depends(get_current_user)):
    """تفاصيل إجازة."""
    lv = db.get_leave(leave_id)
    if lv is None:
        raise HTTPException(status_code=404, detail="الإجازة غير موجودة")
    return {
        "id": lv.id,
        "emp_id": lv.emp_id,
        "type": lv.type,
        "start_date": lv.start_date.isoformat() if lv.start_date else None,
        "end_date": lv.end_date.isoformat() if lv.end_date else None,
        "days_actual": lv.days_actual,
        "status": lv.status,
        "order": lv.order,
        "reason": lv.reason,
    }


@router.post("/leaves")
def add_leave(
    emp_id: str,
    leave_type: str,
    start_date: str,
    amount: int = 0,
    unit: str = "يوم",
    days_actual: int = 0,
    order: str = "",
    order_date: str = "",
    reason: str = "",
    db: Database = Depends(get_db),
    user: str = Depends(get_current_user),
):
    """إضافة إجازة."""
    fields = {
        "type": leave_type,
        "start_date": start_date,
        "amount": amount,
        "unit": unit,
        "days_actual": days_actual,
        "order": order,
        "order_date": order_date,
        "reason": reason,
    }
    leave_id = db.add_leave(emp_id, fields, user)
    return {"status": "ok", "leave_id": leave_id}


@router.put("/leaves/{leave_id}")
def update_leave(
    leave_id: int,
    leave_type: str = None,
    start_date: str = None,
    amount: int = None,
    days_actual: int = None,
    order: str = None,
    reason: str = None,
    db: Database = Depends(get_db),
    user: str = Depends(get_current_user),
):
    """تعديل إجازة."""
    fields = {}
    if leave_type is not None:
        fields["type"] = leave_type
    if start_date is not None:
        fields["start_date"] = start_date
    if amount is not None:
        fields["amount"] = amount
    if days_actual is not None:
        fields["days_actual"] = days_actual
    if order is not None:
        fields["order"] = order
    if reason is not None:
        fields["reason"] = reason
    if not fields:
        raise HTTPException(status_code=400, detail="لا توجد بيانات للتحديث")
    db.update_leave(leave_id, fields, user)
    return {"status": "ok"}


@router.delete("/leaves/{leave_id}")
def delete_leave(leave_id: int, db: Database = Depends(get_db), user: str = Depends(get_current_user)):
    """حذف إجازة (ناعم)."""
    db.soft_delete_leave(leave_id, user)
    return {"status": "ok"}
