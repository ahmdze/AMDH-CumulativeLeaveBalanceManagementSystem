"""اختبارات وحدة المؤسسات: CRUD، Excel، المستخدم المرتبط، وحالة الإرسال الشهري."""

from __future__ import annotations

from pathlib import Path

import pytest

from amdh_leave.db import Database
from amdh_leave.services import institutions as INST


def new_db(tmp_path: Path, name: str = "center.db") -> Database:
    return Database(tmp_path / name, tmp_path / f"backups_{name}")


def add_employee(db: Database, emp_id: str, institution: str) -> None:
    db.add_employee(emp_id, {"name": f"موظف {emp_id}", "institution": institution,
                             "start_date": "2015-01-01"}, "admin")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def test_save_and_list_institutions(tmp_path):
    db = new_db(tmp_path)
    db.save_institution({"name": "مستشفى الكرامة", "code": "H1", "kind": "مستشفى",
                         "manager": "د. علي", "phone": "0770", "address": "المدينة"}, "admin")
    listed = db.list_institutions()
    assert len(listed) == 1
    hospital = listed[0]
    assert (hospital.name, hospital.code, hospital.kind) == ("مستشفى الكرامة", "H1", "مستشفى")
    assert hospital.active is True and hospital.created_at

    db.save_institution({"name": "مستشفى الكرامة", "code": "H1", "manager": "د. حسن"}, "admin")
    assert db.get_institution("مستشفى الكرامة").manager == "د. حسن"
    assert len(db.list_institutions()) == 1, "التعديل لا يُنشئ سجلاً جديداً"
    db.close()


def test_delete_institution_guard(tmp_path):
    db = new_db(tmp_path)
    db.save_institution({"name": "مستشفى النور", "code": "H2"}, "admin")
    add_employee(db, "5001", "مستشفى النور")
    ok, message = db.delete_institution("مستشفى النور")
    assert ok is False and "موظف" in message

    db.save_institution({"name": "مستشفى فارغ", "code": "H5"}, "admin")
    ok, _message = db.delete_institution("مستشفى فارغ")
    assert ok is True
    assert db.get_institution("مستشفى فارغ") is None
    db.close()


def test_center_institution_flag(tmp_path):
    db = new_db(tmp_path)
    db.save_institution({"name": "مركز الدائرة", "code": "C0", "kind": "مركز الدائرة"}, "admin")
    db.save_institution({"name": "مستشفى أ", "code": "H3"}, "admin")
    db.set_center_institution("مركز الدائرة")
    assert db.center_institution() == "مركز الدائرة"
    flags = {item.name: item.is_center for item in db.list_institutions()}
    assert flags == {"مركز الدائرة": True, "مستشفى أ": False}
    db.close()


def test_employee_counts(tmp_path):
    db = new_db(tmp_path)
    add_employee(db, "6001", "مستشفى أ")
    add_employee(db, "6002", "مستشفى أ")
    add_employee(db, "6003", "مستشفى ب")
    db.save_institution({"name": "مستشفى أ"}, "admin")
    db.save_institution({"name": "مستشفى ب"}, "admin")
    counts = {item.name: item.employees for item in db.list_institutions()}
    assert counts == {"مستشفى أ": 2, "مستشفى ب": 1}
    db.close()


# ---------------------------------------------------------------------------
# المستخدم المرتبط
# ---------------------------------------------------------------------------
def test_auto_user_for_institution(tmp_path):
    db = new_db(tmp_path)
    institution = db.save_institution({"name": "مستشفى الكرامة", "code": "H1"}, "admin")
    account, password = INST.create_user_for_institution(db, institution, user="admin")
    assert account.username == "h1"
    assert account.institution == "مستشفى الكرامة"
    assert account.role == "editor" and account.active is True
    assert len(password) >= 8
    assert db.get_institution("مستشفى الكرامة").username == "h1"
    # كلمة المرور تعمل فعلاً
    from amdh_leave.services import security as sec
    assert sec.verify_password(password, account.password_hash, account.salt,
                               account.iterations)
    db.close()


