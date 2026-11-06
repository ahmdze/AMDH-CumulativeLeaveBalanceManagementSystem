"""الترحيلات: _migrate، _backfill، نسخ احتياطي قبل الترحيل.

يحتوي على:
  - _needs_migration(): فحص ما إذا كانت القاعدة تحتاج ترحيل.
  - _safe_pre_migration_backup(): نسخة احتياطية قبل الترحيل.
  - _migrate(): الترحيل الكامل (إنشاء الجداول، الأعمدة، الفهارس، البيانات).
  - _backfill(): تعبئة القيم الناقصة للبيانات القديمة.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from . import schema

LOG = logging.getLogger("amdh.db")


def _needs_migration(conn: sqlite3.Connection, path: Path) -> bool:
    """فحص ما إذا كانت القاعدة تحتاج ترحيل."""
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        return version < schema.SCHEMA_VERSION
    except sqlite3.DatabaseError:
        return False


def _safe_pre_migration_backup(path: Path, backup_dir: Path) -> bool:
    """نسخة احتياطية قبل الترحيل."""
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        dest = backup_dir / f"pre_migration_{stamp}.db"
        shutil.copy2(path, dest)
        return True
    except OSError as exc:  # pragma: no cover
        LOG.error("فشل النسخ الاحتياطي قبل الترحيل: %s", exc)
        return False


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.DatabaseError:
        return set()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def _migrate(conn: sqlite3.Connection, path: Path, backup_dir: Path) -> bool:
    """الترحيل الكامل: إنشاء الجداول، الأعمدة، الفهارس، والبيانات الافتراضية.

    Returns
    -------
    bool
        True إذا تم الترحيل بنجاح، False إذا لم يكن هناك ترحيل مطلوب.
    """
    migrated = False
    if _needs_migration(conn, path):
        migrated = True
        if _safe_pre_migration_backup(path, backup_dir):
            LOG.info("تم إنشاء نسخة احتياطية قبل الترحيل")

    def table_columns_fn(table: str) -> set[str]:
        return _table_columns(conn, table)

    with conn:
        # --- الجداول الأساسية (تعمل على قاعدة جديدة وقديمة) ---------
        schema.create_tables(conn.cursor())

        # --- إضافة الأعمدة الناقصة (بعد إنشاء كل الجداول) -------------
        added = schema.add_missing_columns(conn.cursor(), table_columns_fn)

        # --- الفهارس ----------------------------------------------
        schema.create_indexes(conn.cursor())

        # --- البيانات الافتراضية -----------------------------------
        schema.seed_defaults(conn.cursor())

        # --- تعبئة القيم الناقصة للبيانات القديمة ------------------
        _backfill(conn.cursor(), added)

        conn.execute(f"PRAGMA user_version = {schema.SCHEMA_VERSION}")

    return migrated


def _backfill(c: sqlite3.Cursor, added: dict[str, set[str]] | None = None) -> None:
    """تعبئة الأعمدة الجديدة للصفوف القديمة مرة واحدة فقط (عند إضافتها فعلياُ).

    لا تُعدّل الأرقام المعتمدة (days_actual) إطلاقاُ.
    """
    added = added or {"employees": set(), "leaves": set(), "attachments": set(), "holidays": set()}
    leave_cols = added.get("leaves", set())
    emp_cols = added.get("employees", set())
    attach_cols = added.get("attachments", set())

    if "end_date" in leave_cols:
        c.execute("""UPDATE leaves
                     SET end_date = date(start_date, '+' || (MAX(COALESCE(days_actual,0),1) - 1) || ' days')
                     WHERE (end_date IS NULL OR end_date = '')
                       AND start_date IS NOT NULL AND start_date <> ''
                       AND days_actual IS NOT NULL""")
    if "working_days" in leave_cols:
        c.execute("UPDATE leaves SET working_days = COALESCE(days_actual, 0) WHERE working_days = 0")
    if "count_mode" in leave_cols:
        c.execute("UPDATE leaves SET count_mode = 'calendar' WHERE count_mode IS NULL OR count_mode = ''")
    if "status" in leave_cols:
        c.execute("UPDATE leaves SET status = 'approved' WHERE status IS NULL OR status = ''")
    if "is_adjustment" in leave_cols:
        c.execute("""UPDATE leaves SET is_adjustment = COALESCE(
                        (SELECT r.is_adjustment FROM leave_rules r WHERE r.type = leaves.type), 0)""")
    if "status" in emp_cols:
        c.execute("UPDATE employees SET status = 'active' WHERE status IS NULL OR status = ''")
    if "created_at" in emp_cols:
        c.execute(
            "UPDATE employees SET created_at = ? WHERE created_at IS NULL OR created_at = ''",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),),
        )

    # --- الإصدار 5: الهوية الثابتة (uid) والمؤسسات -------------------
    if "uid" in emp_cols:
        for row in c.execute("SELECT emp_id FROM employees WHERE uid IS NULL OR uid = ''").fetchall():
            c.execute("UPDATE employees SET uid=? WHERE emp_id=?", (uuid.uuid4().hex, row[0]))
    if "previous_institution" in emp_cols:
        c.execute("""UPDATE employees SET previous_institution = institution
                     WHERE previous_institution IS NULL""")
    if "uid" in leave_cols:
        for row in c.execute("SELECT id FROM leaves WHERE uid IS NULL OR uid = ''").fetchall():
            c.execute("UPDATE leaves SET uid=? WHERE id=?", (uuid.uuid4().hex, row[0]))
    if "institution" in leave_cols:
        c.execute("""UPDATE leaves SET institution = COALESCE(
                        (SELECT e.institution FROM employees e WHERE e.emp_id = leaves.emp_id), '')
                     WHERE institution IS NULL OR institution = ''""")
    if "uid" in attach_cols:
        for row in c.execute("SELECT id FROM attachments WHERE uid IS NULL OR uid = ''").fetchall():
            c.execute("UPDATE attachments SET uid=? WHERE id=?", (uuid.uuid4().hex, row[0]))
    if "leave_uid" in attach_cols:
        c.execute("""UPDATE attachments SET leave_uid = COALESCE(
                        (SELECT l.uid FROM leaves l WHERE l.id = attachments.leave_id), '')
                     WHERE leave_uid IS NULL OR leave_uid = ''""")
    if "institution" in attach_cols:
        c.execute("""UPDATE attachments SET institution = COALESCE(
                        (SELECT l.institution FROM leaves l WHERE l.id = attachments.leave_id), '')
                     WHERE institution IS NULL OR institution = ''""")
    # تسجيل المؤسسات الموجودة فعلاُ في البيانات
    c.execute(
        """INSERT OR IGNORE INTO institutions(name, kind, created_at, updated_at)
                 SELECT DISTINCT TRIM(institution), 'مؤسسة', ?, ?
                 FROM employees
                 WHERE institution IS NOT NULL AND TRIM(institution) <> ''""",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),) * 2,
    )
    c.execute(
        """INSERT OR IGNORE INTO institutions(name, kind, created_at, updated_at)
                 SELECT DISTINCT TRIM(institution), 'مؤسسة', ?, ?
                 FROM leaves
                 WHERE institution IS NOT NULL AND TRIM(institution) <> ''""",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),) * 2,
    )
