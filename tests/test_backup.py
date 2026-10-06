"""اختبارات النسخ الاحتياطي: الإنشاء، الدوران، الفحص، الاستعادة، والدمج."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import date
from pathlib import Path

from amdh_leave.db import Database
from amdh_leave.services.backup import BackupService
from tests.conftest import create_legacy_db


def test_create_backup_and_list(db, tmp_path):
    service = BackupService(db, tmp_path / "backups")
    path = service.create("manual")
    assert path is not None and path.exists()
    names = {item["name"] for item in service.list_backups()}
    assert path.name in names
    assert all(item["valid"] for item in service.list_backups())
    assert service.latest() == path


def test_backup_is_a_valid_database(db, tmp_path):
    service = BackupService(db, tmp_path / "backups")
    path = service.create("manual")
    probe = sqlite3.connect(str(path))
    try:
        assert probe.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 1
        assert probe.execute("SELECT COUNT(*) FROM leaves").fetchone()[0] == 2
    finally:
        probe.close()


def test_create_if_changed_skips_when_unchanged(db, tmp_path):
    service = BackupService(db, tmp_path / "backups")
    first = service.create_if_changed("start")
    assert first is not None
    assert service.create_if_changed("start") is None   # لا تغيير بعد النسخة
    db.add_employee("777", {"name": "موظف جديد لاختبار التغيير", "gender": "ذكر",
                            "start_date": "2024-01-01", "institution": "جهة"})
    second = service.create_if_changed("start")
    assert second is not None and second != first


def test_rotate_keeps_newest(db, tmp_path):
    service = BackupService(db, tmp_path / "backups")
    for _ in range(5):
        service.create("auto")
    assert len(service.list_backups()) >= 5
    service.rotate(keep=2)
    assert len(service.list_backups()) == 2


def test_invalid_file_detection(tmp_path):
    service = BackupService(Database(create_legacy_db(tmp_path / "x.db"), tmp_path / "b"),
                            tmp_path / "b")
    junk = tmp_path / "b" / "backup_junk.db"
    junk.write_text("هذا ليس ملف قاعدة بيانات", encoding="utf-8")
    items = {item["name"]: item for item in service.list_backups()}
    assert items["backup_junk.db"]["valid"] is False
    ok, message = service.restore(junk)
    assert ok is False and "صالح" in message
    service.db.close()


def test_restore_reverts_changes_and_keeps_safety_copy(db, tmp_path):
    service = BackupService(db, tmp_path / "backups")
    snapshot = service.create("manual")
    db.add_employee("888", {"name": "سيُلغى بالاستعادة", "gender": "ذكر",
                            "start_date": "2024-01-01"})
    assert db.employee_exists("888")

    ok, message = service.restore(snapshot)
    assert ok is True
    assert "pre_restore" in message
    assert not db.employee_exists("888")
    assert len(db.get_employee("57454545").leaves) == 2
    assert list((tmp_path / "backups").glob("pre_restore_*.db"))


def test_restore_missing_file(db, tmp_path):
    service = BackupService(db, tmp_path / "backups")
    ok, message = service.restore(tmp_path / "nope.db")
    assert ok is False and "غير موجود" in message


def test_import_merge_adds_and_updates(db, tmp_path):
    other = Database(tmp_path / "other.db", tmp_path / "ob")
    other.add_employee("999", {"name": "موظف من قاعدة أخرى", "gender": "أنثى",
                               "institution": "جهة أخرى", "start_date": "2020-01-01"})
    other.add_leave("999", {"type": "اعتيادية", "start_date": "2024-01-01",
                            "end_date": "2024-01-10", "days_actual": 10, "amount": 10,
                            "unit": "يوم"})
    other.close()

    service = BackupService(db, tmp_path / "backups")
    service.import_mode = "update"
    result = service.import_merge(tmp_path / "other.db", "tester")
    assert result["errors"] == []
    assert result["added"] == 1 and result["leaves"] == 1
    assert db.employee_exists("999")
    assert len(db.get_employee("999").leaves) == 1

    # الدمج مرة أخرى في وضع «تجاهل» لا يضيف شيئاً
    service.import_mode = "skip"
    again = service.import_merge(tmp_path / "other.db", "tester")
    assert again["added"] == 0 and again["skipped"] == 1

    # تحديث موظف موجود
    updated = Database(tmp_path / "other.db", tmp_path / "ob")
    updated.update_employee("999", {"name": "اسم محدث", "gender": "أنثى",
                                    "start_date": "2020-01-01"})
    updated.close()
    service.import_mode = "update"
    third = service.import_merge(tmp_path / "other.db", "tester")
    assert third["updated"] == 1
    assert db.get_employee("999").name == "اسم محدث"


def test_import_merge_rejects_bad_file(db, tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_text("not a database", encoding="utf-8")
    service = BackupService(db, tmp_path / "backups")
    result = service.import_merge(bad)
    assert result["errors"]
    result = service.import_merge(tmp_path / "missing.db")
    assert "غير موجود" in result["errors"][0]


def test_import_merge_rolls_back_on_error(db, tmp_path):
    """أي خطأ داخل الدمج يجب ألا يترك قاعدة نصف مستوردة (معاملة واحدة)."""
    other = Database(tmp_path / "src2.db", tmp_path / "ob2")
    other.add_employee("A1", {"name": "أول", "gender": "ذكر", "start_date": "2020-01-01"})
    other.add_employee("A2", {"name": "ثاني", "gender": "ذكر", "start_date": "2020-01-01"})
    other.close()

    before = db.stats()["employees"]
    service = BackupService(db, tmp_path / "backups")
    original = service._merge_employee
    calls = {"n": 0}

    def flaky(cursor, emp, leaves, result, exists):
        calls["n"] += 1
        if calls["n"] == 2:
            raise sqlite3.OperationalError("فشل محاكى أثناء الدمج")
        return original(cursor, emp, leaves, result, exists)

    service._merge_employee = flaky
    result = service.import_merge(tmp_path / "src2.db", "tester")

    assert result["errors"], "يجب الإبلاغ عن الخطأ"
    assert calls["n"] == 2
    assert db.stats()["employees"] == before, "يجب إرجاع كل التغييرات"
    assert not db.employee_exists("A1")
    assert not db.employee_exists("A2")
