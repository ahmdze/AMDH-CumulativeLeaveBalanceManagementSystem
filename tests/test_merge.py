"""اختبارات محرّك الدمج: الهوية بالرقم الوظيفي، نقل الحذف، المرفقات، والتنقّل بين المؤسسات.

الحالة المحورية (طلب المستخدم): موظف في مستشفى 1 أرسل بياناته في الشهر 9، ثم نُقل إلى
مستشفى 2 فأرسل بياناته في الشهر 10 — يجب أن يبقى موظفاً واحداً برصيد واحد، وأن تبقى
إجازات المركز وإجازات المستشفى الأول، وأن يُسجَّل الانتقال.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from amdh_leave.db import Database
from amdh_leave.services import institutions as INST
from amdh_leave.services import merge as M
from amdh_leave.services import transfer as T


# ---------------------------------------------------------------------------
# أدوات
# ---------------------------------------------------------------------------
def new_db(tmp_path: Path, name: str = "center.db") -> Database:
    return Database(tmp_path / name, tmp_path / f"backups_{name}")


def attachments_dir(tmp_path: Path, name: str = "center.db") -> Path:
    directory = tmp_path / f"attachments_{Path(name).stem}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def add_employee(db: Database, emp_id: str = "1001", institution: str = "مستشفى 1",
                 name: str = "أحمد علي", start: str = "2015-01-01", **extra) -> None:
    fields = {"name": name, "institution": institution, "start_date": start,
              "job_title": "ممرض", "workplace": "الردهة", "gender": "ذكر"}
    fields.update(extra)
    db.add_employee(emp_id, fields, "admin")


def add_leave(db: Database, emp_id: str = "1001", kind: str = "عادية",
              start: str = "2026-03-01", days: int = 10, order: str = "100",
              uid: str = "", **extra) -> int:
    fields = {"type": kind, "start_date": start, "end_date": start, "amount": days,
              "unit": "يوم", "days_actual": days, "working_days": days,
              "order": order, "status": "approved"}
    fields.update(extra)
    if uid:
        fields["uid"] = uid
    return db.add_leave(emp_id, fields, "admin")


def export(db: Database, tmp_path: Path, name: str, institution: str = "",
           include_attachments: bool = True, user: str = "admin") -> Path:
    destination = tmp_path / name
    manifest = T.export_transfer(db, destination, institution=institution, user=user,
                                 include_attachments=include_attachments,
                                 attachments_dir=attachments_dir(tmp_path, db.path.name))
    return Path(manifest["path"])


# ---------------------------------------------------------------------------
# الحالة المحورية: تنقّل الموظف بين مؤسستين
# ---------------------------------------------------------------------------
def test_transferred_employee_stays_one_record_with_all_leaves(tmp_path):
    center = new_db(tmp_path, "center.db")
    add_employee(center, "1001", "مستشفى 1")
    first = add_leave(center, "1001", "عادية", "2026-02-01", 10, order="H1-1")
    entered_at_center = add_leave(center, "1001", "اضطرارية", "2026-04-01", 3, order="C-9")

    # المستشفى الثاني: نسخة من بيانات المركز ثم نقل الموظف إليه وإضافة إجازة جديدة
    hospital_path = tmp_path / "h2.db"
    T.export_transfer(center, hospital_path, user="admin",
                      attachments_dir=attachments_dir(tmp_path, "center.db"))
    hospital = Database(tmp_path / "h2.db", tmp_path / "backups_h2")
    hospital.set_employee_institution("1001", "مستشفى 2", moved_on="2026-10-01", user="h2")
    hospital_leave = add_leave(hospital, "1001", "مرضية", "2026-09-15", 5, order="H2-7")

    transfer_file = export(hospital, tmp_path, "h2_transfer.amdhz", institution="مستشفى 2",
                           user="h2")
    plan, report, _info = T.preview_transfer(center, transfer_file)

    assert report.moves == 1, "يجب كشف انتقال الموظف بين المؤسستين"
    assert plan.moves[0]["from_institution"] == "مستشفى 1"
    assert plan.moves[0]["to_institution"] == "مستشفى 2"
    assert report.leaves_added == 1 and report.leaves_updated == 0

    final = T.apply_transfer(center, transfer_file, user="admin",
                             attachments_dir=attachments_dir(tmp_path, "center.db"))
    assert final.leaves_added == 1 and final.moves == 1

    # موظف واحد فقط (لا تكرار بعد النقل)
    employees = center.list_employees()
    assert len(employees) == 1
    assert employees[0].institution == "مستشفى 2"
    assert employees[0].previous_institution == "مستشفى 1"
    assert str(employees[0].moved_on) == "2026-10-01"

    # كل الإجازات باقية: إجازة المستشفى الأول + إجازة المركز + إجازة المستشفى الثاني
    leaves = center.list_leaves("1001")
    assert len(leaves) == 3
    assert {leave.type for leave in leaves} == {"عادية", "اضطرارية", "مرضية"}
    assert first in [leave.id for leave in leaves]
    assert entered_at_center in [leave.id for leave in leaves]
    assert hospital_leave in [leave.id for leave in leaves]

    # سجل الانتقال محفوظ
    moves = center.list_moves("1001")
    assert len(moves) == 1 and moves[0].to_institution == "مستشفى 2"

    # التقرير محفوظ ويمكن استرجاعه
    record = center.last_import_for("مستشفى 2")
    assert record is not None and record.employees_updated == 1
    saved = M.MergeReport.from_json(record.report)
    assert saved.moves == 1 and saved.leaves_added == 1
    assert center.get_institution("مستشفى 2").last_import_at
    center.close()
    hospital.close()


def test_center_entered_leave_is_not_deleted_by_import(tmp_path):
    """كان الدمج القديم يحذف إجازات المركز — الآن لا يُحذف شيء إطلاقاً."""
    center = new_db(tmp_path, "center.db")
    add_employee(center, "2002", "مستشفى 3")
    center_leave = add_leave(center, "2002", "عادية", "2026-05-01", 10, order="C-1")
    hospital_leave = add_leave(center, "2002", "مرضية", "2026-06-01", 4, order="H-2")

    hospital = new_db(tmp_path, "h3.db")
    add_employee(hospital, "2002", "مستشفى 3")
    add_leave(hospital, "2002", "مرضية", "2026-06-01", 4, order="H-2")
    transfer_file = export(hospital, tmp_path, "h3.amdhz", institution="مستشفى 3", user="h3")

    result = T.apply_transfer(center, transfer_file, user="admin",
                              attachments_dir=attachments_dir(tmp_path, "center.db"))
    assert result.leaves_added == 0 and result.leaves_updated == 0
    leaves = center.list_leaves("2002")
    assert {leave.id for leave in leaves} == {center_leave, hospital_leave}
    center.close()
    hospital.close()


def test_soft_deleted_leave_propagates_to_center(tmp_path):
    center = new_db(tmp_path, "center.db")
    add_employee(center, "3003", "مستشفى 4")
    shared_uid = "uid-shared-1"
    add_leave(center, "3003", "عادية", "2026-07-01", 10, order="S-1", uid=shared_uid)

    hospital = new_db(tmp_path, "h4.db")
    add_employee(hospital, "3003", "مستشفى 4")
    leave_id = add_leave(hospital, "3003", "عادية", "2026-07-01", 10, order="S-1", uid=shared_uid)
    hospital.soft_delete_leave(leave_id, "h4", "خطأ إدخال")

    transfer_file = export(hospital, tmp_path, "h4.amdhz", institution="مستشفى 4", user="h4")
    plan, report, _info = T.preview_transfer(center, transfer_file)
    assert report.leaves_updated == 1
    assert any(item["kind"] == "soft_delete" for item in report.conflict_list)

    T.apply_transfer(center, transfer_file, user="admin",
                     attachments_dir=attachments_dir(tmp_path, "center.db"))
    active = center.list_leaves("3003")
    assert active == [], "الإجازة المحذوفة في المستشفى يجب أن تُحذف ناعماً في المركز"
    all_leaves = center.list_leaves("3003", include_deleted=True)
    assert len(all_leaves) == 1 and all_leaves[0].deleted_at
    center.close()
    hospital.close()


def test_merge_is_idempotent(tmp_path):
    center = new_db(tmp_path, "center.db")
    add_employee(center, "4004", "مستشفى 5")
    hospital = new_db(tmp_path, "h5.db")
    add_employee(hospital, "4004", "مستشفى 5")
    add_leave(hospital, "4004", "عادية", "2026-01-05", 10, order="A-1")
    transfer_file = export(hospital, tmp_path, "h5.amdhz", institution="مستشفى 5", user="h5")

    first = T.apply_transfer(center, transfer_file, user="admin",
                             attachments_dir=attachments_dir(tmp_path, "center.db"))
    assert first.leaves_added == 1
    second = T.apply_transfer(center, transfer_file, user="admin",
                              attachments_dir=attachments_dir(tmp_path, "center.db"))
    assert second.leaves_added == 0 and second.leaves_unchanged == 1
    assert second.employees_added == 0 and second.employees_unchanged == 1
    assert len(center.list_leaves("4004")) == 1, "لا تكرار عند إعادة الاستيراد"
    assert any("استُورد سابقاً" in warning for warning in second.warnings)
    center.close()
    hospital.close()


def test_attachments_travel_with_transfer(tmp_path):
    center = new_db(tmp_path, "center.db")
    add_employee(center, "5005", "مستشفى 6")
    hospital = new_db(tmp_path, "h6.db")
    add_employee(hospital, "5005", "مستشفى 6")
    leave_id = add_leave(hospital, "5005", "عادية", "2026-08-01", 10, order="F-1")

    source_dir = attachments_dir(tmp_path, "h6.db")
    (source_dir / "order.pdf").write_bytes(b"%PDF-1.4 fake order")
    hospital.add_attachment(leave_id, "5005", "أمر إجازة.pdf", "order.pdf", "h6",
                            attachments_dir=source_dir)

    transfer_file = export(hospital, tmp_path, "h6.amdhz", institution="مستشفى 6", user="h6")
    info = T.read_transfer_info(transfer_file)
    assert info["archive"] is True and info["attachment_files"] == 1

    target_dir = attachments_dir(tmp_path, "center.db")
    report = T.apply_transfer(center, transfer_file, user="admin", attachments_dir=target_dir)
    assert report.attachments_added == 1

    rows = center.raw_attachments()
    assert len(rows) == 1
    stored = rows[0]["stored_name"]
    assert (target_dir / stored).read_bytes() == b"%PDF-1.4 fake order"
    assert rows[0]["sha256"] and rows[0]["leave_uid"] == center.list_leaves("5005")[0].uid

    # إعادة الاستيراد لا تُكرّر المرفق
    again = T.apply_transfer(center, transfer_file, user="admin", attachments_dir=target_dir)
    assert again.attachments_added == 0 and again.attachments_skipped == 1
    assert len(center.raw_attachments()) == 1
    center.close()
    hospital.close()


def test_other_institution_guard_and_override(tmp_path):
    center = new_db(tmp_path, "center.db")
    add_employee(center, "6006", "مستشفى 7")
    center.register_institutions(["مستشفى 7", "مستشفى 8"], "admin")

    hospital = new_db(tmp_path, "h8.db")
    add_employee(hospital, "6006", "مستشفى 7")
    add_employee(hospital, "6007", "مستشفى 8")
    add_leave(hospital, "6007", "عادية", "2026-02-01", 10, order="X-1")
    # ملف يحتوي موظفين من مؤسستين (المستشفى صدّر كل بياناته)
    transfer_file = export(hospital, tmp_path, "h8.amdhz", user="h8")

    declared = M.MergeOptions(institution="مستشفى 8")
    plan, report, _info = T.preview_transfer(center, transfer_file, declared)
    assert report.employees_skipped == 1
    assert plan.employees_skipped[0]["emp_id"] == "6006"

    allowed = M.MergeOptions(institution="مستشفى 8", allow_other_institutions=True)
    plan2, report2, _info = T.preview_transfer(center, transfer_file, allowed)
    assert report2.employees_skipped == 0
    assert {record["emp_id"] for record in plan2.employees_add} == {"6007"}
    assert report2.employees_unchanged == 1, "موظف مستشفى 7 موجود ومطابق ⇒ بلا تغيير"
    assert report2.moves == 0
    center.close()
    hospital.close()


def test_conflict_keeps_newest_and_reports_it(tmp_path):
    center = new_db(tmp_path, "center.db")
    add_employee(center, "7007", "مستشفى 9")
    uid = "uid-conflict"
    leave_id = add_leave(center, "7007", "عادية", "2026-03-01", 10, order="K-1", uid=uid,
                         modified_at="2026-09-01 10:00:00")

    hospital = new_db(tmp_path, "h9.db")
    add_employee(hospital, "7007", "مستشفى 9")
    add_leave(hospital, "7007", "عادية", "2026-03-01", 7, order="K-1", uid=uid,
              modified_at="2026-08-01 10:00:00")
    transfer_file = export(hospital, tmp_path, "h9.amdhz", institution="مستشفى 9", user="h9")

    plan, report, _info = T.preview_transfer(center, transfer_file)
    assert report.conflicts == 1
    assert report.conflict_list[0]["winner"].startswith("المركز")
    T.apply_transfer(center, transfer_file, user="admin",
                     attachments_dir=attachments_dir(tmp_path, "center.db"))
    assert center.get_leave(leave_id).days_actual == 10, "الأحدث (المركز) هو الذي يُعتمد"

    # وبالعكس: تعديل أحدث في المستشفى يفوز
    hospital.update_leave(add_leave(hospital, "7007", "عادية", "2026-03-01", 7, order="K-1",
                                    uid=uid),
                          {"type": "عادية", "start_date": "2026-03-01", "end_date": "2026-03-10",
                           "days_actual": 4, "order": "K-1", "modified_at": "2026-10-05 10:00:00"})
    transfer_file2 = export(hospital, tmp_path, "h9b.amdhz", institution="مستشفى 9", user="h9")
    report2 = T.apply_transfer(center, transfer_file2, user="admin",
                               attachments_dir=attachments_dir(tmp_path, "center.db"))
    assert report2.leaves_updated == 1
    assert center.get_leave(leave_id).days_actual == 4
    center.close()
    hospital.close()


def test_policy_mismatch_warns(tmp_path):
    center = new_db(tmp_path, "center.db")
    add_employee(center, "8008", "مستشفى 10")
    hospital = new_db(tmp_path, "h10.db")
    add_employee(hospital, "8008", "مستشفى 10")
    hospital.set_meta({"days_per_leave": "20"})          # ضوابط مختلفة
    transfer_file = export(hospital, tmp_path, "h10.amdhz", institution="مستشفى 10", user="h10")

    _plan, report, _info = T.preview_transfer(center, transfer_file)
    assert any("ضوابط الاحتساب" in warning for warning in report.warnings)
    center.close()
    hospital.close()


def test_overlap_is_detected(tmp_path):
    center = new_db(tmp_path, "center.db")
    add_employee(center, "9009", "مستشفى 11")
    add_leave(center, "9009", "عادية", "2026-03-01", 10, order="O-1",
              end_date="2026-03-10")
    hospital = new_db(tmp_path, "h11.db")
    add_employee(hospital, "9009", "مستشفى 11")
    add_leave(hospital, "9009", "مرضية", "2026-03-05", 5, order="O-2", end_date="2026-03-09")
    transfer_file = export(hospital, tmp_path, "h11.amdhz", institution="مستشفى 11", user="h11")

    _plan, report, _info = T.preview_transfer(center, transfer_file)
    assert len(report.overlap_list) == 1
    assert report.overlap_list[0]["new_type"] == "مرضية"
    center.close()
    hospital.close()


def test_legacy_source_without_uid_is_not_duplicated(tmp_path):
    """نسخة قديمة بلا uid: يُكشف التكرار بمطابقة النوع والتاريخ والأمر."""
    center = new_db(tmp_path, "center.db")
    add_employee(center, "1100", "مستشفى 12")
    add_leave(center, "1100", "عادية", "2026-01-05", 10, order="L-1")

    hospital = new_db(tmp_path, "h12.db")
    add_employee(hospital, "1100", "مستشفى 12")
    add_leave(hospital, "1100", "عادية", "2026-01-05", 10, order="L-1")
    hospital.conn.execute("UPDATE leaves SET uid=NULL")     # محاكاة نسخة قديمة
    hospital.conn.commit()

    transfer_file = export(hospital, tmp_path, "h12.amdhz", institution="مستشفى 12", user="h12")
    report = T.apply_transfer(center, transfer_file, user="admin",
                              attachments_dir=attachments_dir(tmp_path, "center.db"))
    assert report.leaves_added == 0
    assert len(center.list_leaves("1100")) == 1
    assert any(item["kind"] == "duplicate_leave" for item in report.conflict_list)
    center.close()
    hospital.close()


# ---------------------------------------------------------------------------
# ملف النقل: التنقية والمحتوى
# ---------------------------------------------------------------------------
def test_transfer_file_is_sanitized(tmp_path):
    center = new_db(tmp_path, "center.db")
    add_employee(center, "1200", "مستشفى 13")
    add_leave(center, "1200", "عادية", "2026-01-05", 10, order="S-1")
    center.log("admin", "اختبار", "employee", "1200", "")
    transfer_file = export(center, tmp_path, "clean.db", institution="مستشفى 13")

    import sqlite3
    connection = sqlite3.connect(str(transfer_file))
    try:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "app_users" in tables and "audit_log" in tables
        users = connection.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]
        audit = connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        assert users == 0, "لا تُصدَّر حسابات المستخدمين (بصمات كلمات المرور)"
        assert audit == 0, "لا يُصدَّر سجل التدقيق"
        imports = connection.execute("SELECT COUNT(*) FROM imports").fetchone()[0]
        assert imports == 0
        auth = connection.execute("SELECT value FROM app_meta WHERE key='auth_enabled'").fetchone()
        assert auth is not None and auth[0] == "0", "لا يُقفل الملف إن فُتح مباشرة"
        assert "transfer_manifest" in tables
    finally:
        connection.close()
    center.close()


def test_transfer_export_filters_by_institution(tmp_path):
    center = new_db(tmp_path, "center.db")
    add_employee(center, "1300", "مستشفى 14")
    add_employee(center, "1301", "مستشفى 15")
    add_leave(center, "1300", "عادية", "2026-01-05", 10, order="A")
    add_leave(center, "1301", "عادية", "2026-02-05", 10, order="B")
    transfer_file = export(center, tmp_path, "h14.db", institution="مستشفى 14")

    info = T.read_transfer_info(transfer_file)
    assert info["manifest"]["institution"] == "مستشفى 14"
    with T.prepare_source(transfer_file) as prepared:
        only = Database(prepared.db_path)
        assert [employee.emp_id for employee in only.list_employees()] == ["1300"]
        assert [leave.emp_id for leave in only.all_leaves()] == ["1300"]
        only.close()
    center.close()


def test_two_way_center_to_hospital(tmp_path):
    """المركز يصدّر لمؤسسة، والمؤسسة تستورد (الاتجاه الثاني)."""
    center = new_db(tmp_path, "center.db")
    add_employee(center, "1400", "مستشفى 16")
    add_leave(center, "1400", "عادية", "2026-04-01", 10, order="C-5")
    add_leave(center, "1400", "اضطرارية", "2026-05-01", 3, order="C-6")

    hospital = new_db(tmp_path, "h16.db")
    add_employee(hospital, "1400", "مستشفى 16")
    add_leave(hospital, "1400", "مرضية", "2026-06-01", 2, order="H-1")

    center_file = export(center, tmp_path, "center_to_h16.db", institution="مستشفى 16")
    report = T.apply_transfer(hospital, center_file, user="h16",
                              attachments_dir=attachments_dir(tmp_path, "h16.db"))
    assert report.leaves_added == 2
    kinds = {leave.type for leave in hospital.list_leaves("1400")}
    assert kinds == {"عادية", "اضطرارية", "مرضية"}, "المؤسسة تحصل على كل التاريخ"
    center.close()
    hospital.close()


def test_monthly_cycle_three_institutions(tmp_path):
    """دورة شهرية كاملة: ثلاث مؤسسات ترسل، والمركز يدمج، ثم يوزّع المحدث."""
    center = new_db(tmp_path, "center.db")
    center.set_center_institution("مركز الدائرة")
    center.register_institutions(["مركز الدائرة", "مستشفى أ", "مستشفى ب", "مركز صحي ج"], "admin")
    add_employee(center, "2001", "مركز الدائرة", name="موظف المركز", start="2010-01-01")

    reports = []
    for index, institution in enumerate(["مستشفى أ", "مستشفى ب", "مركز صحي ج"], start=1):
        hospital = new_db(tmp_path, f"h{index}.db")
        emp_id = f"3{index:03d}"
        add_employee(hospital, emp_id, institution, name=f"موظف {institution}",
                     start="2016-05-01")
        add_leave(hospital, emp_id, "عادية", f"2026-0{index}-10", 10, order=f"{index}-1")
        file = export(hospital, tmp_path, f"h{index}.amdhz", institution=institution,
                      user=institution)
        reports.append(T.apply_transfer(center, file, user="admin",
                                        attachments_dir=attachments_dir(tmp_path, "center.db")))
        hospital.close()

    assert [report.leaves_added for report in reports] == [1, 1, 1]
    assert len(center.list_employees()) == 4
    status = {row["name"]: row for row in INST.institutions_status(center)}
    for institution in ["مستشفى أ", "مستشفى ب", "مركز صحي ج"]:
        assert status[institution]["reported_this_month"] is True, institution
    assert INST.pending_institutions(center, "2000-01"), "شهر قديم: الكل لم يُرسل"
    assert center.center_institution() == "مركز الدائرة"
    center.close()


def test_report_export_rows(tmp_path):
    """التقرير قابل للتصدير إلى Excel (ملخص + تفاصيل)."""
    center = new_db(tmp_path, "center.db")
    add_employee(center, "1500", "مستشفى 17")
    hospital = new_db(tmp_path, "h17.db")
    add_employee(hospital, "1500", "مستشفى 17")
    add_leave(hospital, "1500", "عادية", "2026-07-01", 10, order="R-1")
    transfer_file = export(hospital, tmp_path, "h17.amdhz", institution="مستشفى 17", user="h17")
    report = T.apply_transfer(center, transfer_file, user="admin",
                              attachments_dir=attachments_dir(tmp_path, "center.db"))
    output = M.export_report_excel(tmp_path / "report.xlsx", report)
    assert output.exists() and output.stat().st_size > 0
    center.close()
    hospital.close()
