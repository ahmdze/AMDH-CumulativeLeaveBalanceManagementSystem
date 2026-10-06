"""تهيئة اختبارات pytest: قاعدة بيانات مؤقتة ومسارات معزولة."""

from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amdh_leave import config                        # noqa: E402
from amdh_leave.context import AppContext            # noqa: E402
from amdh_leave.db import Database                   # noqa: E402
from amdh_leave.models import Employee, Leave        # noqa: E402
from amdh_leave.rules import Policy                  # noqa: E402
from amdh_leave.services.backup import BackupService  # noqa: E402
from amdh_leave.services.security import make_session  # noqa: E402

# بيانات الموظف المرجعي (نفس بيانات النظام الحقيقي) — الأرقام المعتمدة
LEGACY_EMPLOYEE = {
    "emp_id": "57454545",
    "name": "احمد زياد رحيمه",
    "job_title": "تقني طبي",
    "workplace": "المركز الصحي",
    "institution": "دائرة صحة المحافظة",
    "gender": "ذكر",
    "start_date": "2019-04-30",
    "notes": "",
}
LEGACY_LEAVES = [
    # إجازة 5 سنوات: 1825 يوماً مستبعدة من الخدمة (خارج الرصيد)
    {"emp_id": "57454545", "type": "5 سنوات", "start_date": "2020-04-30",
     "from_date": "2020-04-30", "amount": 5, "unit": "سنة", "days_actual": 1825,
     "order_num": "100", "order_date": "2020-04-01", "outside_balance": 1,
     "reason": "إجازة خمس سنوات", "added_date": "2020-04-01"},
    # إجازة اعتيادية 20 يوماً
    {"emp_id": "57454545", "type": "اعتيادية", "start_date": "2026-04-30",
     "from_date": "2026-04-30", "amount": 20, "unit": "يوم", "days_actual": 20,
     "order_num": "205", "order_date": "2026-04-15", "outside_balance": 0,
     "reason": "", "added_date": "2026-04-15"},
]
LEGACY_TODAY = date(2026, 10, 6)   # التاريخ الذي تُحتسب عليه الأرقام المعتمدة


def create_legacy_db(path: Path) -> Path:
    """ينشئ قاعدة بيانات بالمخطط القديم تماماً (قبل الترقية) مع بيانات مرجعية."""
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE employees (
            emp_id TEXT PRIMARY KEY, name TEXT, job_title TEXT, workplace TEXT,
            gender TEXT, start_date TEXT, notes TEXT, institution TEXT);
        CREATE TABLE leaves (
            id INTEGER PRIMARY KEY AUTOINCREMENT, emp_id TEXT, type TEXT, start_date TEXT,
            from_date TEXT, amount INTEGER, unit TEXT, days_actual INTEGER, order_num TEXT,
            order_date TEXT, outside_balance INTEGER, reason TEXT, added_date TEXT,
            FOREIGN KEY(emp_id) REFERENCES employees(emp_id) ON DELETE CASCADE);
    """)
    columns = ["emp_id", "name", "job_title", "workplace", "gender", "start_date", "notes", "institution"]
    conn.execute(f"INSERT INTO employees ({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
                 [LEGACY_EMPLOYEE[c] for c in columns])
    for leave in LEGACY_LEAVES:
        keys = list(leave)
        conn.execute(f"INSERT INTO leaves ({','.join(keys)}) VALUES ({','.join('?' * len(keys))})",
                     [leave[k] for k in keys])
    conn.commit()
    conn.execute("PRAGMA user_version = 0")
    conn.close()
    return path


@pytest.fixture()
def tmp_paths(tmp_path) -> config.Paths:
    return config.Paths(tmp_path).ensure()


@pytest.fixture()
def legacy_db(tmp_path) -> Path:
    return create_legacy_db(tmp_path / config.DB_FILENAME)


@pytest.fixture()
def db(legacy_db, tmp_path) -> Database:
    database = Database(legacy_db, tmp_path / "backups")
    yield database
    database.close()


@pytest.fixture()
def empty_db(tmp_path) -> Database:
    database = Database(tmp_path / "empty.db", tmp_path / "backups")
    yield database
    database.close()


@pytest.fixture()
def policy(db) -> Policy:
    return db.policy(refresh=True)


@pytest.fixture()
def employee(db) -> Employee:
    return db.get_employee("57454545")


@pytest.fixture()
def ctx(tmp_path, db) -> AppContext:
    from PyQt6.QtCore import QSettings
    return AppContext(paths=config.Paths(tmp_path).ensure(), db=db,
                      backup=BackupService(db, tmp_path / "backups"),
                      session=make_session(None, False),
                      settings=QSettings("MyCompany", "AMDH-Tests"))


def make_leave(**kwargs) -> Leave:
    data = {"type": "اعتيادية", "start_date": date(2026, 1, 1), "end_date": date(2026, 1, 10),
            "amount": 10, "unit": "يوم", "days_actual": 10, "status": "approved"}
    data.update(kwargs)
    return Leave(**data)
