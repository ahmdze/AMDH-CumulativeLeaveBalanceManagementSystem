"""مخطط قاعدة البيانات: CREATE TABLE، الأعمدة الإضافية، الفهارس، والبيانات الافتراضية.

يحتوي على:
  - SCHEMA_VERSION: رقم الإصدار الحالي.
  - _EMPLOYEE_COLUMNS, _LEAVE_COLUMNS, _ATTACHMENT_COLUMNS: أعمدة تضاف للجداول القديمة.
  - create_tables(): إنشاء جميع الجداول.
  - create_indexes(): إنشاء جميع الفهارس.
  - seed_defaults(): تعبئة البيانات الافتراضية (قواعد، سياسة، مستخدم admin).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .. import config
from ..rules import LeaveRule, default_rules

SCHEMA_VERSION = 7

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
    # الرصيد الافتتاحي (المتبقي كما في تاريخ الاحتساب)
    ("opening_balance_set", "INTEGER DEFAULT 0"),
    ("opening_balance", "INTEGER DEFAULT 0"),
    ("opening_balance_date", "TEXT"),
    ("opening_balance_by", "TEXT"),
    ("opening_balance_note", "TEXT"),
    ("opening_updated_at", "TEXT"),
    ("opening_updated_by", "TEXT"),
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


def create_tables(c: sqlite3.Cursor) -> None:
    """إنشاء جميع الجداول الأساسية والجديدة."""
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
            name TEXT,
            recurring INTEGER DEFAULT 0
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS password_vault (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            kind TEXT DEFAULT 'other',
            label TEXT DEFAULT '',
            institution TEXT DEFAULT '',
            file_name TEXT DEFAULT '',
            file_path TEXT DEFAULT '',
            password TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_by TEXT DEFAULT ''
        )""")
    c.execute("""
        CREATE TABLE IF NOT EXISTS employee_opening_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id TEXT,
            changed_at TEXT,
            changed_by TEXT,
            old_set INTEGER DEFAULT 0,
            old_balance INTEGER DEFAULT 0,
            old_date TEXT,
            old_by TEXT,
            old_note TEXT,
            new_set INTEGER DEFAULT 0,
            new_balance INTEGER DEFAULT 0,
            new_date TEXT,
            new_by TEXT,
            new_note TEXT,
            note TEXT DEFAULT ''
        )""")


def create_indexes(c: sqlite3.Cursor) -> None:
    """إنشاء جميع الفهارس المحسّنة للأداء."""
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
        "CREATE INDEX IF NOT EXISTS idx_opening_hist_emp ON employee_opening_history(emp_id)",
    ):
        c.execute(ddl)


def add_missing_columns(c: sqlite3.Cursor, table_columns_fn) -> dict[str, set[str]]:
    """إضافة الأعمدة الناقصة للجداول القديمة.

    Parameters
    ----------
    c : sqlite3.Cursor
        مؤشر قاعدة البيانات.
    table_columns_fn : callable
        دالة تأخذ (conn, table) وتعيد set[str] لأسماء الأعمدة.

    Returns
    -------
    dict[str, set[str]]
        قاموس يحتوي على الأعمدة المضافة لكل جدول.
    """
    added: dict[str, set[str]] = {
        "employees": set(),
        "leaves": set(),
        "attachments": set(),
        "holidays": set(),
    }
    for table, columns in (
        ("employees", _EMPLOYEE_COLUMNS),
        ("leaves", _LEAVE_COLUMNS),
        ("attachments", _ATTACHMENT_COLUMNS),
    ):
        existing = table_columns_fn(table)
        for name, ddl in columns:
            if name not in existing:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                added[table].add(name)
    # عمود recurring في holidays
    holiday_cols = table_columns_fn("holidays")
    if "recurring" not in holiday_cols:
        c.execute("ALTER TABLE holidays ADD COLUMN recurring INTEGER DEFAULT 0")
        added["holidays"].add("recurring")
    return added


def _insert_rule(c: sqlite3.Cursor, rule: LeaveRule) -> None:
    m = rule.to_mapping()
    c.execute(
        """INSERT OR REPLACE INTO leave_rules
                 (type, consumes_balance, service_exclusion, count_mode, quota_days,
                  quota_period, requires_order, is_adjustment, gender, order_index, active, notes)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            m["type"],
            m["consumes_balance"],
            m["service_exclusion"],
            m["count_mode"],
            m["quota_days"],
            m["quota_period"],
            m["requires_order"],
            m["is_adjustment"],
            m["gender"],
            m["order_index"],
            m["active"],
            m["notes"],
        ),
    )


def seed_defaults(c: sqlite3.Cursor) -> None:
    """تعبئة البيانات الافتراضية: قواعد الإجازات، السياسة، ومستخدم admin."""
    if c.execute("SELECT COUNT(*) FROM leave_rules").fetchone()[0] == 0:
        for rule in default_rules().values():
            _insert_rule(c, rule)
    # إلغاء «تسوية رصيد» من الإدخال الجديد: تُعطَّل قواعد التسوية القديمة
    c.execute("UPDATE leave_rules SET active=0 WHERE is_adjustment=1")
    # تصحيح ضابط الأمومة: لا تخصم من الرصيد وتُستبعد من أيام الخدمة
    c.execute("""UPDATE leave_rules SET consumes_balance=0, service_exclusion=1
                 WHERE type='أمومة' AND consumes_balance=1 AND service_exclusion=0""")
    if not c.execute("SELECT 1 FROM app_meta WHERE key='days_per_leave'").fetchone():
        for key, value in config.DEFAULT_POLICY.items():
            c.execute(
                "INSERT OR IGNORE INTO app_meta(key, value) VALUES (?,?)",
                (key, "1" if value is True else "0" if value is False else str(value)),
            )
    if c.execute("SELECT COUNT(*) FROM app_users").fetchone()[0] == 0:
        from ..services.security import hash_password

        pw_hash, salt, iterations = hash_password("admin")
        c.execute(
            """INSERT INTO app_users
                     (username, display_name, role, institution, password_hash, salt,
                      iterations, active, created_at)
                     VALUES (?,?,?,?,?,?,?,1,?)""",
            (
                "admin",
                "مدير النظام",
                "admin",
                "",
                pw_hash,
                salt,
                iterations,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
