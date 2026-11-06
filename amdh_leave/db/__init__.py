"""طبقة قاعدة البيانات: مخطط، ترحيلات آمنة، معاملات، استعلامات، تدقيق.

مبادئ التصميم:
  * اتصال واحد دائم (لا تسريب اتصالات) مع WAL و busy_timeout.
  * ترحيلات متكرّرة الأمان (idempotent) مبنية على فحص وجود الأعمدة والجداول.
  * نسخة احتياطية تلقائية قبل أي ترحيل يمسّ بنية البيانات.
  * الحذف ناعم (soft delete) قابل للاستعادة لكل الموظفين والإجازات.

التقسيم:
  - schema.py: CREATE TABLE، أعمدة إضافية، فهارس، بيانات افتراضية.
  - migrations.py: _migrate، _backfill، نسخ احتياطي قبل الترحيل.
  - queries.py: list_employees، list_leaves، add_leave، إلخ.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from ..models import (
    AppUser,
    Attachment,
    AuditEntry,
    Employee,
    EmployeeMove,
    Holiday,
    ImportRecord,
    Institution,
    Leave,
)
from ..rules import LeaveRule, Policy
from ..services import crypto
from . import migrations as _migrations
from . import queries as _queries
from . import schema as _schema

# إعادة تصدير كل شيء للحفاظ على التوافق مع الاستيرادات الحالية
SCHEMA_VERSION = _schema.SCHEMA_VERSION

LOG = logging.getLogger("amdh.db")


class Database:
    """واجهة قاعدة البيانات الوحيدة المستخدمة من الواجهة والخدمات."""

    def __init__(
        self, path: str | Path, backup_dir: str | Path | None = None, key_hex: str | None = None
    ) -> None:
        self.path = Path(path)
        self.backup_dir = Path(backup_dir) if backup_dir else self.path.parent / "backups"
        self.key_hex = key_hex
        self._conn: sqlite3.Connection | None = None
        self._policy_cache: Policy | None = None
        self.migrated = False
        self.open()

    # ==================================================================
    # الاتصال
    # ==================================================================
    def open(self) -> None:
        existed = self.path.exists() and self.path.stat().st_size > 0
        if existed and self.key_hex is None and crypto.is_encrypted_database(self.path):
            raise crypto.CryptoError("قاعدة البيانات مشفّرة — يلزم إدخال كلمة المرور لفتحها.")
        if existed and self._needs_migration():
            if self._safe_pre_migration_backup():
                LOG.info("تم إنشاء نسخة احتياطية قبل الترحيل")
            self.migrated = True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = crypto.open_connection(self.path, self.key_hex)
        if not self.key_hex:
            self._conn.isolation_level = None
        self._conn.row_factory = (
            sqlite3.Row if not self.key_hex else getattr(crypto.sqlcipher_module(), "Row", sqlite3.Row)
        )
        cur = self._conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.execute("PRAGMA busy_timeout = 5000")
        try:
            cur.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:  # pragma: no cover - أنظمة ملفات لا تدعم WAL
            LOG.warning("تعذّر تفعيل WAL")
        cur.execute("PRAGMA synchronous = NORMAL")
        self._migrate()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.execute("PRAGMA optimize")
            except sqlite3.DatabaseError:
                pass
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("قاعدة البيانات مغلقة")
        return self._conn

    def cursor(self) -> sqlite3.Cursor:
        return self.conn.cursor()

    @contextmanager
    def transaction(self):
        """معاملة صريحة: تُثبّت عند النجاح وتُرجِع كل شيء عند أي خطأ."""
        cur = self.cursor()
        cur.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except Exception:
            cur.execute("ROLLBACK")
            raise
        else:
            cur.execute("COMMIT")

    # ==================================================================
    # الترحيل
    # ==================================================================
    def _needs_migration(self) -> bool:
        try:
            probe = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
            try:
                version = probe.execute("PRAGMA user_version").fetchone()[0]
                return version < _schema.SCHEMA_VERSION
            finally:
                probe.close()
        except sqlite3.DatabaseError:
            return False

    def _safe_pre_migration_backup(self) -> bool:
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            from datetime import datetime

            stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            dest = self.backup_dir / f"pre_migration_{stamp}.db"
            import shutil

            shutil.copy2(self.path, dest)
            return True
        except OSError as exc:  # pragma: no cover
            LOG.error("فشل النسخ الاحتياطي قبل الترحيل: %s", exc)
            return False

    def _migrate(self) -> None:
        _migrations._migrate(self.conn, self.path, self.backup_dir)

    @property
    def schema_version(self) -> int:
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    # ==================================================================
    # الإعدادات (app_meta) والسياسة
    # ==================================================================
    def get_meta(self) -> dict[str, str]:
        return _queries.get_meta(self.conn)

    def set_meta(self, values: dict) -> None:
        _queries.set_meta(self.conn, values)
        self._policy_cache = None

    def policy(self, refresh: bool = False) -> Policy:
        if self._policy_cache is None or refresh:
            self._policy_cache = Policy.from_meta(self.get_meta(), self.list_rules(), self.holiday_set())
        return self._policy_cache

    def save_policy(self, policy: Policy) -> None:
        self.set_meta(policy.to_meta())

    def invalidate_policy(self) -> None:
        self._policy_cache = None

    # ==================================================================
    # قواعد أنواع الإجازات
    # ==================================================================
    def list_rules(self) -> dict[str, LeaveRule]:
        return _queries.list_rules(self.conn)

    def save_rule(self, rule: LeaveRule) -> None:
        _queries.save_rule(self.conn, rule)
        self._policy_cache = None

    def delete_rule(self, leave_type: str) -> None:
        _queries.delete_rule(self.conn, leave_type)
        self._policy_cache = None

    # ==================================================================
    # العطل الرسمية
    # ==================================================================
    def list_holidays(self, year: int | None = None) -> list[Holiday]:
        return _queries.list_holidays(self.conn, year)

    def holiday_set(self, years: int | None = None) -> set[date]:
        return _queries.holiday_set(self.conn, years)

    def add_holiday(self, day, name: str = "", recurring: bool = False) -> None:
        _queries.add_holiday(self.conn, day, name, recurring=recurring)
        self._policy_cache = None

    def delete_holiday(self, holiday_id: int) -> None:
        _queries.delete_holiday(self.conn, holiday_id)
        self._policy_cache = None

    # ==================================================================
    # الموظفون
    # ==================================================================
    def list_employees(
        self,
        q: str = "",
        workplace: str = "",
        institution: str = "",
        include_deleted: bool = False,
        with_leaves: bool = True,
    ) -> list[Employee]:
        return _queries.list_employees(self.conn, q, workplace, institution, include_deleted, with_leaves)

    def get_employee(self, emp_id: str, include_deleted: bool = True) -> Employee | None:
        return _queries.get_employee(self.conn, emp_id, include_deleted)

    def employee_exists(self, emp_id: str) -> bool:
        return _queries.employee_exists(self.conn, emp_id)

    def add_employee(self, emp_id: str, fields: dict, user: str = "") -> None:
        _queries.add_employee(self.conn, emp_id, fields, user)

    def update_employee(self, emp_id: str, fields: dict, user: str = "") -> None:
        _queries.update_employee(self.conn, emp_id, fields, user)

    def soft_delete_employee(self, emp_id: str, user: str = "") -> None:
        _queries.soft_delete_employee(self.conn, emp_id, user)

    def restore_employee(self, emp_id: str, user: str = "") -> None:
        _queries.restore_employee(self.conn, emp_id, user)

    def purge_employee(self, emp_id: str) -> None:
        _queries.purge_employee(self.conn, emp_id)

    def distinct_values(self, column: str) -> list[str]:
        return _queries.distinct_values(self.conn, column)

    # ==================================================================
    # الإجازات
    # ==================================================================
    def list_leaves(self, emp_id: str, include_deleted: bool = False) -> list[Leave]:
        return _queries.list_leaves_by_emp(self.conn, emp_id, include_deleted)

    def get_leave(self, leave_id: int) -> Leave | None:
        return _queries.get_leave(self.conn, leave_id)

    def all_leaves(self, include_deleted: bool = False) -> list[Leave]:
        return _queries.all_leaves(self.conn, include_deleted)

    def leaves_in_range(self, start: date, end: date, institution: str = "") -> list[tuple[Employee, Leave]]:
        return _queries.leaves_in_range(self.conn, start, end, institution)

    def add_leave(self, emp_id: str, fields: dict, user: str = "") -> int:
        return _queries.add_leave(self.conn, emp_id, fields, user)

    def update_leave(self, leave_id: int, fields: dict, user: str = "") -> None:
        _queries.update_leave(self.conn, leave_id, fields, user)

    def soft_delete_leave(self, leave_id: int, user: str = "", reason: str = "") -> None:
        _queries.soft_delete_leave(self.conn, leave_id, user, reason)

    def restore_leave(self, leave_id: int, user: str = "") -> None:
        _queries.restore_leave(self.conn, leave_id, user)

    def purge_leave(self, leave_id: int) -> None:
        _queries.purge_leave(self.conn, leave_id)

    def void_employee_leaves(self, emp_id: str, user: str = "") -> None:  # pragma: no cover - توافق
        _queries.void_employee_leaves(self.conn, emp_id, user)

    def purge_all_deleted(self) -> dict[str, int]:
        return _queries.purge_all_deleted(self.conn)

    # ==================================================================
    # المرفقات
    # ==================================================================
    def list_attachments(self, leave_id: int) -> list[Attachment]:
        return _queries.list_attachments(self.conn, leave_id)

    def add_attachment(
        self,
        leave_id: int,
        emp_id: str,
        filename: str,
        stored_name: str,
        user: str = "",
        *,
        attachments_dir: str | Path | None = None,
        sha256: str = "",
        institution: str = "",
    ) -> int:
        return _queries.add_attachment(
            self.conn,
            leave_id,
            emp_id,
            filename,
            stored_name,
            user,
            attachments_dir=attachments_dir,
            sha256=sha256,
            institution=institution,
        )

    def delete_attachment(self, attachment_id: int, user: str = "") -> None:
        _queries.delete_attachment(self.conn, attachment_id, user)

    # ==================================================================
    # المستخدمون
    # ==================================================================
    def list_users(self) -> list[AppUser]:
        return _queries.list_users(self.conn)

    def get_user(self, username: str) -> AppUser | None:
        return _queries.get_user(self.conn, username)

    def save_user(self, user: AppUser) -> None:
        _queries.save_user(self.conn, user)

    def delete_user(self, username: str) -> None:
        _queries.delete_user(self.conn, username)

    def touch_login(self, username: str) -> None:
        _queries.touch_login(self.conn, username)

    # ==================================================================
    # خزنة كلمات المرور
    # ==================================================================
    def list_vault(self) -> list[dict]:
        return _queries.list_vault(self.conn)

    def add_vault_entry(
        self,
        *,
        kind: str = "other",
        label: str = "",
        institution: str = "",
        file_name: str = "",
        file_path: str = "",
        password: str = "",
        note: str = "",
        user: str = "",
    ) -> int:
        return _queries.add_vault_entry(
            self.conn,
            kind=kind,
            label=label,
            institution=institution,
            file_name=file_name,
            file_path=file_path,
            password=password,
            note=note,
            user=user,
        )

    def update_vault_entry(self, entry_id: int, **fields) -> None:
        _queries.update_vault_entry(self.conn, entry_id, **fields)

    def delete_vault_entry(self, entry_id: int) -> None:
        _queries.delete_vault_entry(self.conn, entry_id)

    # ==================================================================
    # سجل التدقيق
    # ==================================================================
    def log(self, username: str, action: str, entity: str, entity_id: str = "", details: str = "") -> None:
        _queries.log_action(self.conn, username, action, entity, entity_id, details)

    def list_audit(
        self,
        username: str = "",
        action: str = "",
        entity: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 1000,
    ) -> list[AuditEntry]:
        return _queries.list_audit(self.conn, username, action, entity, date_from, date_to, limit)

    def audit_values(self, column: str) -> list[str]:
        return _queries.audit_values(self.conn, column)

    # ==================================================================
    # صيانة ونُسخ احتياطية
    # ==================================================================
    def integrity_check(self) -> tuple[bool, str]:
        return _queries.integrity_check(self.conn)

    def vacuum(self) -> None:
        _queries.vacuum_db(self.conn)

    def backup_to(self, dest: str | Path) -> Path:
        return _queries.backup_to(self.conn, dest, self.key_hex)

    def export_plaintext(self, dest: str | Path) -> Path:
        return _queries.export_plaintext(self.conn, dest, self.key_hex)

    def stats(self) -> dict:
        return _queries.stats(self.conn, self.path)

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ==================================================================
    # المؤسسات (وحدة النقل والدمج)
    # ==================================================================
    def list_institutions(self, active_only: bool = False) -> list[Institution]:
        return _queries.list_institutions(self.conn, active_only)

    def get_institution(self, name: str) -> Institution | None:
        return _queries.get_institution(self.conn, name)

    def save_institution(self, fields: dict, user: str = "") -> Institution:
        return _queries.save_institution(self.conn, fields, user)

    def register_institutions(self, names, user: str = "") -> list[str]:
        return _queries.register_institutions(self.conn, names, user)

    def delete_institution(self, name: str, user: str = "") -> tuple[bool, str]:
        return _queries.delete_institution(self.conn, name, user)

    def set_institution_import(
        self, name: str, *, when: str, user: str = "", filename: str = "", counts: str = ""
    ) -> None:
        _queries.set_institution_import(
            self.conn, name, when=when, user=user, filename=filename, counts=counts
        )

    def set_institution_export(self, name: str, when: str) -> None:
        _queries.set_institution_export(self.conn, name, when)

    def center_institution(self) -> str:
        return _queries.center_institution(self.conn)

    def set_center_institution(self, name: str) -> None:
        _queries.set_center_institution(self.conn, name)

    def institution_employee_counts(self) -> dict[str, int]:
        return _queries.institution_employee_counts(self.conn)

    # ==================================================================
    # سجل الاستيراد/التصدير
    # ==================================================================
    def add_import(self, record: dict, user: str = "") -> int:
        return _queries.add_import(self.conn, record, user)

    def list_imports(self, limit: int = 50, institution: str = "", direction: str = "") -> list[ImportRecord]:
        return _queries.list_imports(self.conn, limit, institution, direction)

    def get_import(self, import_id: int) -> ImportRecord | None:
        return _queries.get_import(self.conn, import_id)

    def last_import_for(self, institution: str) -> ImportRecord | None:
        return _queries.last_import_for(self.conn, institution)

    def checksum_seen(self, checksum: str) -> ImportRecord | None:
        return _queries.checksum_seen(self.conn, checksum)

    # ==================================================================
    # انتقال الموظفين بين المؤسسات
    # ==================================================================
    def add_move(
        self,
        emp_id: str,
        from_institution: str,
        to_institution: str,
        moved_on=None,
        source_file: str = "",
        note: str = "",
        user: str = "",
    ) -> int:
        return _queries.add_move(
            self.conn, emp_id, from_institution, to_institution, moved_on, source_file, note, user
        )

    def list_moves(self, emp_id: str = "", limit: int = 200) -> list[EmployeeMove]:
        return _queries.list_moves(self.conn, emp_id, limit)

    def set_employee_institution(self, emp_id: str, institution: str, moved_on=None, user: str = "") -> None:
        _queries.set_employee_institution(self.conn, emp_id, institution, moved_on, user)

    # ==================================================================
    # بيانات خامة للمقارنة في الدمج
    # ==================================================================
    def raw_employees(self, include_deleted: bool = True) -> dict[str, dict]:
        return _queries.raw_employees(self.conn, include_deleted)

    def raw_leaves(self, include_deleted: bool = True) -> dict[str, dict]:
        return _queries.raw_leaves(self.conn, include_deleted)

    def raw_attachments(self) -> list[dict]:
        return _queries.raw_attachments(self.conn)

    def get_leave_by_uid(self, uid: str) -> Leave | None:
        return _queries.get_leave_by_uid(self.conn, uid)

    def attachment_hashes(self) -> dict[str, dict]:
        return _queries.attachment_hashes(self.conn)

    def add_attachment_row(
        self,
        c: sqlite3.Cursor,
        *,
        leave_id=None,
        emp_id: str = "",
        filename: str = "",
        stored_name: str = "",
        sha256: str = "",
        leave_uid: str = "",
        institution: str = "",
        uid: str = "",
        user: str = "",
    ) -> int:
        return _queries.add_attachment_row(
            self.conn,
            leave_id=leave_id,
            emp_id=emp_id,
            filename=filename,
            stored_name=stored_name,
            sha256=sha256,
            leave_uid=leave_uid,
            institution=institution,
            uid=uid,
            user=user,
        )

    def set_transfer_manifest(self, values: dict) -> None:
        _queries.set_transfer_manifest(self.conn, values)

    def get_transfer_manifest(self) -> dict[str, str]:
        return _queries.get_transfer_manifest(self.conn)


# إعادة تصدير الأدوات المساعدة للتوافق مع الكود القديم
def _now() -> str:
    return _queries._now()


def _chunks(items: list, size: int):
    return _queries._chunks(items, size)


def _row_to_leave(data: dict) -> Leave:
    return _queries._row_to_leave(data)


def _fallback_leave_key(data: dict) -> str:
    return _queries._fallback_leave_key(data)


def _sha256_file(path: Path) -> str:
    return _queries._sha256_file(path)
