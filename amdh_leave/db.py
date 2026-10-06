"""طبقة قاعدة البيانات: مخطط، ترحيلات آمنة، معاملات، استعلامات، تدقيق.

مبادئ التصميم:
  * اتصال واحد دائم (لا تسريب اتصالات) مع WAL و busy_timeout.
  * ترحيلات متكرّرة الأمان (idempotent) مبنية على فحص وجود الأعمدة والجداول.
  * نسخة احتياطية تلقائية قبل أي ترحيل يمسّ بنية البيانات.
  * الحذف ناعم (soft delete) قابل للاستعادة لكل الموظفين والإجازات.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from . import config
from .models import (AppUser, Attachment, AuditEntry, Employee, EmployeeMove, Holiday,
                     ImportRecord, Institution, Leave)
from .rules import LeaveRule, Policy, default_rules
from .services import crypto
from .services.dates import parse_iso, to_iso

SCHEMA_VERSION = 5

LOG = logging.getLogger("amdh.db")

# أعمدة تُضاف للجداول القديمة (الاسم، التعريف)
_EMPLOYEE_COLUMNS: list[tuple[str, str]] = [
    ("end_date", "TEXT"),
    ("status", "TEXT DEFAULT 'active'"),
    ("created_at", "TEXT"),
    ("updated_at", "TEXT"),
    ("deleted_at", "TEXT"),
    ("deleted_by", "TEXT"),
    ("uid", "TEXT"),
    ("previous_institution", "TEXT"),
    ("moved_on", "TEXT"),
]

_LEAVE_COLUMNS: list[tuple[str, str]] = [
    ("end_date", "TEXT"),
    ("working_days", "INTEGER DEFAULT 0"),
    ("count_mode", "TEXT DEFAULT 'calendar'"),
    ("status", "TEXT DEFAULT 'approved'"),
    ("approved_by", "TEXT"),
    ("approved_at", "TEXT"),
    ("created_by", "TEXT"),
    ("modified_at", "TEXT"),
    ("modified_by", "TEXT"),
    ("deleted_at", "TEXT"),
    ("deleted_by", "TEXT"),
    ("is_adjustment", "INTEGER DEFAULT 0"),
    ("manual_days", "INTEGER DEFAULT 0"),
    ("uid", "TEXT"),
    ("institution", "TEXT"),
]

_ATTACHMENT_COLUMNS: list[tuple[str, str]] = [
    ("uid", "TEXT"),
    ("leave_uid", "TEXT"),
    ("sha256", "TEXT"),
    ("institution", "TEXT"),
]


class Database:
    """واجهة قاعدة البيانات الوحيدة المستخدمة من الواجهة والخدمات."""

    def __init__(self, path: str | Path, backup_dir: str | Path | None = None,
                 key_hex: str | None = None) -> None:
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
            raise crypto.CryptoError(
                "قاعدة البيانات مشفّرة — يلزم إدخال كلمة المرور لفتحها.")
        if existed and self._needs_migration():
            if self._safe_pre_migration_backup():
                LOG.info("تم إنشاء نسخة احتياطية قبل الترحيل")
            self.migrated = True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = crypto.open_connection(self.path, self.key_hex)
        if not self.key_hex:
            self._conn.isolation_level = None
        self._conn.row_factory = sqlite3.Row
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
                return version < SCHEMA_VERSION
            finally:
                probe.close()
        except sqlite3.DatabaseError:
            return False

    def _safe_pre_migration_backup(self) -> bool:
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            dest = self.backup_dir / f"pre_migration_{stamp}.db"
            shutil.copy2(self.path, dest)
            return True
        except OSError as exc:  # pragma: no cover
            LOG.error("فشل النسخ الاحتياطي قبل الترحيل: %s", exc)
            return False

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
        try:
            return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        except sqlite3.DatabaseError:
            return set()

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return row is not None

    def _migrate(self) -> None:
        conn = self.conn
        with self.transaction() as c:
            # --- الجداول الأساسية (تعمل على قاعدة جديدة وقديمة) ---------
            c.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    emp_id TEXT PRIMARY KEY,
                    name TEXT,
                    job_title TEXT,
                    workplace TEXT,
                    gender TEXT,
                    start_date TEXT,
                    notes TEXT,
                    institution TEXT,
                    end_date TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TEXT,
                    updated_at TEXT,
                    deleted_at TEXT,
                    deleted_by TEXT,
                    uid TEXT,
                    previous_institution TEXT,
                    moved_on TEXT
                )""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS leaves (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    emp_id TEXT,
                    type TEXT,
                    start_date TEXT,
                    from_date TEXT,
                    amount INTEGER,
                    unit TEXT,
                    days_actual INTEGER,
                    order_num TEXT,
                    order_date TEXT,
                    outside_balance INTEGER,
                    reason TEXT,
                    added_date TEXT,
                    end_date TEXT,
                    working_days INTEGER DEFAULT 0,
                    count_mode TEXT DEFAULT 'calendar',
                    status TEXT DEFAULT 'approved',
                    approved_by TEXT,
                    approved_at TEXT,
                    created_by TEXT,
                    modified_at TEXT,
                    modified_by TEXT,
                    deleted_at TEXT,
                    deleted_by TEXT,
                    is_adjustment INTEGER DEFAULT 0,
                    manual_days INTEGER DEFAULT 0,
                    uid TEXT,
                    institution TEXT,
                    FOREIGN KEY(emp_id) REFERENCES employees(emp_id) ON DELETE CASCADE
                )""")

            # --- الجداول الجديدة ---------------------------------------
            c.execute("""
                CREATE TABLE IF NOT EXISTS leave_rules (
                    type TEXT PRIMARY KEY,
                    consumes_balance INTEGER DEFAULT 1,
                    service_exclusion INTEGER DEFAULT 0,
                    count_mode TEXT DEFAULT 'calendar',
                    quota_days INTEGER DEFAULT 0,
                    quota_period TEXT DEFAULT 'none',
                    requires_order INTEGER DEFAULT 0,
                    is_adjustment INTEGER DEFAULT 0,
                    gender TEXT DEFAULT '',
                    order_index INTEGER DEFAULT 0,
                    active INTEGER DEFAULT 1,
                    notes TEXT DEFAULT ''
                )""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS holidays (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    day TEXT UNIQUE,
                    name TEXT
                )""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS app_users (
                    username TEXT PRIMARY KEY,
                    display_name TEXT DEFAULT '',
                    role TEXT DEFAULT 'viewer',
                    institution TEXT DEFAULT '',
                    password_hash TEXT DEFAULT '',
                    salt TEXT DEFAULT '',
                    iterations INTEGER DEFAULT 200000,
                    active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT '',
                    last_login TEXT DEFAULT ''
                )""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT,
                    username TEXT,
                    action TEXT,
                    entity TEXT,
                    entity_id TEXT,
                    details TEXT
                )""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    leave_id INTEGER,
                    emp_id TEXT,
                    filename TEXT,
                    stored_name TEXT,
                    added_at TEXT,
                    added_by TEXT,
                    uid TEXT,
                    leave_uid TEXT,
                    sha256 TEXT,
                    institution TEXT
                )""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )""")
            # --- المؤسسات وسجل النقل والاستيراد -------------------------
            c.execute("""
                CREATE TABLE IF NOT EXISTS institutions (
                    name TEXT PRIMARY KEY,
                    code TEXT DEFAULT '',
                    kind TEXT DEFAULT 'مستشفى',
                    manager TEXT DEFAULT '',
                    phone TEXT DEFAULT '',
                    address TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    is_center INTEGER DEFAULT 0,
                    username TEXT DEFAULT '',
                    active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT '',
                    updated_at TEXT DEFAULT '',
                    last_import_at TEXT DEFAULT '',
                    last_export_at TEXT DEFAULT '',
                    last_import_user TEXT DEFAULT '',
                    last_import_file TEXT DEFAULT '',
                    last_import_counts TEXT DEFAULT ''
                )""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT, username TEXT, direction TEXT, scope TEXT,
                    institution TEXT, source_file TEXT, checksum TEXT,
                    source_schema INTEGER DEFAULT 0, source_policy TEXT DEFAULT '',
                    period_from TEXT DEFAULT '', period_to TEXT DEFAULT '',
                    employees_added INTEGER DEFAULT 0, employees_updated INTEGER DEFAULT 0,
                    employees_unchanged INTEGER DEFAULT 0, employees_conflict INTEGER DEFAULT 0,
                    leaves_added INTEGER DEFAULT 0, leaves_updated INTEGER DEFAULT 0,
                    leaves_unchanged INTEGER DEFAULT 0, moves INTEGER DEFAULT 0,
                    attachments INTEGER DEFAULT 0, warnings INTEGER DEFAULT 0,
                    report TEXT DEFAULT ''
                )""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS employee_moves (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    emp_id TEXT, from_institution TEXT, to_institution TEXT,
                    moved_on TEXT, recorded_at TEXT, source_file TEXT, note TEXT
                )""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS transfer_manifest (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )""")

            # --- إضافة الأعمدة الناقصة (بعد إنشاء كل الجداول) -------------
            added: dict[str, set[str]] = {"employees": set(), "leaves": set(), "attachments": set()}
            for table, columns in (("employees", _EMPLOYEE_COLUMNS),
                                   ("leaves", _LEAVE_COLUMNS),
                                   ("attachments", _ATTACHMENT_COLUMNS)):
                existing = self._table_columns(c, table)
                for name, ddl in columns:
                    if name not in existing:
                        c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                        added[table].add(name)

            # --- الفهارس ----------------------------------------------
            for ddl in (
                "CREATE INDEX IF NOT EXISTS idx_leaves_emp ON leaves(emp_id)",
                "CREATE INDEX IF NOT EXISTS idx_leaves_start ON leaves(start_date)",
                "CREATE INDEX IF NOT EXISTS idx_leaves_deleted ON leaves(deleted_at)",
                "CREATE INDEX IF NOT EXISTS idx_leaves_uid ON leaves(uid)",
                "CREATE INDEX IF NOT EXISTS idx_leaves_institution ON leaves(institution)",
                "CREATE INDEX IF NOT EXISTS idx_emp_inst ON employees(institution)",
                "CREATE INDEX IF NOT EXISTS idx_emp_work ON employees(workplace)",
                "CREATE INDEX IF NOT EXISTS idx_emp_deleted ON employees(deleted_at)",
                "CREATE INDEX IF NOT EXISTS idx_emp_uid ON employees(uid)",
                "CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts)",
                "CREATE INDEX IF NOT EXISTS idx_attach_leave ON attachments(leave_id)",
                "CREATE INDEX IF NOT EXISTS idx_attach_uid ON attachments(uid)",
                "CREATE INDEX IF NOT EXISTS idx_attach_sha ON attachments(sha256)",
                "CREATE INDEX IF NOT EXISTS idx_imports_ts ON imports(ts)",
                "CREATE INDEX IF NOT EXISTS idx_imports_inst ON imports(institution)",
                "CREATE INDEX IF NOT EXISTS idx_moves_emp ON employee_moves(emp_id)",
            ):
                c.execute(ddl)

            # --- البيانات الافتراضية -----------------------------------
            if c.execute("SELECT COUNT(*) FROM leave_rules").fetchone()[0] == 0:
                for rule in default_rules().values():
                    self._insert_rule(c, rule)
            if not c.execute("SELECT 1 FROM app_meta WHERE key='days_per_leave'").fetchone():
                for key, value in config.DEFAULT_POLICY.items():
                    c.execute("INSERT OR IGNORE INTO app_meta(key, value) VALUES (?,?)",
                              (key, "1" if value is True else "0" if value is False else str(value)))
            if c.execute("SELECT COUNT(*) FROM app_users").fetchone()[0] == 0:
                from .services.security import hash_password
                pw_hash, salt, iterations = hash_password("admin")
                c.execute("""INSERT INTO app_users
                             (username, display_name, role, institution, password_hash, salt,
                              iterations, active, created_at)
                             VALUES (?,?,?,?,?,?,?,1,?)""",
                          ("admin", "مدير النظام", "admin", "", pw_hash, salt, iterations,
                           datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

            # --- تعبئة القيم الناقصة للبيانات القديمة ------------------
            self._backfill(c, added)

            c.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @staticmethod
    def _insert_rule(c: sqlite3.Cursor, rule: LeaveRule) -> None:
        m = rule.to_mapping()
        c.execute("""INSERT OR REPLACE INTO leave_rules
                     (type, consumes_balance, service_exclusion, count_mode, quota_days,
                      quota_period, requires_order, is_adjustment, gender, order_index, active, notes)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (m["type"], m["consumes_balance"], m["service_exclusion"], m["count_mode"],
                   m["quota_days"], m["quota_period"], m["requires_order"], m["is_adjustment"],
                   m["gender"], m["order_index"], m["active"], m["notes"]))

    def _backfill(self, c: sqlite3.Cursor, added: dict[str, set[str]] | None = None) -> None:
        """تعبئة الأعمدة الجديدة للصفوف القديمة مرة واحدة فقط (عند إضافتها فعلياً).

        لا تُعدّل الأرقام المعتمدة (days_actual) إطلاقاً.
        """
        added = added or {"employees": set(), "leaves": set(), "attachments": set()}
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
            c.execute("UPDATE employees SET created_at = ? WHERE created_at IS NULL OR created_at = ''",
                      (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))

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
        # تسجيل المؤسسات الموجودة فعلاً في البيانات
        c.execute("""INSERT OR IGNORE INTO institutions(name, kind, created_at, updated_at)
                     SELECT DISTINCT TRIM(institution), 'مؤسسة', ?, ?
                     FROM employees
                     WHERE institution IS NOT NULL AND TRIM(institution) <> ''""",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),) * 2)
        c.execute("""INSERT OR IGNORE INTO institutions(name, kind, created_at, updated_at)
                     SELECT DISTINCT TRIM(institution), 'مؤسسة', ?, ?
                     FROM leaves
                     WHERE institution IS NOT NULL AND TRIM(institution) <> ''""",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),) * 2)

    @property
    def schema_version(self) -> int:
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    # ==================================================================
    # الإعدادات (app_meta) والسياسة
    # ==================================================================
    def get_meta(self) -> dict[str, str]:
        rows = self.conn.execute("SELECT key, value FROM app_meta").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def set_meta(self, values: dict) -> None:
        with self.transaction() as c:
            for key, value in values.items():
                c.execute("INSERT INTO app_meta(key, value) VALUES (?,?) "
                          "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
        self._policy_cache = None

    def policy(self, refresh: bool = False) -> Policy:
        if self._policy_cache is None or refresh:
            self._policy_cache = Policy.from_meta(
                self.get_meta(), self.list_rules(), self.holiday_set())
        return self._policy_cache

    def save_policy(self, policy: Policy) -> None:
        self.set_meta(policy.to_meta())

    def invalidate_policy(self) -> None:
        self._policy_cache = None

    # ==================================================================
    # قواعد أنواع الإجازات
    # ==================================================================
    def list_rules(self) -> dict[str, LeaveRule]:
        rows = self.conn.execute("SELECT * FROM leave_rules").fetchall()
        rules = {r["type"]: LeaveRule.from_mapping(dict(r)) for r in rows}
        return rules or default_rules()

    def save_rule(self, rule: LeaveRule) -> None:
        with self.transaction() as c:
            self._insert_rule(c, rule)
        self._policy_cache = None

    def delete_rule(self, leave_type: str) -> None:
        with self.transaction() as c:
            c.execute("DELETE FROM leave_rules WHERE type=?", (leave_type,))
        self._policy_cache = None

    # ==================================================================
    # العطل الرسمية
    # ==================================================================
    def list_holidays(self, year: int | None = None) -> list[Holiday]:
        sql = "SELECT * FROM holidays"
        params: list = []
        if year:
            sql += " WHERE day LIKE ?"
            params.append(f"{year}-%")
        sql += " ORDER BY day"
        return [Holiday(id=r["id"], day=parse_iso(r["day"]), name=r["name"] or "")
                for r in self.conn.execute(sql, params).fetchall()]

    def holiday_set(self, years: int | None = None) -> set[date]:
        holidays = self.list_holidays()
        return {h.day for h in holidays if h.day}

    def add_holiday(self, day, name: str = "") -> None:
        with self.transaction() as c:
            c.execute("INSERT OR REPLACE INTO holidays(day, name) VALUES (?,?)", (to_iso(day), name))
        self._policy_cache = None

    def delete_holiday(self, holiday_id: int) -> None:
        with self.transaction() as c:
            c.execute("DELETE FROM holidays WHERE id=?", (holiday_id,))
        self._policy_cache = None

    # ==================================================================
    # الموظفون
    # ==================================================================
    def _employee_query(self, q: str = "", workplace: str = "", institution: str = "",
                        include_deleted: bool = False) -> tuple[str, list]:
        conditions, params = [], []
        if not include_deleted:
            conditions.append("(deleted_at IS NULL OR deleted_at = '')")
        else:
            conditions.append("(deleted_at IS NOT NULL AND deleted_at <> '')")
        if q:
            conditions.append("(emp_id LIKE ? OR name LIKE ? OR job_title LIKE ?)")
            like = f"%{q}%"
            params += [like, like, like]
        if workplace:
            conditions.append("workplace = ?")
            params.append(workplace)
        if institution:
            conditions.append("institution = ?")
            params.append(institution)
        where = " AND ".join(conditions)
        return f"SELECT * FROM employees WHERE {where} ORDER BY name COLLATE NOCASE, emp_id", params

    def list_employees(self, q: str = "", workplace: str = "", institution: str = "",
                       include_deleted: bool = False, with_leaves: bool = True) -> list[Employee]:
        sql, params = self._employee_query(q, workplace, institution, include_deleted)
        rows = self.conn.execute(sql, params).fetchall()
        employees = [Employee.from_mapping(dict(r)) for r in rows]
        if with_leaves and employees:
            ids = [e.emp_id for e in employees]
            by_emp: dict[str, list[Leave]] = {eid: [] for eid in ids}
            for chunk in _chunks(ids, 400):
                marks = ",".join("?" * len(chunk))
                sql_l = (f"SELECT * FROM leaves WHERE emp_id IN ({marks}) "
                         f"AND (deleted_at IS NULL OR deleted_at = '') ORDER BY id")
                for row in self.conn.execute(sql_l, chunk).fetchall():
                    lv = _row_to_leave(dict(row))
                    by_emp.setdefault(lv.emp_id, []).append(lv)
            for emp in employees:
                emp.leaves = by_emp.get(emp.emp_id, [])
        return employees

    def get_employee(self, emp_id: str, include_deleted: bool = True) -> Employee | None:
        row = self.conn.execute("SELECT * FROM employees WHERE emp_id=?", (emp_id,)).fetchone()
        if not row:
            return None
        emp = Employee.from_mapping(dict(row))
        if not include_deleted and emp.is_deleted:
            return None
        emp.leaves = self.list_leaves(emp_id)
        return emp

    def employee_exists(self, emp_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM employees WHERE emp_id=?", (emp_id,)).fetchone() is not None

    def add_employee(self, emp_id: str, fields: dict, user: str = "") -> None:
        now = _now()
        with self.transaction() as c:
            c.execute("""INSERT INTO employees
                         (emp_id, name, job_title, workplace, gender, start_date, end_date,
                          notes, institution, status, created_at, updated_at, uid,
                          previous_institution)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (emp_id, fields.get("name", ""), fields.get("job_title", ""),
                       fields.get("workplace", ""), fields.get("gender", "ذكر"),
                       fields.get("start_date", ""), fields.get("end_date", ""),
                       fields.get("notes", ""), fields.get("institution", ""),
                       fields.get("status", "active"), now, now,
                       fields.get("uid") or uuid.uuid4().hex,
                       fields.get("previous_institution", fields.get("institution", ""))))
        self.log(user, "إضافة", "employee", emp_id, fields.get("name", ""))

    def update_employee(self, emp_id: str, fields: dict, user: str = "") -> None:
        with self.transaction() as c:
            c.execute("""UPDATE employees SET name=?, job_title=?, workplace=?, gender=?,
                         start_date=?, end_date=?, notes=?, institution=?, status=?, updated_at=?
                         WHERE emp_id=?""",
                      (fields.get("name", ""), fields.get("job_title", ""), fields.get("workplace", ""),
                       fields.get("gender", "ذكر"), fields.get("start_date", ""),
                       fields.get("end_date", ""), fields.get("notes", ""),
                       fields.get("institution", ""), fields.get("status", "active"),
                       _now(), emp_id))
        self.log(user, "تعديل", "employee", emp_id, fields.get("name", ""))

    def soft_delete_employee(self, emp_id: str, user: str = "") -> None:
        with self.transaction() as c:
            c.execute("UPDATE employees SET deleted_at=?, deleted_by=? WHERE emp_id=?",
                      (_now(), user, emp_id))
        self.log(user, "حذف", "employee", emp_id, "")

    def restore_employee(self, emp_id: str, user: str = "") -> None:
        with self.transaction() as c:
            c.execute("UPDATE employees SET deleted_at=NULL, deleted_by=NULL WHERE emp_id=?", (emp_id,))
        self.log(user, "استعادة", "employee", emp_id, "")

    def purge_employee(self, emp_id: str) -> None:
        with self.transaction() as c:
            c.execute("DELETE FROM employees WHERE emp_id=?", (emp_id,))
        LOG.warning("حذف نهائي للموظف %s", emp_id)

    def distinct_values(self, column: str) -> list[str]:
        if column not in {"workplace", "institution", "job_title", "gender"}:
            raise ValueError("عمود غير مسموح")
        rows = self.conn.execute(
            f"SELECT DISTINCT {column} FROM employees WHERE {column} IS NOT NULL AND {column} <> '' "
            f"AND (deleted_at IS NULL OR deleted_at='') ORDER BY {column}").fetchall()
        return [r[0] for r in rows]

    # ==================================================================
    # الإجازات
    # ==================================================================
    def list_leaves(self, emp_id: str, include_deleted: bool = False) -> list[Leave]:
        sql = "SELECT * FROM leaves WHERE emp_id=?"
        if not include_deleted:
            sql += " AND (deleted_at IS NULL OR deleted_at='')"
        sql += " ORDER BY id"
        return [_row_to_leave(dict(r)) for r in self.conn.execute(sql, (emp_id,)).fetchall()]

    def get_leave(self, leave_id: int) -> Leave | None:
        row = self.conn.execute("SELECT * FROM leaves WHERE id=?", (leave_id,)).fetchone()
        return _row_to_leave(dict(row)) if row else None

    def all_leaves(self, include_deleted: bool = False) -> list[Leave]:
        sql = "SELECT * FROM leaves"
        if not include_deleted:
            sql += " WHERE (deleted_at IS NULL OR deleted_at='')"
        sql += " ORDER BY emp_id, id"
        return [_row_to_leave(dict(r)) for r in self.conn.execute(sql).fetchall()]

    def leaves_in_range(self, start: date, end: date, institution: str = "") -> list[tuple[Employee, Leave]]:
        sql = """SELECT l.*, e.name AS emp_name, e.job_title AS emp_job, e.institution AS emp_inst
                 FROM leaves l JOIN employees e ON e.emp_id = l.emp_id
                 WHERE (l.deleted_at IS NULL OR l.deleted_at='')
                   AND (e.deleted_at IS NULL OR e.deleted_at='')
                   AND COALESCE(l.end_date, l.start_date) >= ?
                   AND l.start_date <= ?"""
        params: list = [to_iso(start), to_iso(end)]
        if institution:
            sql += " AND e.institution = ?"
            params.append(institution)
        sql += " ORDER BY l.start_date"
        out = []
        for row in self.conn.execute(sql, params).fetchall():
            data = dict(row)
            emp = Employee(emp_id=data["emp_id"], name=data.pop("emp_name") or "",
                           job_title=data.pop("emp_job") or "", institution=data.pop("emp_inst") or "")
            out.append((emp, _row_to_leave(data)))
        return out

    def add_leave(self, emp_id: str, fields: dict, user: str = "") -> int:
        with self.transaction() as c:
            c.execute("""INSERT INTO leaves
                (emp_id, type, start_date, end_date, from_date, amount, unit, days_actual,
                 working_days, count_mode, order_num, order_date, outside_balance, reason,
                 added_date, status, approved_by, approved_at, created_by, modified_at,
                 modified_by, is_adjustment, manual_days, uid, institution)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (emp_id, fields.get("type", ""), fields.get("start_date", ""),
                       fields.get("end_date", ""), fields.get("from_date", fields.get("start_date", "")),
                       fields.get("amount", 0), fields.get("unit", "يوم"),
                       fields.get("days_actual", 0), fields.get("working_days", 0),
                       fields.get("count_mode", "calendar"), fields.get("order", ""),
                       fields.get("order_date", ""), int(fields.get("outside_balance", False)),
                       fields.get("reason", ""), fields.get("added_date") or _now(),
                       fields.get("status", "approved"), fields.get("approved_by", ""),
                       fields.get("approved_at", ""), user, fields.get("modified_at") or _now(), user,
                       int(fields.get("is_adjustment", False)), int(fields.get("manual_days", False)),
                       fields.get("uid") or uuid.uuid4().hex,
                       fields.get("institution") or self._employee_institution(emp_id)))
            leave_id = int(c.execute("SELECT last_insert_rowid()").fetchone()[0])
        self.log(user, "إضافة", "leave", str(leave_id),
                 f"{emp_id} - {fields.get('type', '')} - {fields.get('days_actual', 0)} يوم")
        return leave_id

    def _employee_institution(self, emp_id: str) -> str:
        if not emp_id:
            return ""
        row = self.conn.execute("SELECT institution FROM employees WHERE emp_id=?",
                                (emp_id,)).fetchone()
        return str(row[0] or "") if row else ""

    def update_leave(self, leave_id: int, fields: dict, user: str = "") -> None:
        """تعديل إجازة: لا يمسّ تاريخ الإضافة ولا منشئ السجل (يُسجَّل التعديل في modified_*)."""
        current = self.get_leave(leave_id)
        emp_id = str(fields.get("emp_id") or (current.emp_id if current else ""))
        with self.transaction() as c:
            c.execute("""UPDATE leaves SET type=?, start_date=?, end_date=?, from_date=?,
                         amount=?, unit=?, days_actual=?, working_days=?, count_mode=?,
                         order_num=?, order_date=?, outside_balance=?, reason=?, status=?,
                         is_adjustment=?, manual_days=?, modified_at=?, modified_by=?,
                         institution=COALESCE(NULLIF(institution, ''), ?)
                         WHERE id=?""",
                      (fields.get("type", ""), fields.get("start_date", ""), fields.get("end_date", ""),
                       fields.get("from_date", fields.get("start_date", "")), fields.get("amount", 0),
                       fields.get("unit", "يوم"), fields.get("days_actual", 0),
                       fields.get("working_days", 0), fields.get("count_mode", "calendar"),
                       fields.get("order", ""), fields.get("order_date", ""),
                       int(fields.get("outside_balance", False)), fields.get("reason", ""),
                       fields.get("status", "approved"), int(fields.get("is_adjustment", False)),
                       int(fields.get("manual_days", False)), _now(), user,
                       fields.get("institution") or self._employee_institution(emp_id),
                       leave_id))
        self.log(user, "تعديل", "leave", str(leave_id),
                 f"{fields.get('type', '')} - {fields.get('days_actual', 0)} يوم")

    def soft_delete_leave(self, leave_id: int, user: str = "", reason: str = "") -> None:
        with self.transaction() as c:
            c.execute("UPDATE leaves SET deleted_at=?, deleted_by=? WHERE id=?",
                      (_now(), user, leave_id))
        self.log(user, "حذف", "leave", str(leave_id), reason)

    def restore_leave(self, leave_id: int, user: str = "") -> None:
        with self.transaction() as c:
            c.execute("UPDATE leaves SET deleted_at=NULL, deleted_by=NULL WHERE id=?", (leave_id,))
        self.log(user, "استعادة", "leave", str(leave_id), "")

    def purge_leave(self, leave_id: int) -> None:
        with self.transaction() as c:
            c.execute("DELETE FROM attachments WHERE leave_id=?", (leave_id,))
            c.execute("DELETE FROM leaves WHERE id=?", (leave_id,))

    def void_employee_leaves(self, emp_id: str, user: str = "") -> None:  # pragma: no cover - توافق
        with self.transaction() as c:
            c.execute("UPDATE leaves SET deleted_at=?, deleted_by=? WHERE emp_id=? AND deleted_at IS NULL",
                      (_now(), user, emp_id))

    def purge_all_deleted(self) -> dict[str, int]:
        """إفراغ سلة المحذوفات نهائياً."""
        with self.transaction() as c:
            leaves = c.execute("SELECT COUNT(*) FROM leaves WHERE deleted_at IS NOT NULL AND deleted_at<>''").fetchone()[0]
            emps = c.execute("SELECT COUNT(*) FROM employees WHERE deleted_at IS NOT NULL AND deleted_at<>''").fetchone()[0]
            c.execute("DELETE FROM leaves WHERE deleted_at IS NOT NULL AND deleted_at<>''")
            c.execute("DELETE FROM employees WHERE deleted_at IS NOT NULL AND deleted_at<>''")
        return {"leaves": leaves, "employees": emps}

    # ==================================================================
    # المرفقات
    # ==================================================================
    def list_attachments(self, leave_id: int) -> list[Attachment]:
        rows = self.conn.execute("SELECT * FROM attachments WHERE leave_id=? ORDER BY id",
                                 (leave_id,)).fetchall()
        return [Attachment.from_mapping(dict(row)) for row in rows]

    def add_attachment(self, leave_id: int, emp_id: str, filename: str, stored_name: str,
                       user: str = "", *, attachments_dir: str | Path | None = None,
                       sha256: str = "", institution: str = "") -> int:
        """يضيف مرفقاً مع بصمة sha256 ومعرّف ثابت لتنتقل المرفقات مع ملفات النقل."""
        leave = self.get_leave(leave_id) if leave_id else None
        if not sha256 and attachments_dir and stored_name:
            candidate = Path(attachments_dir) / stored_name
            if candidate.exists():
                sha256 = _sha256_file(candidate)
        with self.transaction() as c:
            return self.add_attachment_row(
                c, leave_id=leave_id, emp_id=emp_id, filename=filename, stored_name=stored_name,
                sha256=sha256, leave_uid=(leave.uid if leave else ""),
                institution=institution or (leave.institution if leave else
                                            self._employee_institution(emp_id)),
                user=user)

    def delete_attachment(self, attachment_id: int, user: str = "") -> None:
        with self.transaction() as c:
            c.execute("DELETE FROM attachments WHERE id=?", (attachment_id,))
        self.log(user, "حذف مرفق", "attachment", str(attachment_id), "")

    # ==================================================================
    # المستخدمون
    # ==================================================================
    def list_users(self) -> list[AppUser]:
        rows = self.conn.execute("SELECT * FROM app_users ORDER BY username").fetchall()
        return [AppUser.from_mapping(dict(r)) for r in rows]

    def get_user(self, username: str) -> AppUser | None:
        row = self.conn.execute("SELECT * FROM app_users WHERE username=?", (username,)).fetchone()
        return AppUser.from_mapping(dict(row)) if row else None

    def save_user(self, user: AppUser) -> None:
        with self.transaction() as c:
            exists = c.execute("SELECT 1 FROM app_users WHERE username=?", (user.username,)).fetchone()
            if exists:
                c.execute("""UPDATE app_users SET display_name=?, role=?, institution=?,
                             password_hash=?, salt=?, iterations=?, active=? WHERE username=?""",
                          (user.display_name, user.role, user.institution, user.password_hash,
                           user.salt, user.iterations, int(user.active), user.username))
            else:
                c.execute("""INSERT INTO app_users(username, display_name, role, institution,
                             password_hash, salt, iterations, active, created_at)
                             VALUES (?,?,?,?,?,?,?,?,?)""",
                          (user.username, user.display_name, user.role, user.institution,
                           user.password_hash, user.salt, user.iterations, int(user.active), _now()))

    def delete_user(self, username: str) -> None:
        with self.transaction() as c:
            c.execute("DELETE FROM app_users WHERE username=?", (username,))

    def touch_login(self, username: str) -> None:
        with self.transaction() as c:
            c.execute("UPDATE app_users SET last_login=? WHERE username=?", (_now(), username))

    # ==================================================================
    # سجل التدقيق
    # ==================================================================
    def log(self, username: str, action: str, entity: str, entity_id: str = "", details: str = "") -> None:
        try:
            with self.transaction() as c:
                c.execute("""INSERT INTO audit_log(ts, username, action, entity, entity_id, details)
                             VALUES (?,?,?,?,?,?)""",
                          (_now(), username or "—", action, entity, str(entity_id), details))
        except sqlite3.DatabaseError as exc:  # pragma: no cover
            LOG.error("تعذّر تسجيل التدقيق: %s", exc)

    def list_audit(self, username: str = "", action: str = "", entity: str = "",
                   date_from: str = "", date_to: str = "", limit: int = 1000) -> list[AuditEntry]:
        conditions, params = ["1=1"], []
        if username:
            conditions.append("username = ?")
            params.append(username)
        if action:
            conditions.append("action = ?")
            params.append(action)
        if entity:
            conditions.append("entity = ?")
            params.append(entity)
        if date_from:
            conditions.append("ts >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("ts <= ?")
            params.append(date_to + " 23:59:59")
        params.append(int(limit))
        sql = (f"SELECT * FROM audit_log WHERE {' AND '.join(conditions)} "
               f"ORDER BY id DESC LIMIT ?")
        rows = self.conn.execute(sql, params).fetchall()
        return [AuditEntry(id=r["id"], ts=r["ts"], username=r["username"], action=r["action"],
                           entity=r["entity"], entity_id=r["entity_id"], details=r["details"])
                for r in rows]

    def audit_values(self, column: str) -> list[str]:
        if column not in {"username", "action", "entity"}:
            raise ValueError("عمود غير مسموح")
        rows = self.conn.execute(
            f"SELECT DISTINCT {column} FROM audit_log WHERE {column} IS NOT NULL ORDER BY {column}").fetchall()
        return [r[0] for r in rows]

    # ==================================================================
    # صيانة ونُسخ احتياطية
    # ==================================================================
    def integrity_check(self) -> tuple[bool, str]:
        try:
            result = self.conn.execute("PRAGMA integrity_check").fetchone()[0]
            ok = str(result).lower() == "ok"
            fk = self.conn.execute("PRAGMA foreign_key_check").fetchall()
            if fk:
                return False, f"مرجعية معطوبة: {len(fk)} سجل"
            return ok, str(result)
        except sqlite3.DatabaseError as exc:
            return False, str(exc)

    def vacuum(self) -> None:
        self.conn.execute("VACUUM")

    def backup_to(self, dest: str | Path) -> Path:
        """نسخة احتياطية متسقة عبر واجهة SQLite (آمنة حتى مع وجود كتابة)."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(str(dest))
        try:
            with target:
                self.conn.backup(target)
        finally:
            target.close()
        return dest

    def stats(self) -> dict:
        c = self.conn
        live = "(deleted_at IS NULL OR deleted_at='')"
        dead = "(deleted_at IS NOT NULL AND deleted_at<>'')"
        return {
            "employees": c.execute(f"SELECT COUNT(*) FROM employees WHERE {live}").fetchone()[0],
            "employees_deleted": c.execute(f"SELECT COUNT(*) FROM employees WHERE {dead}").fetchone()[0],
            "leaves": c.execute(f"SELECT COUNT(*) FROM leaves WHERE {live}").fetchone()[0],
            "leaves_deleted": c.execute(f"SELECT COUNT(*) FROM leaves WHERE {dead}").fetchone()[0],
            "institutions": len(self.distinct_values("institution")),
            "workplaces": len(self.distinct_values("workplace")),
            "attachments": c.execute("SELECT COUNT(*) FROM attachments").fetchone()[0],
            "audit": c.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0],
            "size_bytes": self.path.stat().st_size if self.path.exists() else 0,
            "schema_version": self.schema_version,
            "path": str(self.path),
        }

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ==================================================================
    # المؤسسات (وحدة النقل والدمج)
    # ==================================================================
    def list_institutions(self, active_only: bool = False) -> list[Institution]:
        sql = "SELECT i.*, (SELECT COUNT(*) FROM employees e WHERE e.institution = i.name " \
              "AND (e.deleted_at IS NULL OR e.deleted_at='')) AS employees FROM institutions i"
        if active_only:
            sql += " WHERE i.active = 1"
        sql += " ORDER BY i.is_center DESC, i.name"
        return [Institution.from_mapping(dict(row)) for row in self.conn.execute(sql)]

    def get_institution(self, name: str) -> Institution | None:
        row = self.conn.execute("SELECT * FROM institutions WHERE name=?", (name,)).fetchone()
        return Institution.from_mapping(dict(row)) if row else None

    def save_institution(self, fields: dict, user: str = "") -> Institution:
        name = str(fields.get("name") or "").strip()
        if not name:
            raise ValueError("اسم المؤسسة إلزامي")
        now = _now()
        existing = self.get_institution(name)
        payload = {
            "code": str(fields.get("code") or "").strip(),
            "kind": str(fields.get("kind") or "مستشفى").strip(),
            "manager": str(fields.get("manager") or "").strip(),
            "phone": str(fields.get("phone") or "").strip(),
            "address": str(fields.get("address") or "").strip(),
            "notes": str(fields.get("notes") or "").strip(),
            "is_center": int(bool(fields.get("is_center"))),
            "username": str(fields.get("username") or "").strip(),
            "active": int(fields.get("active", 1)),
        }
        with self.transaction() as c:
            if existing:
                c.execute("""UPDATE institutions SET code=?, kind=?, manager=?, phone=?, address=?,
                             notes=?, is_center=?, username=?, active=?, updated_at=? WHERE name=?""",
                          (payload["code"], payload["kind"], payload["manager"], payload["phone"],
                           payload["address"], payload["notes"], payload["is_center"],
                           payload["username"], payload["active"], now, name))
            else:
                c.execute("""INSERT INTO institutions
                             (name, code, kind, manager, phone, address, notes, is_center,
                              username, active, created_at, updated_at)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (name, payload["code"], payload["kind"], payload["manager"],
                           payload["phone"], payload["address"], payload["notes"],
                           payload["is_center"], payload["username"], payload["active"], now, now))
        self.log(user or "—", "إضافة" if not existing else "تعديل", "institution", name,
                 payload["kind"])
        return self.get_institution(name)  # type: ignore[return-value]

    def register_institutions(self, names, user: str = "") -> list[str]:
        """يتأكد من وجود المؤسسات (يُنشئ الناقص) — تُستخدم عند الدمج والتصدير."""
        created: list[str] = []
        now = _now()
        with self.transaction() as c:
            for raw in names:
                name = str(raw or "").strip()
                if not name:
                    continue
                row = c.execute("SELECT 1 FROM institutions WHERE name=?", (name,)).fetchone()
                if not row:
                    c.execute("""INSERT INTO institutions(name, kind, created_at, updated_at)
                                 VALUES (?,?,?,?)""", (name, "مؤسسة", now, now))
                    created.append(name)
        if created and user:
            self.log(user, "إضافة", "institution", ", ".join(created), "أُنشئت تلقائياً عند الاستيراد")
        return created

    def delete_institution(self, name: str) -> tuple[bool, str]:
        """يحذف مؤسسة بشرط ألا يكون لها موظفون أو إجازات."""
        employees = self.conn.execute(
            "SELECT COUNT(*) FROM employees WHERE institution=?", (name,)).fetchone()[0]
        if employees:
            return False, f"لا يمكن الحذف: هناك {employees} موظفاً مرتبطاً بهذه المؤسسة."
        with self.transaction() as c:
            c.execute("DELETE FROM institutions WHERE name=?", (name,))
        return True, "تم حذف المؤسسة."

    def set_institution_import(self, name: str, *, when: str, user: str = "",
                               filename: str = "", counts: str = "") -> None:
        with self.transaction() as c:
            c.execute("""UPDATE institutions SET last_import_at=?, last_import_user=?,
                         last_import_file=?, last_import_counts=? WHERE name=?""",
                      (when, user, filename, counts, name))

    def set_institution_export(self, name: str, when: str) -> None:
        with self.transaction() as c:
            c.execute("UPDATE institutions SET last_export_at=? WHERE name=?", (when, name))

    def center_institution(self) -> str:
        value = self.get_meta().get("center_institution", "")
        if value:
            return value
        row = self.conn.execute("SELECT name FROM institutions WHERE is_center=1 LIMIT 1").fetchone()
        return row[0] if row else ""

    def set_center_institution(self, name: str) -> None:
        name = str(name or "").strip()
        with self.transaction() as c:
            c.execute("UPDATE institutions SET is_center=0")
            if name:
                c.execute("UPDATE institutions SET is_center=1 WHERE name=?", (name,))
        self.set_meta({"center_institution": name})

    def institution_employee_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT institution, COUNT(*) FROM employees WHERE (deleted_at IS NULL OR deleted_at='') "
            "GROUP BY institution").fetchall()
        return {row[0] or "": row[1] for row in rows}

    # ==================================================================
    # سجل الاستيراد/التصدير
    # ==================================================================
    def add_import(self, record: dict, user: str = "") -> int:
        columns = ["ts", "username", "direction", "scope", "institution", "source_file",
                   "checksum", "source_schema", "source_policy", "period_from", "period_to",
                   "employees_added", "employees_updated", "employees_unchanged",
                   "employees_conflict", "leaves_added", "leaves_updated", "leaves_unchanged",
                   "moves", "attachments", "warnings", "report"]
        values = [record.get(column, "" if column in {"ts", "username", "direction", "scope",
                                                      "institution", "source_file", "checksum",
                                                      "source_policy", "period_from", "period_to",
                                                      "report"} else 0)
                  for column in columns]
        if not record.get("ts"):
            values[0] = _now()
        if not record.get("username"):
            values[1] = user or "—"
        with self.transaction() as c:
            c.execute(f"INSERT INTO imports ({','.join(columns)}) "
                      f"VALUES ({','.join('?' * len(columns))})", values)
            return int(c.execute("SELECT last_insert_rowid()").fetchone()[0])

    def list_imports(self, limit: int = 50, institution: str = "",
                     direction: str = "") -> list[ImportRecord]:
        conditions, params = ["1=1"], []
        if institution:
            conditions.append("institution = ?")
            params.append(institution)
        if direction:
            conditions.append("direction = ?")
            params.append(direction)
        params.append(int(limit))
        rows = self.conn.execute(
            f"SELECT * FROM imports WHERE {' AND '.join(conditions)} ORDER BY id DESC LIMIT ?",
            params).fetchall()
        return [ImportRecord.from_mapping(dict(row)) for row in rows]

    def get_import(self, import_id: int) -> ImportRecord | None:
        row = self.conn.execute("SELECT * FROM imports WHERE id=?", (import_id,)).fetchone()
        return ImportRecord.from_mapping(dict(row)) if row else None

    def last_import_for(self, institution: str) -> ImportRecord | None:
        rows = self.list_imports(limit=1, institution=institution, direction="import")
        return rows[0] if rows else None

    def checksum_seen(self, checksum: str) -> ImportRecord | None:
        if not checksum:
            return None
        row = self.conn.execute(
            "SELECT * FROM imports WHERE checksum=? ORDER BY id DESC LIMIT 1", (checksum,)).fetchone()
        return ImportRecord.from_mapping(dict(row)) if row else None

    # ==================================================================
    # انتقال الموظفين بين المؤسسات
    # ==================================================================
    def add_move(self, emp_id: str, from_institution: str, to_institution: str,
                 moved_on=None, source_file: str = "", note: str = "", user: str = "") -> int:
        with self.transaction() as c:
            c.execute("""INSERT INTO employee_moves
                         (emp_id, from_institution, to_institution, moved_on, recorded_at,
                          source_file, note)
                         VALUES (?,?,?,?,?,?,?)""",
                      (emp_id, from_institution, to_institution, to_iso(moved_on), _now(),
                       source_file, note))
            return int(c.execute("SELECT last_insert_rowid()").fetchone()[0])

    def list_moves(self, emp_id: str = "", limit: int = 200) -> list[EmployeeMove]:
        if emp_id:
            rows = self.conn.execute(
                "SELECT * FROM employee_moves WHERE emp_id=? ORDER BY id DESC LIMIT ?",
                (emp_id, int(limit))).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM employee_moves ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        return [EmployeeMove.from_mapping(dict(row)) for row in rows]

    def set_employee_institution(self, emp_id: str, institution: str, moved_on=None,
                                 user: str = "") -> None:
        with self.transaction() as c:
            c.execute("""UPDATE employees SET previous_institution = institution,
                         institution = ?, moved_on = ?, updated_at = ? WHERE emp_id = ?""",
                      (institution, to_iso(moved_on), _now(), emp_id))
        self.log(user, "نقل", "employee", emp_id, f"إلى {institution}")

    # ==================================================================
    # بيانات خامة للمقارنة في الدمج
    # ==================================================================
    def raw_employees(self, include_deleted: bool = True) -> dict[str, dict]:
        sql = "SELECT * FROM employees"
        if not include_deleted:
            sql += " WHERE deleted_at IS NULL OR deleted_at=''"
        return {str(row["emp_id"]): dict(row) for row in self.conn.execute(sql)}

    def raw_leaves(self, include_deleted: bool = True) -> dict[str, dict]:
        """مفتاح القاموس هو uid الإجازة (أو مفتاح بديل إن غاب)."""
        sql = "SELECT * FROM leaves"
        if not include_deleted:
            sql += " WHERE deleted_at IS NULL OR deleted_at=''"
        result: dict[str, dict] = {}
        for row in self.conn.execute(sql):
            data = dict(row)
            result[data.get("uid") or _fallback_leave_key(data)] = data
        return result

    def raw_attachments(self) -> list[dict]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM attachments")]

    def get_leave_by_uid(self, uid: str) -> Leave | None:
        row = self.conn.execute("SELECT * FROM leaves WHERE uid=?", (uid,)).fetchone()
        return _row_to_leave(dict(row)) if row else None

    def attachment_hashes(self) -> dict[str, dict]:
        rows = self.conn.execute(
            "SELECT * FROM attachments WHERE sha256 IS NOT NULL AND sha256 <> ''").fetchall()
        return {row["sha256"]: dict(row) for row in rows}

    def add_attachment_row(self, c: sqlite3.Cursor, *, leave_id=None, emp_id: str = "",
                           filename: str = "", stored_name: str = "", sha256: str = "",
                           leave_uid: str = "", institution: str = "", uid: str = "",
                           user: str = "") -> int:
        """إدراج مرفق داخل معاملة قائمة (يُستخدم في الدمج والواجهة)."""
        c.execute("""INSERT INTO attachments
                     (leave_id, emp_id, filename, stored_name, added_at, added_by,
                      uid, leave_uid, sha256, institution)
                     VALUES (?,?,?,?,?,?,?,?,?,?)""",
                  (leave_id, emp_id, filename, stored_name, _now(), user,
                   uid or uuid.uuid4().hex, leave_uid, sha256, institution))
        return int(c.execute("SELECT last_insert_rowid()").fetchone()[0])

    def set_transfer_manifest(self, values: dict) -> None:
        with self.transaction() as c:
            for key, value in values.items():
                c.execute("INSERT INTO transfer_manifest(key, value) VALUES (?,?) "
                          "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                          (str(key), str(value)))

    def get_transfer_manifest(self) -> dict[str, str]:
        try:
            rows = self.conn.execute("SELECT key, value FROM transfer_manifest").fetchall()
        except sqlite3.DatabaseError:
            return {}
        return {row["key"]: row["value"] for row in rows}


# ---------------------------------------------------------------------------
# أدوات
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _row_to_leave(data: dict) -> Leave:
    data = dict(data)
    if "order_num" in data:
        data.setdefault("order", data.get("order_num") or "")
    return Leave.from_mapping(data)


def _fallback_leave_key(data: dict) -> str:
    """مفتاح بديل للإجازات القديمة بلا uid (نوع + تاريخ بدء + رقم الأمر + الأيام)."""
    return "|".join(str(data.get(field) or "") for field in
                    ("type", "start_date", "order_num", "days_actual"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
