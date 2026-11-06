"""اختبارات قاعدة البيانات: الترحيل الآمن، الحذف الناعم، التدقيق، والمعاملات."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from amdh_leave import config
from amdh_leave.db import SCHEMA_VERSION, Database
from amdh_leave.rules import LeaveRule
from tests.conftest import LEGACY_EMPLOYEE, LEGACY_LEAVES


# ---------------------------------------------------------------------------
# الترحيل
# ---------------------------------------------------------------------------
def test_migration_adds_columns_and_keeps_data(db):
    columns = {row[1] for row in db.conn.execute("PRAGMA table_info(employees)")}
    assert {"end_date", "status", "created_at", "updated_at", "deleted_at", "deleted_by"} <= columns
    leave_columns = {row[1] for row in db.conn.execute("PRAGMA table_info(leaves)")}
    assert {"end_date", "working_days", "count_mode", "status", "modified_at", "is_adjustment",
            "manual_days", "deleted_at"} <= leave_columns

    employee = db.get_employee("57454545")
    assert employee.name == LEGACY_EMPLOYEE["name"]
    assert employee.institution == LEGACY_EMPLOYEE["institution"]
    assert len(employee.leaves) == len(LEGACY_LEAVES)
    assert [lv.days_actual for lv in employee.leaves] == [1825, 20]
    assert employee.leaves[0].outside_balance is True


def test_migration_sets_schema_version_and_creates_backup(legacy_db, tmp_path):
    backups = tmp_path / "backups"
    database = Database(legacy_db, backups)
    try:
        assert database.schema_version == SCHEMA_VERSION
        assert database.migrated is True
        assert list(backups.glob("pre_migration_*.db")), "يجب إنشاء نسخة قبل الترحيل"
    finally:
        database.close()


def test_migration_is_idempotent(legacy_db, tmp_path):
    first = Database(legacy_db, tmp_path / "backups")
    rules = first.list_rules()
    meta = first.get_meta()
    first.close()
    second = Database(legacy_db, tmp_path / "backups")
    try:
        assert second.migrated is False
        assert second.list_rules().keys() == rules.keys()
        assert second.get_meta() == meta
        assert second.get_employee("57454545").leaves[1].days_actual == 20
    finally:
        second.close()


def test_backfill_computes_end_date_from_days(db):
    leave = db.get_employee("57454545").leaves[1]
    assert leave.end_date == date(2026, 5, 19)   # 20 يوماً بدءاً من 2026-04-30
    assert leave.start_date == date(2026, 4, 30)


def test_indexes_and_wal_are_enabled(db):
    indexes = {row[0] for row in db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"idx_leaves_emp", "idx_leaves_start", "idx_emp_inst", "idx_emp_work",
            "idx_audit_ts"} <= indexes
    assert db.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_fresh_database_is_usable(empty_db):
    assert empty_db.schema_version == SCHEMA_VERSION
    assert empty_db.stats()["employees"] == 0
    assert empty_db.policy().days_per_leave == config.DAYS_PER_LEAVE
    assert len(empty_db.list_rules()) >= 9


# ---------------------------------------------------------------------------
# الموظفون
# ---------------------------------------------------------------------------
def test_employee_crud_and_filters(db):
    db.add_employee("200", {"name": "زينب علي", "job_title": "ممرضة", "workplace": "مستشفى ب",
                            "institution": "صحة ب", "gender": "أنثى", "start_date": "2021-06-01"},
                    "tester")
    assert db.employee_exists("200")
    assert len(db.list_employees()) == 2
    assert [e.emp_id for e in db.list_employees(q="زينب")] == ["200"]
    assert [e.emp_id for e in db.list_employees(institution="صحة ب")] == ["200"]
    assert [e.emp_id for e in db.list_employees(workplace="المركز الصحي")] == ["57454545"]
    assert set(db.distinct_values("institution")) == {"دائرة صحة المحافظة", "صحة ب"}

    db.update_employee("200", {"name": "زينب علي حسن", "start_date": "2021-06-01",
                               "gender": "أنثى", "institution": "صحة ب"}, "tester")
    assert db.get_employee("200").name == "زينب علي حسن"
    assert db.get_employee("200").updated_at


def test_distinct_values_rejects_unknown_column(db):
    with pytest.raises(ValueError):
        db.distinct_values("name; DROP TABLE employees")


def test_soft_delete_and_restore_employee(db):
    db.soft_delete_employee("57454545", "tester")
    assert db.stats()["employees"] == 0
    assert db.stats()["employees_deleted"] == 1
    assert db.list_employees() == []
    assert [e.emp_id for e in db.list_employees(include_deleted=True)] == ["57454545"]
    assert db.get_employee("57454545", include_deleted=False) is None

    db.restore_employee("57454545", "tester")
    assert db.stats()["employees"] == 1
    assert len(db.get_employee("57454545").leaves) == 2


def test_purge_employee_cascades(db):
    db.soft_delete_employee("57454545", "tester")
    db.purge_employee("57454545")
    assert not db.employee_exists("57454545")
    assert db.conn.execute("SELECT COUNT(*) FROM leaves").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# الإجازات
# ---------------------------------------------------------------------------
def test_add_update_leave_preserves_added_date(db):
    """الخطأ القديم: تعديل الإجازة كان يكتب تاريخ الإضافة = اليوم."""
    leave_id = db.add_leave("57454545", {
        "type": "مرضية", "start_date": "2026-01-05", "end_date": "2026-01-09",
        "amount": 5, "unit": "يوم", "days_actual": 5, "order": "300",
        "order_date": "2026-01-01", "reason": "زكام", "added_date": "2026-01-02 08:00:00"},
        "tester")
    original = db.get_leave(leave_id)
    assert original.added_date == "2026-01-02 08:00:00"
    assert original.order == "300"          # order_num يُقرأ باسم order

    db.update_leave(leave_id, {"type": "مرضية", "start_date": "2026-01-05",
                               "end_date": "2026-01-10", "amount": 6, "unit": "يوم",
                               "days_actual": 6, "order": "300", "order_date": "2026-01-01",
                               "reason": "تمديد"}, "tester")
    updated = db.get_leave(leave_id)
    assert updated.days_actual == 6
    assert updated.added_date == "2026-01-02 08:00:00"   # لم يتغير
    assert updated.modified_at and updated.modified_by == "tester"
    assert updated.created_by == "tester"


def test_soft_delete_and_restore_leave(db):
    leave_id = db.get_employee("57454545").leaves[0].id
    db.soft_delete_leave(leave_id, "tester", "خطأ إدخال")
    assert len(db.list_leaves("57454545")) == 1
    assert len(db.list_leaves("57454545", include_deleted=True)) == 2
    db.restore_leave(leave_id, "tester")
    assert len(db.list_leaves("57454545")) == 2


def test_purge_all_deleted(db):
    leave_id = db.get_employee("57454545").leaves[0].id
    db.soft_delete_leave(leave_id, "tester")
    db.soft_delete_employee("57454545", "tester")
    result = db.purge_all_deleted()
    assert result == {"leaves": 1, "employees": 1}
    assert db.stats()["employees"] == 0


def test_leaves_in_range_joins_employee(db):
    rows = db.leaves_in_range(date(2026, 4, 1), date(2026, 6, 30))
    assert len(rows) == 1
    employee, leave = rows[0]
    assert employee.name == LEGACY_EMPLOYEE["name"]
    assert leave.type == "اعتيادية"
    assert db.leaves_in_range(date(2026, 6, 1), date(2026, 6, 30)) == []
    assert db.leaves_in_range(date(2020, 1, 1), date(2026, 12, 31),
                              institution="دائرة صحة المحافظة")


# ---------------------------------------------------------------------------
# المعاملات والتدقيق والجداول المساندة
# ---------------------------------------------------------------------------
def test_transaction_rolls_back(empty_db):
    with pytest.raises(RuntimeError):
        with empty_db.transaction() as conn:
            conn.execute("INSERT INTO employees(emp_id, name) VALUES('ROLL','x')")
            raise RuntimeError("boom")
    assert empty_db.get_employee("ROLL") is None


def test_audit_log_records_actions(db):
    db.add_employee("300", {"name": "اختبار", "gender": "ذكر", "start_date": "2020-01-01"}, "tester")
    db.update_employee("300", {"name": "اختبار 2", "gender": "ذكر", "start_date": "2020-01-01"},
                       "tester")
    db.soft_delete_employee("300", "tester")
    entries = db.list_audit()
    actions = [e.action for e in entries]
    assert actions[0] == "حذف"
    assert "إضافة" in actions and "تعديل" in actions
    assert all(e.username == "tester" for e in entries)
    assert db.list_audit(action="إضافة")[0].entity == "employee"
    assert "tester" in db.audit_values("username")
    assert db.list_audit(date_from="2000-01-01", date_to="2000-01-02") == []


def test_meta_and_policy_roundtrip(db):
    from dataclasses import replace as dc_replace
    policy = db.policy(refresh=True)
    policy = dc_replace(policy, days_per_leave=7, expiry_years=3, weekend=(5,))
    db.save_policy(policy)
    reloaded = db.policy(refresh=True)
    assert reloaded.days_per_leave == 7
    assert reloaded.expiry_years == 3
    assert reloaded.weekend == (5,)


def test_rules_crud(db):
    db.save_rule(LeaveRule(type="عارضة", consumes_balance=True, quota_days=10,
                           quota_period="year", order_index=50))
    assert "عارضة" in db.policy(refresh=True).rules
    db.save_rule(LeaveRule(type="عارضة", consumes_balance=False, order_index=50))
    assert db.policy(refresh=True).rule("عارضة").consumes_balance is False
    db.delete_rule("عارضة")
    assert "عارضة" not in db.policy(refresh=True).rules


def test_holidays(db):
    db.add_holiday(date(2026, 1, 1), "رأس السنة")
    db.add_holiday(date(2026, 3, 21), "نوروز")
    assert len(db.list_holidays()) == 2
    assert len(db.list_holidays(2026)) == 2
    assert len(db.list_holidays(2025)) == 0
    assert date(2026, 1, 1) in db.holiday_set()
    db.delete_holiday(db.list_holidays()[0].id)
    assert len(db.list_holidays()) == 1


def test_users_and_login_touch(db):
    from amdh_leave.models import AppUser
    from amdh_leave.services.security import hash_password
    users = db.list_users()
    assert users and users[0].username == "admin"
    password_hash, salt, iterations = hash_password("secret")
    db.save_user(AppUser(username="sara", display_name="سارة", role="editor",
                         institution="صحة ب", password_hash=password_hash, salt=salt,
                         iterations=iterations))
    stored = db.get_user("sara")
    assert stored.role == "editor" and stored.institution == "صحة ب"
    db.touch_login("sara")
    assert db.get_user("sara").last_login
    db.delete_user("sara")
    assert db.get_user("sara") is None


def test_attachments(db):
    leave_id = db.get_employee("57454545").leaves[0].id
    db.add_attachment(leave_id, "57454545", "order.pdf", "abc.pdf", "tester")
    items = db.list_attachments(leave_id)
    assert len(items) == 1 and items[0].filename == "order.pdf"
    db.delete_attachment(items[0].id, "tester")
    assert db.list_attachments(leave_id) == []


def test_stats_and_integrity(db):
    stats = db.stats()
    assert stats["employees"] == 1 and stats["leaves"] == 2
    assert stats["schema_version"] == SCHEMA_VERSION
    assert stats["path"].endswith(config.DB_FILENAME)
    ok, message = db.integrity_check()
    assert ok and message.lower() == "ok"


def test_backup_to_and_vacuum(db, tmp_path):
    target = tmp_path / "copy.db"
    db.backup_to(target)
    assert target.exists() and target.stat().st_size > 0
    probe = sqlite3.connect(str(target))
    try:
        assert probe.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 1
    finally:
        probe.close()
    db.vacuum()
    assert db.integrity_check()[0]


def test_update_leave_does_not_touch_created_by(db):
    leave_id = db.add_leave("57454545", {"type": "اعتيادية", "start_date": "2026-07-01",
                                         "end_date": "2026-07-05", "days_actual": 5,
                                         "amount": 5, "unit": "يوم"}, "creator")
    db.update_leave(leave_id, {"type": "اعتيادية", "start_date": "2026-07-01",
                               "end_date": "2026-07-06", "days_actual": 6, "amount": 6,
                               "unit": "يوم"}, "editor")
    leave = db.get_leave(leave_id)
    assert leave.created_by == "creator"
    assert leave.modified_by == "editor"
