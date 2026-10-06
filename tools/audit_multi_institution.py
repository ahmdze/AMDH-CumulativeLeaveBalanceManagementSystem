"""إثبات عملي لدورة العمل الشهرية بين المركز والمؤسسات (على مجلدات مؤقتة فقط).

يحاكي السيناريو الذي طلبه المستخدم:
  * الشهر 9/2026: مستشفى 1 يرسل بيانات موظف (1001) وإجازاته.
  * الشهر 10/2026: الموظف نُقل إلى مستشفى 2 فأرسل بياناته وإجازاته الجديدة.
ويتحقّق من:
  1. إجازات المركز المعتمدة لموظف المستشفى **لا تُمحى** عند الاستيراد.
  2. إجازة حُذفت في المستشفى (حذف ناعم) تُحذف في المركز أيضاً.
  3. الموظف المنقول يبقى **سجلاً واحداً** برصيد واحد، ويُسجَّل انتقاله.
  4. المرفقات (ملفات الأوامر) تنتقل مع البيانات.
  5. إعادة استيراد الملف نفسه لا تُكرّر شيئاً.
  6. المستخدم المرتبط بالمؤسسة يرى موظفي مؤسسته فقط.

التشغيل:  python tools/audit_multi_institution.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amdh_leave.db import Database                             # noqa: E402
from amdh_leave.services import institutions as INST           # noqa: E402
from amdh_leave.services import merge as M                     # noqa: E402
from amdh_leave.services import security as sec                # noqa: E402
from amdh_leave.services import transfer as T                  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(title: str, passed: bool, detail: str = "") -> None:
    CHECKS.append((title, bool(passed), detail))
    mark = "✅" if passed else "❌"
    print(f"  {mark} {title}" + (f" — {detail}" if detail else ""))


def add_employee(db: Database, emp_id: str, institution: str, name: str,
                 start: str = "2015-01-01") -> None:
    db.add_employee(emp_id, {"name": name, "institution": institution,
                             "start_date": start, "job_title": "ممرض"}, "admin")


def add_leave(db: Database, emp_id: str, kind: str, start: str, days: int, order: str,
              uid: str = "", end: str = "") -> int:
    return db.add_leave(emp_id, {"type": kind, "start_date": start, "end_date": end or start,
                                 "amount": days, "unit": "يوم", "days_actual": days,
                                 "working_days": days, "order": order, "status": "approved",
                                 "uid": uid}, "admin")


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="amdh_cycle_"))
    print("=" * 78)
    print("محاكاة الدورة الشهرية: مركز الدائرة + ثلاث مؤسسات")
    print(f"مجلد العمل المؤقت: {root}")
    print("=" * 78)

    # ------------------------------------------------------------------
    # 1) المركز: موظف مستشفى 1 + إجازة سجّلها المركز + إجازة من المستشفى
    # ------------------------------------------------------------------
    center = Database(root / "center.db", root / "center_backups")
    center.set_meta({"days_per_leave": "10"})
    center.save_institution({"name": "مركز الدائرة", "code": "C0", "kind": "مركز الدائرة"},
                            "admin")
    center.set_center_institution("مركز الدائرة")
    for name, code in (("مستشفى 1", "H1"), ("مستشفى 2", "H2"), ("مركز صحي 3", "PH3")):
        center.save_institution({"name": name, "code": code}, "admin")

    add_employee(center, "1001", "مستشفى 1", "أحمد زياد")
    add_leave(center, "1001", "عادية", "2026-02-01", 10, "H1-1")
    center_leave = add_leave(center, "1001", "اضطرارية", "2026-04-01", 3, "CENTER-9")
    print("\n[قبل الاستيراد] المركز: موظف واحد، إجازتان "
          f"(منها إجازة سجّلها المركز #{center_leave})")

    # ------------------------------------------------------------------
    # 2) الشهر 9: نسخة مستشفى 1 (تسلّمها المركز عبر ملف نقل) ترسل للمركز
    # ------------------------------------------------------------------
    h1_dir = root / "h1"
    h1_dir.mkdir()
    # نسخة المستشفى تُنشأ عبر واجهة النسخ في SQLite (لا نسخ ملف مباشر، حتى لا تضيع
    # المعاملات الموجودة في ملف -wal)
    handed = T.export_transfer(center, h1_dir / "employees_leave.db", user="admin",
                               include_attachments=False,
                               attachments_dir=root / "center_attachments")
    hospital1 = Database(Path(handed["path"]), h1_dir / "backups")
    add_leave(hospital1, "1001", "مرضية", "2026-08-10", 4, "H1-77", end="2026-08-13")
    month9 = T.export_transfer(hospital1, root / "month9_h1.amdhz", institution="مستشفى 1",
                               user="h1", attachments_dir=h1_dir / "attachments")
    report9 = T.apply_transfer(center, Path(month9["path"]), user="admin",
                               attachments_dir=root / "center_attachments")
    print(f"\n[الشهر 9] استوردنا ملف مستشفى 1: أُضيفت {report9.leaves_added} إجازة، "
          f"حُدِّثت {report9.leaves_updated}")

    # ------------------------------------------------------------------
    # 3) الشهر 10: الموظف نُقل إلى مستشفى 2 فأرسل بياناته الجديدة
    # ------------------------------------------------------------------
    h2_dir = root / "h2"
    h2_dir.mkdir()
    handed2 = T.export_transfer(center, h2_dir / "employees_leave.db", user="admin",
                                include_attachments=False,
                                attachments_dir=root / "center_attachments")
    hospital2 = Database(Path(handed2["path"]), h2_dir / "backups")
    hospital2.set_employee_institution("1001", "مستشفى 2", moved_on="2026-10-01", user="h2")
    hospital2.soft_delete_leave(add_leave(hospital2, "1001", "عادية", "2026-06-01", 10,
                                          "H2-ERR"), "h2", "خطأ إدخال")
    new_leave = add_leave(hospital2, "1001", "عادية", "2026-09-20", 10, "H2-5",
                          end="2026-09-29")
    attachment_dir = h2_dir / "attachments"
    attachment_dir.mkdir()
    (attachment_dir / "order.pdf").write_bytes(b"%PDF-1.4 order of hospital 2")
    hospital2.add_attachment(new_leave, "1001", "أمر الإجازة.pdf", "order.pdf", "h2",
                             attachments_dir=attachment_dir)
    month10 = T.export_transfer(hospital2, root / "month10_h2.amdhz", institution="مستشفى 2",
                                user="h2", attachments_dir=attachment_dir)

    _plan, preview, _info = T.preview_transfer(center, Path(month10["path"]))
    print("\n[الشهر 10] معاينة ملف مستشفى 2 (بلا أي كتابة):")
    for line in preview.summary_lines():
        print("   " + line)
    report10 = T.apply_transfer(center, Path(month10["path"]), user="admin",
                                attachments_dir=root / "center_attachments")

    # ------------------------------------------------------------------
    # 4) التحقّق
    # ------------------------------------------------------------------
    print("\n" + "=" * 78)
    print("نتائج التحقّق")
    print("=" * 78)
    employees = center.list_employees()
    leaves = center.list_leaves("1001")
    all_leaves = center.list_leaves("1001", include_deleted=True)
    moves = center.list_moves("1001")
    attachments = center.raw_attachments()

    check("إجازة المركز المعتمدة لم تُمحَ بالاستيراد",
          center.get_leave(center_leave) is not None
          and not center.get_leave(center_leave).deleted_at,
          f"الإجازة #{center_leave} ما زالت موجودة وفعّالة")
    check("الموظف المنقول بقي سجلاً واحداً (لا تكرار)",
          len(employees) == 1 and employees[0].institution == "مستشفى 2",
          f"عدد الموظفين={len(employees)} | المؤسسة الحالية={employees[0].institution}")
    check("سُجِّل انتقال الموظف بين المؤسستين",
          len(moves) == 1 and moves[0].from_institution == "مستشفى 1"
          and moves[0].to_institution == "مستشفى 2",
          f"{moves[0].from_institution} ← {moves[0].to_institution} بتاريخ {moves[0].moved_on}")
    check("الحذف الناعم في المستشفى انتقل إلى المركز",
          len(all_leaves) == len(leaves) + 1
          and any(leave.deleted_at for leave in all_leaves),
          f"الفعّالة={len(leaves)} | المحذوفة={len(all_leaves) - len(leaves)}")
    check("إجازات الفترة السابقة باقية (لا حذف إطلاقاً)",
          len(all_leaves) >= 5, f"إجمالي الإجازات في سجل الموظف={len(all_leaves)}")
    check("المرفق انتقل مع بيانات المستشفى الثاني",
          len(attachments) == 1 and attachments[0]["sha256"],
          f"عدد المرفقات={len(attachments)} | بصمة={str(attachments[0]['sha256'])[:12]}…")
    check("تاريخ آخر استيراد محفوظ لكل مؤسسة",
          bool(center.get_institution("مستشفى 1").last_import_at)
          and bool(center.get_institution("مستشفى 2").last_import_at),
          f"مستشفى 1: {center.get_institution('مستشفى 1').last_import_at} | "
          f"مستشفى 2: {center.get_institution('مستشفى 2').last_import_at}")

    again = T.apply_transfer(center, Path(month10["path"]), user="admin",
                             attachments_dir=root / "center_attachments")
    check("إعادة استيراد الملف نفسه لا تُكرّر البيانات",
          again.employees_added == 0 and again.leaves_added == 0
          and len(center.list_employees()) == 1,
          f"أُضيف {again.leaves_added} إجازة، وبلا تغيير {again.leaves_unchanged}")

    # مستخدم مؤسسة: يرى موظفي مؤسسته فقط
    institution = center.get_institution("مستشفى 2")
    account, password = INST.create_user_for_institution(center, institution, user="admin")
    from PyQt6.QtCore import QSettings

    from amdh_leave.context import AppContext
    from amdh_leave.services.backup import BackupService
    add_employee(center, "2002", "مركز صحي 3", "موظف مؤسسة أخرى")
    ctx = AppContext(paths=None, db=center, backup=BackupService(center, root / "b"),
                     session=sec.make_session(account, False),
                     settings=QSettings("MyCompany", "AMDH-Audit"))
    visible = [employee.emp_id for employee in ctx.employees()]
    check("المستخدم المرتبط يرى موظفي مؤسسته فقط",
          visible == ["1001"] and account.institution == "مستشفى 2",
          f"المستخدم {account.username} يرى {visible}")

    pending = INST.pending_institutions(center)
    check("متابعة الإرسال الشهري تعمل",
          isinstance(pending, list),
          "المؤسسات التي لم تُرسل هذا الشهر: "
          + ("، ".join(item["name"] for item in pending) or "لا شيء"))

    records = center.list_imports(limit=10, direction="import")
    check("تقارير الاستيراد محفوظة وقابلة للاسترجاع",
          len(records) >= 3 and bool(records[0].report),
          f"عدد سجلات الاستيراد={len(records)} | آخر تقرير يحوي "
          f"{len(M.MergeReport.from_json(records[0].report).conflict_list)} تعارضاً")

    report_path = M.export_report_excel(root / "تقرير_الشهر10.xlsx", report10)
    check("تصدير تقرير الاستيراد إلى Excel",
          report_path.exists() and report_path.stat().st_size > 0,
          f"{report_path.name} ({report_path.stat().st_size:,} بايت)")

    # المركز يسجّل إجازة بصفته الجهة الأعلى، ثم يوزّع المحدث على المؤسسة (الاتجاه الثاني)
    center_extra = add_leave(center, "1001", "اضطرارية", "2026-10-02", 2, "CENTER-11")
    back = T.export_transfer(center, root / "center_to_h2.amdhz", institution="مستشفى 2",
                             user="admin", attachments_dir=root / "center_attachments")
    hospital2.close()
    hospital2 = Database(h2_dir / "employees_leave.db", h2_dir / "backups")
    back_report = T.apply_transfer(hospital2, Path(back["path"]), user="h2",
                                   attachments_dir=attachment_dir)
    hospital2_leaves = {leave.type for leave in hospital2.list_leaves("1001")}
    check("الاتجاه الثاني (المركز ← المؤسسة) يعمل",
          back_report.leaves_added >= 1 and center_extra in [
              leave.id for leave in hospital2.list_leaves("1001")],
          f"وصلت {back_report.leaves_added} إجازة جديدة للمؤسسة، وترى الآن الأنواع: "
          f"{'، '.join(sorted(hospital2_leaves))}")

    failed = [title for title, passed, _detail in CHECKS if not passed]
    print("\n" + "=" * 78)
    print(f"النتيجة: {len(CHECKS) - len(failed)}/{len(CHECKS)} فحصاً ناجحاً")
    for title in failed:
        print(f"   ❌ فشل: {title}")
    print("=" * 78)
    print(f"\nالمسار الكامل: {root}")
    print(f"كلمة مرور المستخدم {account.username}: {password}")
    center.close()
    hospital1.close()
    hospital2.close()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
