"""تدقيق أمان طريقة العمل الموزّعة (مركز + مؤسسات) — أدلة فعلية على سلوك الدمج.

يحاكي: قاعدة مركز فيها مركز الدائرة، وقواعد مستشفيات، ثم يدمج نسخة مستشفى في المركز
ويقيس ما يحدث فعلاً للبيانات. كل ذلك في مجلد مؤقت (لا يمسّ بيانات المستخدم).
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amdh_leave.db import Database                              # noqa: E402
from amdh_leave.services.backup import BackupService            # noqa: E402
from tests.conftest import create_legacy_db                     # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="amdh_audit_"))
REPORT: list[str] = []


def say(line: str = "") -> None:
    REPORT.append(line)
    print(line)


def make_center() -> Database:
    path = TMP / "center" / "employees_leave.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    create_legacy_db(path)
    db = Database(path, path.parent / "backups")
    # إجازة أضافها المركز لموظف المستشفى (اعتماد مركزي)
    leave_id = db.add_leave("57454545", {
        "type": "طويلة", "start_date": "2026-09-01", "end_date": "2026-09-10",
        "amount": 10, "unit": "يوم", "days_actual": 10, "order": "CENTER-1",
        "reason": "اعتماد مركزي", "added_date": "2026-09-01"}, "admin")
    # مرفق في المركز على الإجازة المركزية (لقياس اليُتم بعد الدمج)
    db.add_attachment(leave_id, "57454545", "اعتماد-مركزي.pdf", "center-stored.pdf", "admin")
    return db


def make_hospital() -> Path:
    path = TMP / "hospital" / "employees_leave.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    create_legacy_db(path)
    db = Database(path, path.parent / "backups")
    # إجازة اعتيادية جديدة أدخلها المستشفى
    leave_id = db.add_leave("57454545", {
        "type": "اعتيادية", "start_date": "2026-10-01", "end_date": "2026-10-03",
        "amount": 3, "unit": "يوم", "days_actual": 3, "order": "HOSP-9",
        "reason": "", "added_date": "2026-10-01"}, "hospital")
    # إجازة أُدخلت بالخطأ ثم حُذفت (حذف ناعم في نسخة المستشفى)
    wrong = db.add_leave("57454545", {
        "type": "مرضية", "start_date": "2026-10-20", "end_date": "2026-10-21",
        "amount": 2, "unit": "يوم", "days_actual": 2, "order": "HOSP-ERR",
        "reason": "خطأ إدخال", "added_date": "2026-10-20"}, "hospital")
    db.soft_delete_leave(wrong, "hospital", "خطأ إدخال")
    # موظف جديد للمستشفى
    db.add_employee("H-100", {"name": "موظف المستشفى", "job_title": "ممرض",
                              "workplace": "مستشفى أ", "institution": "مستشفى أ",
                              "gender": "ذكر", "start_date": "2022-01-01"}, "hospital")
    # موظف بترقيم متعارض مع موظف مؤسسة أخرى (نفس الرقم لشخص مختلف)
    db.add_employee("SHARED-1", {"name": "شخص من مستشفى أ", "job_title": "إداري",
                                 "institution": "مستشفى أ", "gender": "ذكر",
                                 "start_date": "2023-01-01"}, "hospital")
    db.add_attachment(leave_id, "57454545", "أمر.pdf", "stored.pdf", "hospital")
    db.close()
    return path


def main() -> int:
    say("=" * 78)
    say("تدقيق الدمج: مركز الدائرة ← نسخة مستشفى")
    say("=" * 78)

    center = make_center()
    hospital_path = make_hospital()

    before = {leave.id: leave for leave in center.list_leaves("57454545")}
    say(f"\n[المركز قبل الدمج] إجازات الموظف 57454545: {len(before)}")
    for leave in before.values():
        say(f"   #{leave.id} {leave.type} {leave.start_date} أيام={leave.days_actual} "
            f"أمر={leave.order}")

    # موظف بنفس الترقيم لكن مؤسسة أخرى موجودة في المركز (تعارض ترقيم)
    center.add_employee("SHARED-1", {"name": "شخص من مؤسسة أخرى", "job_title": "محاسب",
                                     "institution": "مؤسسة ب", "gender": "أنثى",
                                     "start_date": "2020-05-05"}, "admin")
    center.add_leave("SHARED-1", {"type": "اعتيادية", "start_date": "2026-06-01",
                                  "end_date": "2026-06-05", "amount": 5, "unit": "يوم",
                                  "days_actual": 5, "order": "B-77"}, "admin")
    shared_before = center.get_employee("SHARED-1")
    say(f"\n[المركز قبل الدمج] الموظف SHARED-1: {shared_before.name} / "
        f"{shared_before.institution} / إجازات={len(shared_before.leaves)}")

    service = BackupService(center, center.backup_dir)
    service.import_mode = "update"
    result = service.import_merge(hospital_path, "admin")
    say(f"\n[نتيجة الدمج] {result}")

    after = {leave.id: leave for leave in center.list_leaves("57454545")}
    say(f"\n[المركز بعد الدمج] إجازات الموظف 57454545: {len(after)}")
    for leave in after.values():
        say(f"   #{leave.id} {leave.type} {leave.start_date} أيام={leave.days_actual} "
            f"أمر={leave.order} محذوف={'نعم' if leave.is_deleted else 'لا'}")
    kept_ids = set(before) & set(after)
    say(f"\n   ▸ إجازات المركز التي بقيت بنفس المعرّف: {len(kept_ids)}")
    say(f"   ▸ هل بقيت الإجازة المركزية (CENTER-1)؟ "
        f"{'نعم' if any(l.order == 'CENTER-1' for l in after.values()) else 'لا — حُذفت'}")
    say(f"   ▸ هل «عادات» الإجازة المحذوفة في المستشفى (HOSP-ERR)؟ "
        f"{'نعم — عادت كإجازة فعّالة' if any(l.order == 'HOSP-ERR' and not l.is_deleted for l in after.values()) else 'لا'}")

    shared_after = center.get_employee("SHARED-1")
    say(f"\n[تعارض الترقيم] SHARED-1 بعد الدمج: {shared_after.name} / "
        f"{shared_after.institution} / إجازات={[l.order for l in shared_after.leaves]}")
    say(f"   ▸ الاسم تغيّر؟ {'نعم — استُبدل ببيانات المستشفى' if shared_after.name != shared_before.name else 'لا'}")

    orphans = center.conn.execute(
        "SELECT COUNT(*) FROM attachments WHERE leave_id NOT IN (SELECT id FROM leaves)"
    ).fetchone()[0]
    total_attachments = center.conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
    say(f"\n[المرفقات] الإجمالي={total_attachments} | يتيمة (بلا إجازة موجودة)={orphans}")

    say(f"\n[سجل التدقيق] عدد السجلات={center.stats()['audit']} | "
        f"سجلات الاستيراد={len(center.list_audit(action='استيراد'))}")
    say(f"[النسخ الاحتياطية] {len(service.list_backups())} نسخة "
        f"(منها pre_import={len(list(center.backup_dir.glob('*pre_import*')))})")
    say(f"[إصدار المخطط في نسخة المستشفى] "
        f"{Database(hospital_path, TMP / 'x' / 'b').schema_version}")

    center.close()
    say(f"\nمجلد التدقيق: {TMP}")
    (TMP / "audit_report.txt").write_text("\n".join(REPORT), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
