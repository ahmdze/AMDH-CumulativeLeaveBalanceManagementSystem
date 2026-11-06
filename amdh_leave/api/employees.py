"""Endpoints للموظفين (CRUD)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..db import Database
from .main import get_db, get_current_user

router = APIRouter()


@router.get("/employees")
def list_employees(q: str = "", workplace: str = "", institution: str = "",
                   db: Database = Depends(get_db), _user: str = Depends(get_current_user)):
    """قائمة الموظفين."""
    emps = db.list_employees(q=q, workplace=workplace, institution=institution, with_leaves=False)
    return [{"emp_id": e.emp_id, "name": e.name, "job_title": e.job_title,
             "workplace": e.workplace, "institution": e.institution, "gender": e.gender,
             "start_date": e.start_date.isoformat() if e.start_date else None}
            for e in emps]


@router.get("/employees/{emp_id}")
def get_employee(emp_id: str, db: Database = Depends(get_db),
                 _user: str = Depends(get_current_user)):
    """تفاصيل موظف."""
    emp = db.get_employee(emp_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    return {
        "emp_id": emp.emp_id, "name": emp.name, "job_title": emp.job_title,
        "workplace": emp.workplace, "institution": emp.institution, "gender": emp.gender,
        "start_date": emp.start_date.isoformat() if emp.start_date else None,
        "end_date": emp.end_date.isoformat() if emp.end_date else None,
        "notes": emp.notes, "status": emp.status,
        "leaves": [{"id": lv.id, "type": lv.type, "start_date": lv.start_date.isoformat() if lv.start_date else None,
                     "days_actual": lv.days_actual, "status": lv.status}
                   for lv in emp.leaves if not lv.is_deleted],
    }


@router.post("/employees")
def add_employee(emp_id: str, name: str = "", job_title: str = "", workplace: str = "",
                 institution: str = "", gender: str = "ذكر", start_date: str = "",
                 notes: str = "", db: Database = Depends(get_db),
                 user: str = Depends(get_current_user)):
    """إضافة موظف جديد."""
    if db.employee_exists(emp_id):
        raise HTTPException(status_code=409, detail="الموظف موجود بالفعل")
    fields = {"name": name, "job_title": job_title, "workplace": workplace,
              "institution": institution, "gender": gender, "start_date": start_date, "notes": notes}
    db.add_employee(emp_id, fields, user)
    return {"status": "ok", "emp_id": emp_id}


@router.put("/employees/{emp_id}")
def update_employee(emp_id: str, name: str = None, job_title: str = None, workplace: str = None,
                    institution: str = None, gender: str = None, start_date: str = None,
                    notes: str = None, db: Database = Depends(get_db),
                    user: str = Depends(get_current_user)):
    """تعديل موظف."""
    fields = {}
    if name is not None:
        fields["name"] = name
    if job_title is not None:
        fields["job_title"] = job_title
    if workplace is not None:
        fields["workplace"] = workplace
    if institution is not None:
        fields["institution"] = institution
    if gender is not None:
        fields["gender"] = gender
    if start_date is not None:
        fields["start_date"] = start_date
    if notes is not None:
        fields["notes"] = notes
    if not fields:
        raise HTTPException(status_code=400, detail="لا توجد بيانات للتحديث")
    db.update_employee(emp_id, fields, user)
    return {"status": "ok"}


@router.delete("/employees/{emp_id}")
def delete_employee(emp_id: str, db: Database = Depends(get_db),
                    user: str = Depends(get_current_user)):
    """حذف موظف (ناعم)."""
    db.soft_delete_employee(emp_id, user)
    return {"status": "ok"}
