"""Endpoints للتصدير."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..db import Database
from ..services import reports as R
from ..services.security import Session
from .main import get_current_session, get_db

router = APIRouter()


@router.get("/export/excel")
def export_excel(
    institution: str = "",
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """تصدير تقرير Excel."""
    if not session.can("export"):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية التصدير")
    from ..exporters import excel as exc

    eff_inst = session.scoped_institution or institution
    employees = db.list_employees(institution=eff_inst, with_leaves=True)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = Path(f.name)
    exc.export_employee_master(path, employees)
    return FileResponse(
        str(path),
        filename=f"employees_{eff_inst or 'all'}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/export/pdf")
def export_pdf(
    institution: str = "",
    db: Database = Depends(get_db),
    session: Session = Depends(get_current_session),
):
    """تصدير تقرير PDF للأرصدة."""
    if not session.can("export"):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية التصدير")
    from ..exporters import pdf as P

    eff_inst = session.scoped_institution or institution
    employees = db.list_employees(institution=eff_inst, with_leaves=True)
    policy = db.policy()
    rows = R.global_report(employees, policy)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = Path(f.name)
    P.export_report(path, rows, policy, institution=eff_inst)
    return FileResponse(
        str(path),
        filename=f"report_{eff_inst or 'all'}.pdf",
        media_type="application/pdf",
    )