def test_username_is_unique_and_ascii(tmp_path):
    db = new_db(tmp_path)
    first = db.save_institution({"name": "مستشفى الكرامة", "code": "H1"}, "admin")
    second = db.save_institution({"name": "مستشفى الكرامة الثاني", "code": "H1"}, "admin")
    account1, _ = INST.create_user_for_institution(db, first, user="admin")
    account2, _ = INST.create_user_for_institution(db, second, user="admin")
    assert account1.username == "h1"
    assert account2.username != account1.username
    assert account2.username.isascii()

    arabic = db.save_institution({"name": "مركز صحي النور"}, "admin")
    account3, _ = INST.create_user_for_institution(db, arabic, password="Secret123", user="admin")
    assert account3.username.isascii() and account3.username
    assert db.get_institution("مركز صحي النور").code, "يُولَّد رمز تلقائياً عند غيابه"
    db.close()


def test_scoped_user_sees_only_own_institution(tmp_path):
    from PyQt6.QtCore import QSettings
    from amdh_leave.context import AppContext
    from amdh_leave.services.backup import BackupService
    from amdh_leave.services.security import make_session
    db = new_db(tmp_path)
    add_employee(db, "7001", "مستشفى أ")
    add_employee(db, "7002", "مستشفى ب")
    institution = db.save_institution({"name": "مستشفى أ", "code": "HA"}, "admin")
    account, _ = INST.create_user_for_institution(db, institution, user="admin")
    ctx = AppContext(paths=None, db=db, backup=BackupService(db, tmp_path / "b"),
                     session=make_session(account, True),
                     settings=QSettings("MyCompany", "AMDH-Institutions-Test"))
    assert [employee.emp_id for employee in ctx.employees()] == ["7001"]
    assert ctx.session.scoped_institution == "مستشفى أ"
    db.close()


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
def test_excel_roundtrip(tmp_path):
    db = new_db(tmp_path)
    db.save_institution({"name": "مستشفى الكرامة", "code": "H1", "kind": "مستشفى",
                         "manager": "د. علي", "phone": "0770", "username": "h1"}, "admin")
    db.save_institution({"name": "مركز صحي النور", "code": "PH2", "kind": "مركز صحي"}, "admin")
    output = INST.export_excel(tmp_path / "institutions.xlsx", db)
    assert output.exists()

    headers, rows = INST.read_excel(output)
    assert "اسم المؤسسة" in headers
    assert len(rows) == 2
    mapping = INST.guess_mapping(headers)
    assert mapping["name"] and mapping["code"] and mapping["kind"]
    first = INST.normalize_row(rows[0], mapping)
    assert first["name"] in {"مستشفى الكرامة", "مركز صحي النور"}
    assert first["active"] is True
    db.close()


def test_template_and_mapping(tmp_path):
    path = INST.export_template(tmp_path / "template.xlsx")
    assert path.exists()
    headers, rows = INST.read_excel(path)
    assert headers == ["name", "code", "kind", "manager", "phone", "address", "notes",
                       "username", "active"]
    assert len(rows) == 2
    mapping = INST.guess_mapping(headers)
    assert mapping["name"] == "name" and mapping["kind"] == "kind"
    row = INST.normalize_row(rows[0], mapping)
    assert row["name"] == "مستشفى الكرامة" and row["kind"] == "مستشفى"

    # أعمدة عربية
    arabic_headers = ["اسم المؤسسة", "الرمز", "النوع", "المدير/المسؤول", "الهاتف"]
    mapping2 = INST.guess_mapping(arabic_headers)
    assert mapping2["name"] == "اسم المؤسسة" and mapping2["code"] == "الرمز"
    db = new_db(tmp_path)
    result = INST.import_from_rows(
        db, [{"اسم المؤسسة": "مستشفى جديد", "الرمز": "H9", "النوع": "مستشفى"}], mapping2,
        user="admin", password_mode="unified", unified_password="Welcome123")
    assert result["added"] == 1 and len(result["users"]) == 1
    institution = db.get_institution("مستشفى جديد")
    assert institution and institution.username
    account = db.get_user(institution.username)
    from amdh_leave.services import security as sec
    assert sec.verify_password("Welcome123", account.password_hash, account.salt,
                               account.iterations)
    db.close()


