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
        while dest.exists():  # ضمان عدم الكتابة فوق نسخة سابقة
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
            items.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "kind": kind,
                    "valid": self._is_valid(path),
                }
            )
        return items

    def _is_valid(self, path: Path) -> bool:
        """يتحقق أن الملف قاعدة سليمة (مشفّرة أو عادية) تحتوي جدول الموظفين."""
        try:
            if getattr(self.db, "key_hex", None):
                from . import crypto

                probe = crypto.open_connection(path, self.db.key_hex)
            else:
                probe = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                row = probe.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='employees'"
                ).fetchone()
                if not row:
                    return False
                return str(probe.execute("PRAGMA integrity_check").fetchone()[0]).lower() == "ok"
            finally:
                probe.close()
        except Exception:  # noqa: BLE001
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
            report = T.apply_transfer(
                self.db,
                source,
                M.MergeOptions(),
                user=user,
                attachments_dir=self.db.path.parent / "attachments",
            )
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(str(exc))
            return result
        result.update(
            {
                "added": report.employees_added,
                "updated": report.employees_updated,
                "skipped": report.employees_skipped,
                "leaves": report.leaves_added,
                "errors": list(report.warnings),
            }
        )
        result["report"] = report
        return result


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
