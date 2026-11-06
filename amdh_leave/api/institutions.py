"""Endpoints للمؤسسات."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..db import Database
from .main import get_db, get_current_user

router = APIRouter()


@router.get("/institutions")
def list_institutions(db: Database = Depends(get_db),
                      _user: str = Depends(get_current_user)):
    """قائمة المؤسسات."""
    insts = db.list_institutions()
    return [{"name": i.name, "code": i.code, "kind": i.kind,
             "is_center": i.is_center, "active": i.active} for i in insts]
