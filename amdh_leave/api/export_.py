"""Endpoints للتصدير."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from ..db import Database
from .main import get_current_user, get_db

router = APIRouter()


@router.get("/export/excel")
def export_excel(
    institution: str = "", db: Database = Depends(get_db), _user: str = Depends(get_current_user)
):
    """تصدير تقرير Excel."""
    import tempfile
    from pathlib import Path

    from ..exporters import excel as exc

    employees = db.list_employees(institution=institution, with_leaves=True)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = Path(f.name)
    exc.export_employee_master(path, employees)
    return FileResponse(
        str(path),
        filename=f"employees_{institution}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
