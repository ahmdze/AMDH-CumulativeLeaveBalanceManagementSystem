"""Endpoints للإجازات (CRUD)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..db import Database
from ..services.security import Session
from .main import get_current_session, get_db

router = APIRouter()


@router.get("/leaves")
def list_leaves(
    emp_id: str = "",
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """قائمة الإجازات."""
    scope = session.scoped_institution
    if emp_id:
        emp = db.get_employee(emp_id)
        if emp and scope and emp.institution != scope and emp.secondment_to != scope:
            raise HTTPException(status_code=403, detail="الموظف لا يتبع لمؤسستك")
        leaves = db.list_leaves(emp_id)
    else:
        leaves = db.all_leaves()
        if scope:
            allowed_ids = {e.emp_id for e in db.list_employees(institution=scope, with_leaves=False)}
            leaves = [lv for lv in leaves if lv.emp_id in allowed_ids]
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
def get_leave(
    leave_id: int,
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """تفاصيل إجازة."""
    lv = db.get_leave(leave_id)
    if lv is None:
        raise HTTPException(status_code=404, detail="الإجازة غير موجودة")
    scope = session.scoped_institution
    if scope:
        emp = db.get_employee(lv.emp_id)
        if emp and emp.institution != scope and emp.secondment_to != scope:
            raise HTTPException(status_code=403, detail="الإجازة لا تتبع لمؤسستك")
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
    session: Session = Depends(get_current_session),
):
    """إضافة إجازة."""
    if not session.can("edit_leave"):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية تسجيل الإجازات")
    emp = db.get_employee(emp_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    scope = session.scoped_institution
    if scope and emp.institution != scope and emp.secondment_to != scope:
        raise HTTPException(status_code=403, detail="الموظف لا يتبع لمؤسستك")
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
    leave_id = db.add_leave(emp_id, fields, session.username)
    return {"status": "ok", "leave_id": leave_id}


@router.put("/leaves/{leave_id}")
def update_leave(
    leave_id: int,
    leave_type: str | None = None,
    start_date: str | None = None,
    amount: int | None = None,
    days_actual: int | None = None,
    order: str | None = None,
    reason: str | None = None,
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """تعديل إجازة."""
    if not session.can("edit_leave"):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية تعديل الإجازات")
    existing = db.get_leave(leave_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="الإجازة غير موجودة")
    scope = session.scoped_institution
    if scope:
        emp = db.get_employee(existing.emp_id)
        if emp and emp.institution != scope and emp.secondment_to != scope:
            raise HTTPException(status_code=403, detail="الإجازة لا تتبع لمؤسستك")
    fields = existing.to_fields()
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
    db.update_leave(leave_id, fields, session.username)
    return {"status": "ok"}


@router.delete("/leaves/{leave_id}")
def delete_leave(
    leave_id: int,
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """حذف إجازة (ناعم)."""
    if not session.can("delete_leave"):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية حذف الإجازات")
    existing = db.get_leave(leave_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="الإجازة غير موجودة")
    scope = session.scoped_institution
    if scope:
        emp = db.get_employee(existing.emp_id)
        if emp and emp.institution != scope and emp.secondment_to != scope:
            raise HTTPException(status_code=403, detail="الإجازة لا تتبع لمؤسستك")
    db.soft_delete_leave(leave_id, session.username)
    return {"status": "ok"}
