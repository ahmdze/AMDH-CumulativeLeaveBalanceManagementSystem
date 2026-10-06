"""النسخ الاحتياطي: إنشاء، دوران، استعادة، فحص سلامة."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from ..logging_setup import get_logger

LOG = get_logger("backup")


class BackupService:
    """إدارة النسخ الاحتياطية في مجلد backups مع دوران تلقائي."""

    def __init__(self, db, backups_dir: Path) -> None:
        self.db = db
        self.dir = Path(backups_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def create(self, kind: str = "manual") -> Path | None:
        """إنشاء نسخة متسقة (عبر واجهة SQLite) باسم فريد يحمل التاريخ والوقت والميكروثانية."""
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
        dest = self.dir / f"backup_{stamp}_{kind}.db"
        counter = 1
        while dest.exists():   # ضمان عدم الكتابة فوق نسخة سابقة
            dest = self.dir / f"backup_{stamp}_{kind}_{counter}.db"
            counter += 1
        try:
            self.db.backup_to(dest)
        except Exception as exc:  # pragma: no cover
            LOG.error("فشل إنشاء نسخة احتياطية: %s", exc)
            return None
        LOG.info("نسخة احتياطية: %s", dest.name)
        self.rotate()
        return dest

    def create_if_changed(self, kind: str = "auto") -> Path | None:
        """ينشئ نسخة عند الإقلاع/الإغلاق فقط إن تغيّرت قاعدة البيانات بعد آخر نسخة."""
        latest = self.latest()
        if latest is None:
            return self.create(kind)
        try:
            newest = 0.0
            # ملف WAL يتغيّر عند كل كتابة، لذا لا يكفي فحص الملف الرئيسي
            for suffix in ("", "-wal"):
                candidate = Path(str(self.db.path) + suffix)
                if candidate.exists():
                    newest = max(newest, candidate.stat().st_mtime)
            if newest <= latest.stat().st_mtime:
                return None
        except OSError:
            pass
        return self.create(kind)

    def latest(self) -> Path | None:
        files = self.list_backups()
        return Path(files[0]["path"]) if files else None

    def list_backups(self) -> list[dict]:
        items: list[dict] = []
        for path in sorted(self.dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                stat = path.stat()
            except OSError:
                continue
            kind = "auto"
            name = path.stem
            for token in ("pre_migration", "pre_restore", "pre_import", "manual", "auto", "exit", "start"):
                if token in name:
                    kind = token
                    break
            items.append({
                "path": str(path),
                "name": path.name,
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "kind": kind,
                "valid": self._is_valid(path),
            })
        return items

    @staticmethod
    def _is_valid(path: Path) -> bool:
        """يتحقق أن الملف قاعدة SQLite سليمة تحتوي جدول الموظفين."""
        try:
            probe = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                row = probe.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='employees'").fetchone()
                if not row:
                    return False
                return str(probe.execute("PRAGMA integrity_check").fetchone()[0]).lower() == "ok"
            finally:
                probe.close()
        except sqlite3.DatabaseError:
            return False

    def rotate(self, keep: int | None = None) -> int:
        """يحتفظ بأحدث (keep) نسخة ويحذف الأقدم. لا يحذف نسخ ما قبل الترحيل/الاستعادة الحديثة."""
        keep = int(keep or getattr(self.db, "backup_keep", 30) or 30)
        files = sorted(self.dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        removed = 0
        for path in files[keep:]:
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
        return removed

    # ------------------------------------------------------------------
    def restore(self, source: str | Path, safety_copy: bool = True) -> tuple[bool, str]:
        """استعادة قاعدة البيانات من ملف نسخة احتياطية."""
        source = Path(source)
        if not source.exists():
            return False, "الملف غير موجود"
        if not self._is_valid(source):
            return False, "الملف ليس قاعدة بيانات صالحة (فشل الفحص)"
        safety: Path | None = None
        try:
            if safety_copy and self.db.path.exists():
                stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                safety = self.dir / f"pre_restore_{stamp}.db"
                shutil.copy2(self.db.path, safety)
            self.db.close()
            for suffix in ("-wal", "-shm"):
                side = Path(str(self.db.path) + suffix)
                if side.exists():
                    side.unlink()
            shutil.copy2(source, self.db.path)
            self.db.open()
            self.db.invalidate_policy()
        except Exception as exc:  # pragma: no cover
            LOG.error("فشل الاستعادة: %s", exc)
            try:
                self.db.open()
            except Exception:
                pass
            return False, f"فشل الاستعادة: {exc}"
        LOG.warning("تمت الاستعادة من %s", source.name)
        note = f" (نسخة أمان: {safety.name})" if safety else ""
        return True, f"تمت الاستعادة من: {source.name}{note}"

    def import_merge(self, source: str | Path, user: str = "") -> dict:
        """(متوافقية) يفوّض الدمج إلى المحرّك الجديد غير المُدمّر.

        كان هذا الدمج يحذف إجازات الهدف ثم يُدخل إجازات المصدر فقط (فقدان بيانات المركز)،
        فاستُبدل بـ ``services.merge`` الذي لا يحذف شيئاً ويطابق بهوية ``uid``.
        """
        source = Path(source)
        result = {"added": 0, "updated": 0, "skipped": 0, "leaves": 0, "errors": []}
        if not source.exists():
            result["errors"].append("الملف غير موجود")
            return result
        from . import merge as M
        from . import transfer as T
        try:
            report = T.apply_transfer(self.db, source, M.MergeOptions(), user=user,
                                      attachments_dir=self.db.path.parent / "attachments")
        except Exception as exc:                          # noqa: BLE001
            result["errors"].append(str(exc))
            return result
        result.update({"added": report.employees_added, "updated": report.employees_updated,
                       "skipped": report.employees_skipped, "leaves": report.leaves_added,
                       "errors": list(report.warnings)})
        result["report"] = report
        return result
        try:
            src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
            src.row_factory = sqlite3.Row
        except sqlite3.DatabaseError as exc:
            result["errors"].append(f"تعذّر فتح الملف: {exc}")
            return result
        try:
            tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "employees" not in tables:
                result["errors"].append("الملف لا يحتوي جدول الموظفين")
                return result
            employees = [dict(r) for r in src.execute("SELECT * FROM employees")]
            leaves = ([dict(r) for r in src.execute("SELECT * FROM leaves")] if "leaves" in tables else [])
            by_emp: dict[str, list[dict]] = {}
            for lv in leaves:
                by_emp.setdefault(str(lv.get("emp_id")), []).append(lv)

            import_mode = getattr(self, "import_mode", "update")
            with self.db.transaction() as c:
                for emp in employees:
                    emp_id = str(emp.get("emp_id") or "")
                    if not emp_id:
                        continue
                    exists = c.execute("SELECT 1 FROM employees WHERE emp_id=?", (emp_id,)).fetchone()
                    if exists and import_mode == "skip":
                        result["skipped"] += 1
                        continue
                    self._merge_employee(c, emp, by_emp.get(emp_id, []), result, bool(exists))
            self.db.log(user, "استيراد", "database", source.name,
                        f"إضافة {result['added']} - تحديث {result['updated']}")
        except Exception as exc:
            result["errors"].append(str(exc))
            LOG.error("فشل الدمج: %s", exc)
        finally:
            src.close()
        return result

    def _merge_employee(self, c, emp: dict, leaves: list[dict], result: dict, exists: bool) -> None:
        """دمج موظف واحد وإجازاته داخل المعاملة الحالية (نقطة فصل قابلة للاختبار)."""
        emp_id = str(emp.get("emp_id") or "")
        fields = {
            "name": emp.get("name") or "", "job_title": emp.get("job_title") or "",
            "workplace": emp.get("workplace") or "", "institution": emp.get("institution") or "",
            "gender": emp.get("gender") or "ذكر", "start_date": emp.get("start_date") or "",
            "end_date": emp.get("end_date") or "", "notes": emp.get("notes") or "",
            "status": emp.get("status") or "active",
        }
        if exists:
            c.execute("""UPDATE employees SET name=?, job_title=?, workplace=?, gender=?,
                         start_date=?, end_date=?, notes=?, institution=?, status=?,
                         updated_at=? WHERE emp_id=?""",
                      (fields["name"], fields["job_title"], fields["workplace"], fields["gender"],
                       fields["start_date"], fields["end_date"], fields["notes"],
                       fields["institution"], fields["status"], _now(), emp_id))
            c.execute("DELETE FROM leaves WHERE emp_id=?", (emp_id,))
            result["updated"] += 1
        else:
            c.execute("""INSERT INTO employees(emp_id, name, job_title, workplace, gender,
                         start_date, end_date, notes, institution, status, created_at, updated_at)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (emp_id, fields["name"], fields["job_title"], fields["workplace"],
                       fields["gender"], fields["start_date"], fields["end_date"],
                       fields["notes"], fields["institution"], fields["status"], _now(), _now()))
            result["added"] += 1
        for lv in leaves:
            c.execute("""INSERT INTO leaves(emp_id, type, start_date, end_date, from_date,
                         amount, unit, days_actual, working_days, count_mode, order_num,
                         order_date, outside_balance, reason, added_date, status,
                         is_adjustment, manual_days)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (emp_id, lv.get("type") or "", lv.get("start_date") or "",
                       lv.get("end_date") or lv.get("start_date") or "",
                       lv.get("from_date") or lv.get("start_date") or "",
                       lv.get("amount") or 0, lv.get("unit") or "يوم",
                       lv.get("days_actual") or 0, lv.get("working_days") or 0,
                       lv.get("count_mode") or "calendar", lv.get("order_num") or "",
                       lv.get("order_date") or "", int(lv.get("outside_balance") or 0),
                       lv.get("reason") or "", lv.get("added_date") or _now(),
                       lv.get("status") or "approved", int(lv.get("is_adjustment") or 0), 0))
            result["leaves"] += 1


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