def test_import_rows_updates_and_skips(tmp_path):
    db = new_db(tmp_path)
    db.save_institution({"name": "مستشفى قديم", "code": "H1", "manager": "د. س"}, "admin")
    mapping = INST.guess_mapping(["name", "code", "manager", "active"])
    rows = [
        {"name": "مستشفى قديم", "code": "H1", "manager": "د. جديد", "active": "نعم"},
        {"name": "مستشفى ثانٍ", "code": "H2", "manager": "", "active": "لا"},
        {"name": "", "code": "H3", "manager": "", "active": "نعم"},
        {"name": "مستشفى ثانٍ", "code": "H2", "manager": "", "active": "نعم"},
    ]
    result = INST.import_from_rows(db, rows, mapping, user="admin", create_users=False)
    assert result["added"] == 1 and result["updated"] == 1 and result["skipped"] == 2
    assert db.get_institution("مستشفى قديم").manager == "د. جديد"
    assert db.get_institution("مستشفى ثانٍ").active is False
    assert any("صف 3" in error for error in result["errors"])
    assert any("مكرر" in error for error in result["errors"])
    db.close()


def test_credentials_export(tmp_path):
    db = new_db(tmp_path)
    mapping = INST.guess_mapping(["name", "code"])
    result = INST.import_from_rows(db, [{"name": "مستشفى أ", "code": "HA"},
                                        {"name": "مستشفى ب", "code": "HB"}], mapping,
                                   user="admin")
    assert len(result["users"]) == 2
    path = INST.export_credentials(tmp_path / "credentials.xlsx", result["users"])
    assert path.exists()
    headers, rows = INST.read_excel(path)
    assert headers == ["اسم المؤسسة", "اسم المستخدم", "كلمة المرور"]
    assert len(rows) == 2
    for row in rows:
        assert row["اسم المستخدم"] and row["كلمة المرور"]
    db.close()


# ---------------------------------------------------------------------------
# حالة الإرسال الشهري
# ---------------------------------------------------------------------------
def test_status_and_pending(tmp_path):
    from amdh_leave.services import transfer as T
    db = new_db(tmp_path)
    db.save_institution({"name": "مركز الدائرة", "kind": "مركز الدائرة"}, "admin")
    db.set_center_institution("مركز الدائرة")
    db.save_institution({"name": "مستشفى أ", "code": "HA"}, "admin")
    db.save_institution({"name": "مستشفى ب", "code": "HB"}, "admin")
    add_employee(db, "8001", "مستشفى أ")

    # مستشفى أ يرسل: نستورد ملفاً فارغاً من نسخة أخرى
    other = Database(tmp_path / "other.db", tmp_path / "bo")
    other.save_institution({"name": "مستشفى أ", "code": "HA"}, "admin")
    add_employee(other, "8001", "مستشفى أ")
    file = tmp_path / "a.db"
    T.export_transfer(other, file, institution="مستشفى أ", user="ha")
    T.apply_transfer(db, file, user="admin", attachments_dir=tmp_path / "att")
    other.close()

    status = {row["name"]: row for row in INST.institutions_status(db)}
    assert status["مستشفى أ"]["reported_this_month"] is True
    assert status["مستشفى أ"]["last_import_at"]
    assert status["مستشفى ب"]["reported_this_month"] is False
    pending = [row["name"] for row in INST.pending_institutions(db)]
    assert pending == ["مستشفى ب"], "مركز الدائرة لا يُطالب بالإرسال"
    assert INST.month_label("2026-10") == "10/2026"
    db.close()


def test_report_saved_with_institution_history(tmp_path):
    from amdh_leave.services import transfer as T
    db = new_db(tmp_path)
    db.save_institution({"name": "مستشفى أ", "code": "HA"}, "admin")
    other = Database(tmp_path / "other.db", tmp_path / "bo")
    other.save_institution({"name": "مستشفى أ", "code": "HA"}, "admin")
    add_employee(other, "9001", "مستشفى أ")
    file = T.export_transfer(other, tmp_path / "a.amdhz", institution="مستشفى أ", user="ha")["path"]
    T.apply_transfer(db, file, user="admin", attachments_dir=tmp_path / "att")

    records = db.list_imports(institution="مستشفى أ", direction="import")
    assert len(records) == 1
    assert records[0].employees_added == 1
    assert records[0].checksum
    assert db.checksum_seen(records[0].checksum) is not None
    other.close()
    db.close()
