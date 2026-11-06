"""Endpoints للموظفين (CRUD)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..db import Database
from ..services.security import Session
from .main import get_current_session, get_db

router = APIRouter()


@router.get("/employees")
def list_employees(
    q: str = "",
    workplace: str = "",
    institution: str = "",
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """قائمة الموظفين."""
    eff_inst = session.scoped_institution or institution
    emps = db.list_employees(q=q, workplace=workplace, institution=eff_inst, with_leaves=False)
    return [
        {
            "emp_id": e.emp_id,
            "name": e.name,
            "job_title": e.job_title,
            "workplace": e.workplace,
            "institution": e.institution,
            "secondment_to": e.secondment_to,
            "gender": e.gender,
            "start_date": e.start_date.isoformat() if e.start_date else None,
        }
        for e in emps
    ]


@router.get("/employees/{emp_id}")
def get_employee(
    emp_id: str,
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """تفاصيل موظف."""
    emp = db.get_employee(emp_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    scope = session.scoped_institution
    if scope and emp.institution != scope and emp.secondment_to != scope:
        raise HTTPException(status_code=403, detail="الموظف لا يتبع لمؤسستك")
    return {
        "emp_id": emp.emp_id,
        "name": emp.name,
        "job_title": emp.job_title,
        "workplace": emp.workplace,
        "institution": emp.institution,
        "secondment_to": emp.secondment_to,
        "secondment_start": emp.secondment_start.isoformat() if emp.secondment_start else None,
        "secondment_end": emp.secondment_end.isoformat() if emp.secondment_end else None,
        "gender": emp.gender,
        "start_date": emp.start_date.isoformat() if emp.start_date else None,
        "end_date": emp.end_date.isoformat() if emp.end_date else None,
        "notes": emp.notes,
        "status": emp.status,
        "leaves": [
            {
                "id": lv.id,
                "type": lv.type,
                "start_date": lv.start_date.isoformat() if lv.start_date else None,
                "days_actual": lv.days_actual,
                "status": lv.status,
            }
            for lv in emp.leaves
            if not lv.is_deleted
        ],
    }


@router.post("/employees")
def add_employee(
    emp_id: str,
    name: str = "",
    job_title: str = "",
    workplace: str = "",
    institution: str = "",
    gender: str = "ذكر",
    start_date: str = "",
    notes: str = "",
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """إضافة موظف جديد."""
    if not session.can("edit_employee"):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية إضافة موظفين")
    if db.employee_exists(emp_id):
        raise HTTPException(status_code=409, detail="الموظف موجود بالفعل")
    eff_inst = session.scoped_institution or institution
    fields = {
        "name": name,
        "job_title": job_title,
        "workplace": workplace,
        "institution": eff_inst,
        "gender": gender,
        "start_date": start_date,
        "notes": notes,
    }
    db.add_employee(emp_id, fields, session.username)
    return {"status": "ok", "emp_id": emp_id}


@router.put("/employees/{emp_id}")
def update_employee(
    emp_id: str,
    name: str | None = None,
    job_title: str | None = None,
    workplace: str | None = None,
    institution: str | None = None,
    gender: str | None = None,
    start_date: str | None = None,
    notes: str | None = None,
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """تعديل موظف."""
    if not session.can("edit_employee"):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية تعديل الموظفين")
    existing = db.get_employee(emp_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    scope = session.scoped_institution
    if scope and existing.institution != scope and existing.secondment_to != scope:
        raise HTTPException(status_code=403, detail="الموظف لا يتبع لمؤسستك")
    fields = existing.to_fields()
    if name is not None:
        fields["name"] = name
    if job_title is not None:
        fields["job_title"] = job_title
    if workplace is not None:
        fields["workplace"] = workplace
    if institution is not None and not scope:
        fields["institution"] = institution
    if gender is not None:
        fields["gender"] = gender
    if start_date is not None:
        fields["start_date"] = start_date
    if notes is not None:
        fields["notes"] = notes
    db.update_employee(emp_id, fields, session.username)
    return {"status": "ok"}


@router.delete("/employees/{emp_id}")
def delete_employee(
    emp_id: str,
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """حذف موظف (ناعم)."""
    if not session.can("delete_employee"):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية حذف الموظفين")
    existing = db.get_employee(emp_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    scope = session.scoped_institution
    if scope and existing.institution != scope:
        raise HTTPException(status_code=403, detail="الموظف لا يتبع لمؤسستك")
    db.soft_delete_employee(emp_id, session.username)
    return {"status": "ok"}
