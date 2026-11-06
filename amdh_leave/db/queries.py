"""استعلامات قاعدة البيانات: جميع دوال الاستعلام والعمليات.

يحتوي على:
  - الموظفين: list_employees, get_employee, add_employee, update_employee, إلخ.
  - الإجازات: list_leaves, add_leave, update_leave, إلخ.
  - المرفقات: list_attachments, add_attachment, إلخ.
  - المستخدمون: list_users, save_user, إلخ.
  - العطل الرسمية: list_holidays, add_holiday, إلخ.
  - قواعد الإجازات: list_rules, save_rule, إلخ.
  - المؤسسات: list_institutions, save_institution, إلخ.
  - الاستيراد/التصدير: add_import, list_imports, إلخ.
  - سجل التدقيق: log, list_audit, إلخ.
  - الصيانة: integrity_check, backup_to, إلخ.
"""

from __future__ import annotations

import calendar
import hashlib
import logging
import sqlite3
import uuid
from datetime import date, datetime
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
from ..rules import LeaveRule, default_rules
from ..services import crypto
from ..services.dates import parse_iso, to_iso

LOG = logging.getLogger("amdh.db")


# ==================================================================
# أدوات
# ==================================================================


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _row_to_leave(data: dict) -> Leave:
    data = dict(data)
    if "order_num" in data:
        data.setdefault("order", data.get("order_num") or "")
    return Leave.from_mapping(data)


def _fallback_leave_key(data: dict) -> str:
    """مفتاح بديل للإجازات القديمة بلا uid (نوع + تاريخ بدء + رقم الأمر + الأيام)."""
    return "|".join(
        str(data.get(field) or "") for field in ("type", "start_date", "order_num", "days_actual")
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ==================================================================
# الإعدادات (app_meta) والسياسة
# ==================================================================


def get_meta(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM app_meta").fetchall()
    return {r["key"]: r["value"] for r in rows}


def set_meta(conn: sqlite3.Connection, values: dict) -> None:
    with conn:
        for key, value in values.items():
            conn.execute(
                "INSERT INTO app_meta(key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )


# ==================================================================
# قواعد أنواع الإجازات
# ==================================================================


def list_rules(conn: sqlite3.Connection) -> dict[str, LeaveRule]:
    rows = conn.execute("SELECT * FROM leave_rules").fetchall()
    rules = {r["type"]: LeaveRule.from_mapping(dict(r)) for r in rows}
    return rules or default_rules()


def save_rule(conn: sqlite3.Connection, rule: LeaveRule) -> None:
    m = rule.to_mapping()
    with conn:
        conn.execute(
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


def delete_rule(conn: sqlite3.Connection, leave_type: str) -> None:
    with conn:
        conn.execute("DELETE FROM leave_rules WHERE type=?", (leave_type,))


# ==================================================================
# العطل الرسمية
# ==================================================================


def list_holidays(conn: sqlite3.Connection, year: int | None = None) -> list[Holiday]:
    sql = "SELECT * FROM holidays"
    params: list = []
    if year:
        sql += " WHERE day LIKE ? OR recurring = 1"
        params.append(f"{year}-%")
    sql += " ORDER BY day"
    result = []
    for r in conn.execute(sql, params).fetchall():
        d = dict(r)
        day_obj = parse_iso(d["day"])
        recurring = bool(d.get("recurring", 0))
        if year and day_obj and recurring and day_obj.year != year:
            max_day = calendar.monthrange(year, day_obj.month)[1]
            day_obj = date(year, day_obj.month, min(day_obj.day, max_day))
        result.append(
            Holiday(
                id=d["id"],
                day=day_obj,
                name=d.get("name") or "",
                recurring=recurring,
            )
        )
    return result


def holiday_set(conn: sqlite3.Connection, years: int | list[int] | set[int] | None = None) -> set[date]:
    """يعيد مجموعة تواريخ العطل الرسمية، مع توليد العطل المتكررة سنوياً لجميع السنوات."""
    holidays = list_holidays(conn)
    result: set[date] = set()
    if years is None:
        current_year = date.today().year
        target_years = list(range(1990, current_year + 15))
    elif isinstance(years, int):
        target_years = [years]
    else:
        target_years = list(years)

    for h in holidays:
        if not h.day:
            continue
        result.add(h.day)
        if h.recurring:
            for yr in target_years:
                max_day = calendar.monthrange(yr, h.day.month)[1]
                result.add(date(yr, h.day.month, min(h.day.day, max_day)))
    return result


def add_holiday(conn: sqlite3.Connection, day, name: str = "", recurring: bool = False) -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO holidays(day, name, recurring) VALUES (?,?,?)",
            (to_iso(day), name, int(recurring)),
        )


def delete_holiday(conn: sqlite3.Connection, holiday_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM holidays WHERE id=?", (holiday_id,))


# ==================================================================
# الموظفون
# ==================================================================


def _employee_query(
    q: str = "", workplace: str = "", institution: str = "", include_deleted: bool = False
) -> tuple[str, list]:
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
        conditions.append("(institution = ? OR secondment_to = ?)")
        params.extend([institution, institution])
    where = " AND ".join(conditions)
    return f"SELECT * FROM employees WHERE {where} ORDER BY name COLLATE NOCASE, emp_id", params


def list_employees(
    conn: sqlite3.Connection,
    q: str = "",
    workplace: str = "",
    institution: str = "",
    include_deleted: bool = False,
    with_leaves: bool = True,
) -> list[Employee]:
    sql, params = _employee_query(q, workplace, institution, include_deleted)
    rows = conn.execute(sql, params).fetchall()
    employees = [Employee.from_mapping(dict(r)) for r in rows]
    if with_leaves and employees:
        ids = [e.emp_id for e in employees]
        by_emp: dict[str, list[Leave]] = {eid: [] for eid in ids}
        for chunk in _chunks(ids, 400):
            marks = ",".join("?" * len(chunk))
            sql_l = (
                f"SELECT * FROM leaves WHERE emp_id IN ({marks}) "
                f"AND (deleted_at IS NULL OR deleted_at = '') ORDER BY id"
            )
            for row in conn.execute(sql_l, chunk).fetchall():
                lv = _row_to_leave(dict(row))
                by_emp.setdefault(lv.emp_id, []).append(lv)
        for emp in employees:
            emp.leaves = by_emp.get(emp.emp_id, [])
    return employees


def get_employee(conn: sqlite3.Connection, emp_id: str, include_deleted: bool = True) -> Employee | None:
    row = conn.execute("SELECT * FROM employees WHERE emp_id=?", (emp_id,)).fetchone()
    if not row:
        return None
    emp = Employee.from_mapping(dict(row))
    if not include_deleted and getattr(emp, "is_deleted", False):
        return None
    emp.leaves = list_leaves_by_emp(conn, emp_id)
    return emp


def employee_exists(conn: sqlite3.Connection, emp_id: str) -> bool:
    return conn.execute("SELECT 1 FROM employees WHERE emp_id=?", (emp_id,)).fetchone() is not None


def _opening_values(fields: dict) -> tuple[int, int, str, str, str]:
    """قيم الرصيد الافتتاحي الموحّدة (set, amount, date, by, note)."""
    is_set = int(bool(fields.get("opening_balance_set")))
    if not is_set:
        return 0, 0, "", "", ""
    return (
        1,
        int(fields.get("opening_balance") or 0),
        str(fields.get("opening_balance_date") or ""),
        str(fields.get("opening_balance_by") or ""),
        str(fields.get("opening_balance_note") or ""),
    )


def add_employee(conn: sqlite3.Connection, emp_id: str, fields: dict, user: str = "") -> None:
    now = _now()
    opening = _opening_values(fields)
    with conn:
        conn.execute(
            """INSERT INTO employees
                     (emp_id, name, job_title, workplace, gender, start_date, end_date,
                      notes, institution, status, created_at, updated_at, uid,
                      previous_institution, opening_balance_set, opening_balance,
                      opening_balance_date, opening_balance_by, opening_balance_note,
                      opening_updated_at, opening_updated_by,
                      secondment_to, secondment_start, secondment_end, secondment_order)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                emp_id,
                fields.get("name", ""),
                fields.get("job_title", ""),
                fields.get("workplace", ""),
                fields.get("gender", "ذكر"),
                fields.get("start_date", ""),
                fields.get("end_date", ""),
                fields.get("notes", ""),
                fields.get("institution", ""),
                fields.get("status", "active"),
                now,
                now,
                fields.get("uid") or uuid.uuid4().hex,
                fields.get("previous_institution", fields.get("institution", "")),
                *opening,
                now if opening[0] else "",
                user if opening[0] else "",
                fields.get("secondment_to", ""),
                fields.get("secondment_start", ""),
                fields.get("secondment_end", ""),
                fields.get("secondment_order", ""),
            ),
        )
    log_action(conn, user, "إضافة", "employee", emp_id, fields.get("name", ""))


def _log_opening_change(c, emp_id: str, old: tuple, new: tuple, user: str, note: str = "") -> None:
    if tuple(old) == tuple(new):
        return
    c.execute(
        """INSERT INTO employee_opening_history
                 (emp_id, changed_at, changed_by, old_set, old_balance, old_date,
                  old_by, old_note, new_set, new_balance, new_date, new_by, new_note, note)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (emp_id, _now(), user or "—", *old, *new, note),
    )


def update_employee(conn: sqlite3.Connection, emp_id: str, fields: dict, user: str = "") -> None:
    previous = get_employee(conn, emp_id)
    old_opening = (
        int(bool(previous.opening_balance_set)) if previous else 0,
        int(previous.opening_balance or 0) if previous else 0,
        previous.opening_balance_date.strftime("%Y-%m-%d")
        if previous and previous.opening_balance_date
        else "",
        previous.opening_balance_by if previous else "",
        previous.opening_balance_note if previous else "",
    )
    opening = _opening_values(fields)
    sec_to = fields.get("secondment_to", previous.secondment_to if previous else "")
    sec_start = fields.get(
        "secondment_start",
        D_iso(previous.secondment_start) if previous and previous.secondment_start else "",
    )
    sec_end = fields.get(
        "secondment_end",
        D_iso(previous.secondment_end) if previous and previous.secondment_end else "",
    )
    sec_order = fields.get("secondment_order", previous.secondment_order if previous else "")
    with conn:
        conn.execute(
            """UPDATE employees SET name=?, job_title=?, workplace=?, gender=?,
                     start_date=?, end_date=?, notes=?, institution=?, status=?,
                     opening_balance_set=?, opening_balance=?, opening_balance_date=?,
                     opening_balance_by=?, opening_balance_note=?,
                     opening_updated_at=CASE WHEN ? THEN ? ELSE opening_updated_at END,
                     opening_updated_by=CASE WHEN ? THEN ? ELSE opening_updated_by END,
                     secondment_to=?, secondment_start=?, secondment_end=?, secondment_order=?,
                     updated_at=? WHERE emp_id=?""",
            (
                fields.get("name", ""),
                fields.get("job_title", ""),
                fields.get("workplace", ""),
                fields.get("gender", "ذكر"),
                fields.get("start_date", ""),
                fields.get("end_date", ""),
                fields.get("notes", ""),
                fields.get("institution", ""),
                fields.get("status", "active"),
                *opening,
                int(opening != old_opening),
                _now(),
                int(opening != old_opening),
                user,
                sec_to,
                sec_start,
                sec_end,
                sec_order,
                _now(),
                emp_id,
            ),
        )
        if opening != old_opening:
            _log_opening_change(conn, emp_id, old_opening, opening, user, "تعديل الرصيد الافتتاحي")
    log_action(conn, user, "تعديل", "employee", emp_id, fields.get("name", ""))


def D_iso(d: date | None) -> str:
    return d.strftime("%Y-%m-%d") if d else ""


def soft_delete_employee(conn: sqlite3.Connection, emp_id: str, user: str = "") -> None:
    with conn:
        conn.execute("UPDATE employees SET deleted_at=?, deleted_by=? WHERE emp_id=?", (_now(), user, emp_id))
    log_action(conn, user, "حذف", "employee", emp_id, "")


def restore_employee(conn: sqlite3.Connection, emp_id: str, user: str = "") -> None:
    with conn:
        conn.execute("UPDATE employees SET deleted_at=NULL, deleted_by=NULL WHERE emp_id=?", (emp_id,))
    log_action(conn, user, "استعادة", "employee", emp_id, "")


def purge_employee(conn: sqlite3.Connection, emp_id: str) -> None:
    with conn:
        conn.execute("DELETE FROM employees WHERE emp_id=?", (emp_id,))
    LOG.warning("حذف نهائي للموظف %s", emp_id)


def distinct_values(conn: sqlite3.Connection, column: str) -> list[str]:
    if column not in {"workplace", "institution", "job_title", "gender"}:
        raise ValueError("عمود غير مسموح")
    rows = conn.execute(
        f"SELECT DISTINCT {column} FROM employees WHERE {column} IS NOT NULL AND {column} <> '' "
        f"AND (deleted_at IS NULL OR deleted_at='') ORDER BY {column}"
    ).fetchall()
    return [r[0] for r in rows]


# ==================================================================
# الإجازات
# ==================================================================


def list_leaves_by_emp(conn: sqlite3.Connection, emp_id: str, include_deleted: bool = False) -> list[Leave]:
    sql = "SELECT * FROM leaves WHERE emp_id=?"
    if not include_deleted:
        sql += " AND (deleted_at IS NULL OR deleted_at='')"
    sql += " ORDER BY id"
    return [_row_to_leave(dict(r)) for r in conn.execute(sql, (emp_id,)).fetchall()]


def get_leave(conn: sqlite3.Connection, leave_id: int) -> Leave | None:
    row = conn.execute("SELECT * FROM leaves WHERE id=?", (leave_id,)).fetchone()
    return _row_to_leave(dict(row)) if row else None


def all_leaves(conn: sqlite3.Connection, include_deleted: bool = False) -> list[Leave]:
    sql = "SELECT * FROM leaves"
    if not include_deleted:
        sql += " WHERE (deleted_at IS NULL OR deleted_at='')"
    sql += " ORDER BY emp_id, id"
    return [_row_to_leave(dict(r)) for r in conn.execute(sql).fetchall()]


def leaves_in_range(
    conn: sqlite3.Connection, start: date, end: date, institution: str = ""
) -> list[tuple[Employee, Leave]]:
    sql = """SELECT l.*, e.name AS emp_name, e.job_title AS emp_job, e.institution AS emp_inst
             FROM leaves l JOIN employees e ON e.emp_id = l.emp_id
             WHERE (l.deleted_at IS NULL OR l.deleted_at='')
               AND (e.deleted_at IS NULL OR e.deleted_at='')
               AND COALESCE(l.end_date, l.start_date) >= ?
               AND l.start_date <= ?"""
    params: list = [to_iso(start), to_iso(end)]
    if institution:
        sql += " AND (e.institution = ? OR e.secondment_to = ?)"
        params.extend([institution, institution])
    sql += " ORDER BY l.start_date"
    out = []
    for row in conn.execute(sql, params).fetchall():
        data = dict(row)
        emp = Employee(
            emp_id=data["emp_id"],
            name=data.pop("emp_name") or "",
            job_title=data.pop("emp_job") or "",
            institution=data.pop("emp_inst") or "",
        )
        out.append((emp, _row_to_leave(data)))
    return out


def _employee_institution(conn: sqlite3.Connection, emp_id: str) -> str:
    if not emp_id:
        return ""
    row = conn.execute("SELECT institution FROM employees WHERE emp_id=?", (emp_id,)).fetchone()
    return str(row[0] or "") if row else ""


def add_leave(conn: sqlite3.Connection, emp_id: str, fields: dict, user: str = "") -> int:
    with conn:
        conn.execute(
            """INSERT INTO leaves
            (emp_id, type, start_date, end_date, from_date, amount, unit, days_actual,
             working_days, count_mode, order_num, order_date, outside_balance, reason,
             added_date, status, approved_by, approved_at, created_by, modified_at,
             modified_by, is_adjustment, manual_days, uid, institution)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                emp_id,
                fields.get("type", ""),
                fields.get("start_date", ""),
                fields.get("end_date", ""),
                fields.get("from_date", fields.get("start_date", "")),
                fields.get("amount", 0),
                fields.get("unit", "يوم"),
                fields.get("days_actual", 0),
                fields.get("working_days", 0),
                fields.get("count_mode", "calendar"),
                fields.get("order", ""),
                fields.get("order_date", ""),
                int(fields.get("outside_balance", False)),
                fields.get("reason", ""),
                fields.get("added_date") or _now(),
                fields.get("status", "approved"),
                fields.get("approved_by", ""),
                fields.get("approved_at", ""),
                user,
                fields.get("modified_at") or _now(),
                user,
                int(fields.get("is_adjustment", False)),
                int(fields.get("manual_days", False)),
                fields.get("uid") or uuid.uuid4().hex,
                fields.get("institution") or _employee_institution(conn, emp_id),
            ),
        )
        leave_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    log_action(
        conn,
        user,
        "إضافة",
        "leave",
        str(leave_id),
        f"{emp_id} - {fields.get('type', '')} - {fields.get('days_actual', 0)} يوم",
    )
    return leave_id


def update_leave(conn: sqlite3.Connection, leave_id: int, fields: dict, user: str = "") -> None:
    """تعديل إجازة: لا يمسّ تاريخ الإضافة ولا منشئ السجل (يُسجَّل التعديل في modified_*)."""
    current = get_leave(conn, leave_id)
    emp_id = str(fields.get("emp_id") or (current.emp_id if current else ""))
    with conn:
        conn.execute(
            """UPDATE leaves SET type=?, start_date=?, end_date=?, from_date=?,
                     amount=?, unit=?, days_actual=?, working_days=?, count_mode=?,
                     order_num=?, order_date=?, outside_balance=?, reason=?, status=?,
                     is_adjustment=?, manual_days=?, modified_at=?, modified_by=?,
                     institution=COALESCE(NULLIF(institution, ''), ?)
                     WHERE id=?""",
            (
                fields.get("type", ""),
                fields.get("start_date", ""),
                fields.get("end_date", ""),
                fields.get("from_date", fields.get("start_date", "")),
                fields.get("amount", 0),
                fields.get("unit", "يوم"),
                fields.get("days_actual", 0),
                fields.get("working_days", 0),
                fields.get("count_mode", "calendar"),
                fields.get("order", ""),
                fields.get("order_date", ""),
                int(fields.get("outside_balance", False)),
                fields.get("reason", ""),
                fields.get("status", "approved"),
                int(fields.get("is_adjustment", False)),
                int(fields.get("manual_days", False)),
                _now(),
                user,
                fields.get("institution") or _employee_institution(conn, emp_id),
                leave_id,
            ),
        )
    log_action(
        conn,
        user,
        "تعديل",
        "leave",
        str(leave_id),
        f"{fields.get('type', '')} - {fields.get('days_actual', 0)} يوم",
    )


def soft_delete_leave(conn: sqlite3.Connection, leave_id: int, user: str = "", reason: str = "") -> None:
    with conn:
        conn.execute("UPDATE leaves SET deleted_at=?, deleted_by=? WHERE id=?", (_now(), user, leave_id))
    log_action(conn, user, "حذف", "leave", str(leave_id), reason)


def restore_leave(conn: sqlite3.Connection, leave_id: int, user: str = "") -> None:
    with conn:
        conn.execute("UPDATE leaves SET deleted_at=NULL, deleted_by=NULL WHERE id=?", (leave_id,))
    log_action(conn, user, "استعادة", "leave", str(leave_id), "")


def purge_leave(conn: sqlite3.Connection, leave_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM attachments WHERE leave_id=?", (leave_id,))
        conn.execute("DELETE FROM leaves WHERE id=?", (leave_id,))


def void_employee_leaves(
    conn: sqlite3.Connection, emp_id: str, user: str = ""
) -> None:  # pragma: no cover - توافق
    with conn:
        conn.execute(
            "UPDATE leaves SET deleted_at=?, deleted_by=? WHERE emp_id=? AND deleted_at IS NULL",
            (_now(), user, emp_id),
        )


def purge_all_deleted(conn: sqlite3.Connection) -> dict[str, int]:
    """إفراغ سلة المحذوفات نهائياً."""
    with conn:
        leaves = conn.execute(
            "SELECT COUNT(*) FROM leaves WHERE deleted_at IS NOT NULL AND deleted_at<>''"
        ).fetchone()[0]
        emps = conn.execute(
            "SELECT COUNT(*) FROM employees WHERE deleted_at IS NOT NULL AND deleted_at<>''"
        ).fetchone()[0]
        conn.execute("DELETE FROM leaves WHERE deleted_at IS NOT NULL AND deleted_at<>''")
        conn.execute("DELETE FROM employees WHERE deleted_at IS NOT NULL AND deleted_at<>''")
    return {"leaves": leaves, "employees": emps}


# ==================================================================
# المرفقات
# ==================================================================


def list_attachments(conn: sqlite3.Connection, leave_id: int) -> list[Attachment]:
    rows = conn.execute("SELECT * FROM attachments WHERE leave_id=? ORDER BY id", (leave_id,)).fetchall()
    return [Attachment.from_mapping(dict(row)) for row in rows]


def add_attachment(
    conn: sqlite3.Connection,
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
    """يضيف مرفقاً مع بصمة sha256 ومعرّف ثابت لتنتقل المرفقات مع ملفات النقل."""
    leave = get_leave(conn, leave_id) if leave_id else None
    if not sha256 and attachments_dir and stored_name:
        candidate = Path(attachments_dir) / stored_name
        if candidate.exists():
            sha256 = _sha256_file(candidate)
    with conn:
        return add_attachment_row(
            conn,
            leave_id=leave_id,
            emp_id=emp_id,
            filename=filename,
            stored_name=stored_name,
            sha256=sha256,
            leave_uid=(leave.uid if leave else ""),
            institution=institution or (leave.institution if leave else _employee_institution(conn, emp_id)),
            user=user,
        )


def delete_attachment(conn: sqlite3.Connection, attachment_id: int, user: str = "") -> None:
    with conn:
        conn.execute("DELETE FROM attachments WHERE id=?", (attachment_id,))
    log_action(conn, user, "حذف مرفق", "attachment", str(attachment_id), "")


# ==================================================================
# المستخدمون
# ==================================================================


def list_users(conn: sqlite3.Connection) -> list[AppUser]:
    rows = conn.execute("SELECT * FROM app_users ORDER BY username").fetchall()
    return [AppUser.from_mapping(dict(r)) for r in rows]


def get_user(conn: sqlite3.Connection, username: str) -> AppUser | None:
    row = conn.execute("SELECT * FROM app_users WHERE username=?", (username,)).fetchone()
    return AppUser.from_mapping(dict(row)) if row else None


def save_user(conn: sqlite3.Connection, user: AppUser) -> None:
    with conn:
        exists = conn.execute("SELECT 1 FROM app_users WHERE username=?", (user.username,)).fetchone()
        if exists:
            conn.execute(
                """UPDATE app_users SET display_name=?, role=?, institution=?,
                             password_hash=?, salt=?, iterations=?, active=? WHERE username=?""",
                (
                    user.display_name,
                    user.role,
                    user.institution,
                    user.password_hash,
                    user.salt,
                    user.iterations,
                    int(user.active),
                    user.username,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO app_users(username, display_name, role, institution,
                             password_hash, salt, iterations, active, created_at)
                             VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    user.username,
                    user.display_name,
                    user.role,
                    user.institution,
                    user.password_hash,
                    user.salt,
                    user.iterations,
                    int(user.active),
                    _now(),
                ),
            )


def delete_user(conn: sqlite3.Connection, username: str) -> None:
    with conn:
        conn.execute("DELETE FROM app_users WHERE username=?", (username,))


def touch_login(conn: sqlite3.Connection, username: str) -> None:
    with conn:
        conn.execute("UPDATE app_users SET last_login=? WHERE username=?", (_now(), username))


# ==================================================================
# خزنة كلمات المرور (مع تشفير تلقائي للقيم الحساسة)
# ==================================================================


def list_vault(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM password_vault ORDER BY id DESC").fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["password"] = crypto.decrypt_secret_text(str(d.get("password") or ""))
        out.append(d)
    return out


def add_vault_entry(
    conn: sqlite3.Connection,
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
    enc_pw = crypto.encrypt_secret_text(password)
    with conn:
        cursor = conn.execute(
            "INSERT INTO password_vault(created_at, kind, label, institution, file_name, "
            "file_path, password, note, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
            (_now(), kind, label, institution, file_name, file_path, enc_pw, note, user or "—"),
        )
        return int(cursor.lastrowid)


def update_vault_entry(conn: sqlite3.Connection, entry_id: int, **fields) -> None:
    allowed = ("kind", "label", "institution", "file_name", "file_path", "password", "note")
    updates = {key: str(fields[key] or "") for key in allowed if key in fields}
    if not updates:
        return
    if "password" in updates:
        updates["password"] = crypto.encrypt_secret_text(updates["password"])
    with conn:
        assignments = ", ".join(f"{key}=?" for key in updates)
        conn.execute(
            f"UPDATE password_vault SET {assignments} WHERE id=?", (*updates.values(), int(entry_id))
        )


def delete_vault_entry(conn: sqlite3.Connection, entry_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM password_vault WHERE id=?", (int(entry_id),))


# ==================================================================
# سجل التدقيق
# ==================================================================


def log_action(
    conn: sqlite3.Connection, username: str, action: str, entity: str, entity_id: str = "", details: str = ""
) -> None:
    try:
        with conn:
            conn.execute(
                """INSERT INTO audit_log(ts, username, action, entity, entity_id, details)
                             VALUES (?,?,?,?,?,?)""",
                (_now(), username or "—", action, entity, str(entity_id), details),
            )
    except sqlite3.DatabaseError as exc:  # pragma: no cover
        LOG.error("تعذّر تسجيل التدقيق: %s", exc)


def list_audit(
    conn: sqlite3.Connection,
    username: str = "",
    action: str = "",
    entity: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 1000,
) -> list[AuditEntry]:
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
    sql = f"SELECT * FROM audit_log WHERE {' AND '.join(conditions)} ORDER BY id DESC LIMIT ?"
    rows = conn.execute(sql, params).fetchall()
    return [
        AuditEntry(
            id=r["id"],
            ts=r["ts"],
            username=r["username"],
            action=r["action"],
            entity=r["entity"],
            entity_id=r["entity_id"],
            details=r["details"],
        )
        for r in rows
    ]


def audit_values(conn: sqlite3.Connection, column: str) -> list[str]:
    if column not in {"username", "action", "entity"}:
        raise ValueError("عمود غير مسموح")
    rows = conn.execute(
        f"SELECT DISTINCT {column} FROM audit_log WHERE {column} IS NOT NULL ORDER BY {column}"
    ).fetchall()
    return [r[0] for r in rows]


# ==================================================================
# صيانة ونُسخ احتياطية
# ==================================================================


def integrity_check(conn: sqlite3.Connection) -> tuple[bool, str]:
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        ok = str(result).lower() == "ok"
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            return False, f"مرجعية معطوبة: {len(fk)} سجل"
        return ok, str(result)
    except sqlite3.DatabaseError as exc:
        return False, str(exc)


def vacuum_db(conn: sqlite3.Connection) -> None:
    conn.execute("VACUUM")


def backup_to(conn: sqlite3.Connection, dest: str | Path, key_hex: str | None = None) -> Path:
    """نسخة احتياطية متسقة عبر واجهة SQLite (آمنة حتى مع وجود كتابة)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if key_hex:
        target = crypto.open_connection(dest, key_hex)
    else:
        target = sqlite3.connect(str(dest))
    try:
        with target:
            conn.backup(target)
    finally:
        target.close()
    return dest


def export_plaintext(conn: sqlite3.Connection, dest: str | Path, key_hex: str | None = None) -> Path:
    """ينسخ القاعدة إلى ملف **غير مشفّر** (للتنقية والتصدير فقط)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    if not key_hex:
        return backup_to(conn, dest, None)
    conn.execute("ATTACH DATABASE ? AS plaintext KEY ''", (str(dest),))
    try:
        conn.execute("SELECT sqlcipher_export('plaintext')")
    finally:
        conn.execute("DETACH DATABASE plaintext")
    return dest


def stats(conn: sqlite3.Connection, path: Path) -> dict:
    live = "(deleted_at IS NULL OR deleted_at='')"
    dead = "(deleted_at IS NOT NULL AND deleted_at<>'')"
    return {
        "employees": conn.execute(f"SELECT COUNT(*) FROM employees WHERE {live}").fetchone()[0],
        "employees_deleted": conn.execute(f"SELECT COUNT(*) FROM employees WHERE {dead}").fetchone()[0],
        "leaves": conn.execute(f"SELECT COUNT(*) FROM leaves WHERE {live}").fetchone()[0],
        "leaves_deleted": conn.execute(f"SELECT COUNT(*) FROM leaves WHERE {dead}").fetchone()[0],
        "institutions": len(distinct_values(conn, "institution")),
        "workplaces": len(distinct_values(conn, "workplace")),
        "attachments": conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0],
        "audit": conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0],
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "schema_version": int(conn.execute("PRAGMA user_version").fetchone()[0]),
        "path": str(path),
    }


# ==================================================================
# المؤسسات (وحدة النقل والدمج)
# ==================================================================


def list_institutions(conn: sqlite3.Connection, active_only: bool = False) -> list[Institution]:
    sql = (
        "SELECT i.*, (SELECT COUNT(*) FROM employees e WHERE e.institution = i.name "
        "AND (e.deleted_at IS NULL OR e.deleted_at='')) AS employees FROM institutions i"
    )
    if active_only:
        sql += " WHERE i.active = 1"
    sql += " ORDER BY i.is_center DESC, i.name"
    return [Institution.from_mapping(dict(row)) for row in conn.execute(sql)]


def get_institution(conn: sqlite3.Connection, name: str) -> Institution | None:
    row = conn.execute("SELECT * FROM institutions WHERE name=?", (name,)).fetchone()
    return Institution.from_mapping(dict(row)) if row else None


def save_institution(conn: sqlite3.Connection, fields: dict, user: str = "") -> Institution:
    name = str(fields.get("name") or "").strip()
    if not name:
        raise ValueError("اسم المؤسسة إلزامي")
    now = _now()
    existing = get_institution(conn, name)
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
    with conn:
        if existing:
            conn.execute(
                """UPDATE institutions SET code=?, kind=?, manager=?, phone=?, address=?,
                             notes=?, is_center=?, username=?, active=?, updated_at=? WHERE name=?""",
                (
                    payload["code"],
                    payload["kind"],
                    payload["manager"],
                    payload["phone"],
                    payload["address"],
                    payload["notes"],
                    payload["is_center"],
                    payload["username"],
                    payload["active"],
                    now,
                    name,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO institutions
                             (name, code, kind, manager, phone, address, notes, is_center,
                              username, active, created_at, updated_at)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    name,
                    payload["code"],
                    payload["kind"],
                    payload["manager"],
                    payload["phone"],
                    payload["address"],
                    payload["notes"],
                    payload["is_center"],
                    payload["username"],
                    payload["active"],
                    now,
                    now,
                ),
            )
    log_action(conn, user or "—", "إضافة" if not existing else "تعديل", "institution", name, payload["kind"])
    return get_institution(conn, name)  # type: ignore[return-value]


def register_institutions(conn: sqlite3.Connection, names, user: str = "") -> list[str]:
    """يتأكد من وجود المؤسسات (يُنشئ الناقص) — تُستخدم عند الدمج والتصدير."""
    created: list[str] = []
    now = _now()
    with conn:
        for raw in names:
            name = str(raw or "").strip()
            if not name:
                continue
            row = conn.execute("SELECT 1 FROM institutions WHERE name=?", (name,)).fetchone()
            if not row:
                conn.execute(
                    """INSERT INTO institutions(name, kind, created_at, updated_at)
                                 VALUES (?,?,?,?)""",
                    (name, "مؤسسة", now, now),
                )
                created.append(name)
    if created and user:
        log_action(conn, user, "إضافة", "institution", ", ".join(created), "أُنشئت تلقائياً عند الاستيراد")
    return created


def delete_institution(conn: sqlite3.Connection, name: str, user: str = "") -> tuple[bool, str]:
    """يحذف مؤسسة ومستخدميها، بشرط ألا يكون لها موظفون وألا تكون المركز."""
    institution = get_institution(conn, name)
    if institution is None:
        return False, "المؤسسة غير موجودة."
    center = center_institution(conn)
    if institution.is_center or center == name:
        return False, "لا يمكن حذف مؤسسة مركز الدائرة."
    employees = conn.execute("SELECT COUNT(*) FROM employees WHERE institution=?", (name,)).fetchone()[0]
    if employees:
        return False, f"لا يمكن الحذف: هناك {employees} موظفاً مرتبطاً بهذه المؤسسة."
    with conn:
        conn.execute("UPDATE app_users SET institution='' WHERE institution=? AND role='admin'", (name,))
        deleted = conn.execute(
            "DELETE FROM app_users WHERE (institution=? OR username=?) AND role<>'admin'",
            (name, institution.username or ""),
        ).rowcount
        conn.execute("DELETE FROM institutions WHERE name=?", (name,))
    log_action(conn, user or "—", "حذف", "institution", name, f"حُذفت المؤسسة و{deleted} مستخدم مرتبط بها")
    return True, f"تم حذف المؤسسة ومستخدمها ({deleted} مستخدم)."


def set_institution_import(
    conn: sqlite3.Connection, name: str, *, when: str, user: str = "", filename: str = "", counts: str = ""
) -> None:
    with conn:
        conn.execute(
            """UPDATE institutions SET last_import_at=?, last_import_user=?,
                         last_import_file=?, last_import_counts=? WHERE name=?""",
            (when, user, filename, counts, name),
        )


def set_institution_export(conn: sqlite3.Connection, name: str, when: str) -> None:
    with conn:
        conn.execute("UPDATE institutions SET last_export_at=? WHERE name=?", (when, name))


def center_institution(conn: sqlite3.Connection) -> str:
    meta = get_meta(conn)
    value = meta.get("center_institution", "")
    if value:
        return value
    row = conn.execute("SELECT name FROM institutions WHERE is_center=1 LIMIT 1").fetchone()
    return row[0] if row else ""


def set_center_institution(conn: sqlite3.Connection, name: str) -> None:
    name = str(name or "").strip()
    with conn:
        conn.execute("UPDATE institutions SET is_center=0")
        if name:
            conn.execute("UPDATE institutions SET is_center=1 WHERE name=?", (name,))
    set_meta(conn, {"center_institution": name})


def institution_employee_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT institution, COUNT(*) FROM employees WHERE (deleted_at IS NULL OR deleted_at='') "
        "GROUP BY institution"
    ).fetchall()
    return {row[0] or "": row[1] for row in rows}


# ==================================================================
# سجل الاستيراد/التصدير
# ==================================================================


def add_import(conn: sqlite3.Connection, record: dict, user: str = "") -> int:
    columns = [
        "ts",
        "username",
        "direction",
        "scope",
        "institution",
        "source_file",
        "checksum",
        "source_schema",
        "source_policy",
        "period_from",
        "period_to",
        "employees_added",
        "employees_updated",
        "employees_unchanged",
        "employees_conflict",
        "leaves_added",
        "leaves_updated",
        "leaves_unchanged",
        "moves",
        "attachments",
        "warnings",
        "report",
    ]
    values = [
        record.get(
            column,
            ""
            if column
            in {
                "ts",
                "username",
                "direction",
                "scope",
                "institution",
                "source_file",
                "checksum",
                "source_policy",
                "period_from",
                "period_to",
                "report",
            }
            else 0,
        )
        for column in columns
    ]
    if not record.get("ts"):
        values[0] = _now()
    if not record.get("username"):
        values[1] = user or "—"
    with conn:
        conn.execute(
            f"INSERT INTO imports ({','.join(columns)}) VALUES ({','.join('?' * len(columns))})", values
        )
        return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def list_imports(
    conn: sqlite3.Connection, limit: int = 50, institution: str = "", direction: str = ""
) -> list[ImportRecord]:
    conditions, params = ["1=1"], []
    if institution:
        conditions.append("institution = ?")
        params.append(institution)
    if direction:
        conditions.append("direction = ?")
        params.append(direction)
    params.append(int(limit))
    rows = conn.execute(
        f"SELECT * FROM imports WHERE {' AND '.join(conditions)} ORDER BY id DESC LIMIT ?", params
    ).fetchall()
    return [ImportRecord.from_mapping(dict(row)) for row in rows]


def get_import(conn: sqlite3.Connection, import_id: int) -> ImportRecord | None:
    row = conn.execute("SELECT * FROM imports WHERE id=?", (import_id,)).fetchone()
    return ImportRecord.from_mapping(dict(row)) if row else None


def last_import_for(conn: sqlite3.Connection, institution: str) -> ImportRecord | None:
    rows = list_imports(conn, limit=1, institution=institution, direction="import")
    return rows[0] if rows else None


def checksum_seen(conn: sqlite3.Connection, checksum: str) -> ImportRecord | None:
    if not checksum:
        return None
    row = conn.execute(
        "SELECT * FROM imports WHERE checksum=? ORDER BY id DESC LIMIT 1", (checksum,)
    ).fetchone()
    return ImportRecord.from_mapping(dict(row)) if row else None


# ==================================================================
# انتقال وتنسيب الموظفين بين المؤسسات
# ==================================================================


def add_move(
    conn: sqlite3.Connection,
    emp_id: str,
    from_institution: str,
    to_institution: str,
    moved_on=None,
    source_file: str = "",
    note: str = "",
    user: str = "",
    *,
    move_type: str = "transfer",
    end_date=None,
) -> int:
    with conn:
        conn.execute(
            """INSERT INTO employee_moves
                         (emp_id, from_institution, to_institution, moved_on, recorded_at,
                          source_file, note, move_type, end_date)
                         VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                emp_id,
                from_institution,
                to_institution,
                to_iso(moved_on),
                _now(),
                source_file,
                note,
                move_type or "transfer",
                to_iso(end_date),
            ),
        )
        return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def list_moves(conn: sqlite3.Connection, emp_id: str = "", limit: int = 200) -> list[EmployeeMove]:
    if emp_id:
        rows = conn.execute(
            "SELECT * FROM employee_moves WHERE emp_id=? ORDER BY id DESC LIMIT ?", (emp_id, int(limit))
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM employee_moves ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    return [EmployeeMove.from_mapping(dict(row)) for row in rows]


def set_employee_institution(
    conn: sqlite3.Connection, emp_id: str, institution: str, moved_on=None, user: str = ""
) -> None:
    with conn:
        conn.execute(
            """UPDATE employees SET previous_institution = institution,
                         institution = ?, moved_on = ?, updated_at = ? WHERE emp_id = ?""",
            (institution, to_iso(moved_on), _now(), emp_id),
        )
    log_action(conn, user, "نقل", "employee", emp_id, f"إلى {institution}")


def set_employee_secondment(
    conn: sqlite3.Connection,
    emp_id: str,
    secondment_to: str,
    start_date=None,
    end_date=None,
    order: str = "",
    user: str = "",
) -> None:
    """تسجيل أو إنهاء تنسيب/تكليف مؤقت للموظف."""
    emp = get_employee(conn, emp_id)
    from_inst = emp.institution if emp else ""
    with conn:
        conn.execute(
            """UPDATE employees SET secondment_to=?, secondment_start=?, secondment_end=?,
                         secondment_order=?, updated_at=? WHERE emp_id=?""",
            (secondment_to, to_iso(start_date), to_iso(end_date), order, _now(), emp_id),
        )
    if secondment_to:
        add_move(
            conn,
            emp_id,
            from_inst,
            secondment_to,
            moved_on=start_date,
            source_file=order or "—",
            note=f"تنسيب إلى {secondment_to}" + (f" حتى {to_iso(end_date)}" if end_date else ""),
            user=user,
            move_type="secondment",
            end_date=end_date,
        )
        log_action(conn, user, "تنسيب", "employee", emp_id, f"إلى {secondment_to}")
    else:
        log_action(conn, user, "إنهاء تنسيب", "employee", emp_id, f"عودة إلى {from_inst}")


# ==================================================================
# بيانات خامة للمقارنة في الدمج
# ==================================================================


def raw_employees(conn: sqlite3.Connection, include_deleted: bool = True) -> dict[str, dict]:
    sql = "SELECT * FROM employees"
    if not include_deleted:
        sql += " WHERE deleted_at IS NULL OR deleted_at=''"
    return {str(row["emp_id"]): dict(row) for row in conn.execute(sql)}


def raw_leaves(conn: sqlite3.Connection, include_deleted: bool = True) -> dict[str, dict]:
    """مفتاح القاموس هو uid الإجازة (أو مفتاح بديل إن غاب)."""
    sql = "SELECT * FROM leaves"
    if not include_deleted:
        sql += " WHERE deleted_at IS NULL OR deleted_at=''"
    result: dict[str, dict] = {}
    for row in conn.execute(sql):
        data = dict(row)
        result[data.get("uid") or _fallback_leave_key(data)] = data
    return result


def raw_attachments(conn: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in conn.execute("SELECT * FROM attachments")]


def get_leave_by_uid(conn: sqlite3.Connection, uid: str) -> Leave | None:
    row = conn.execute("SELECT * FROM leaves WHERE uid=?", (uid,)).fetchone()
    return _row_to_leave(dict(row)) if row else None


def attachment_hashes(conn: sqlite3.Connection) -> dict[str, dict]:
    rows = conn.execute("SELECT * FROM attachments WHERE sha256 IS NOT NULL AND sha256 <> ''").fetchall()
    return {row["sha256"]: dict(row) for row in rows}


def add_attachment_row(
    conn: sqlite3.Connection,
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
    """إدراج مرفق داخل معاملة قائمة (يُستخدم في الدمج والواجهة)."""
    conn.execute(
        """INSERT INTO attachments
                     (leave_id, emp_id, filename, stored_name, added_at, added_by,
                      uid, leave_uid, sha256, institution)
                     VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            leave_id,
            emp_id,
            filename,
            stored_name,
            _now(),
            user,
            uid or uuid.uuid4().hex,
            leave_uid,
            sha256,
            institution,
        ),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def set_transfer_manifest(conn: sqlite3.Connection, values: dict) -> None:
    with conn:
        for key, value in values.items():
            conn.execute(
                "INSERT INTO transfer_manifest(key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(key), str(value)),
            )


def get_transfer_manifest(conn: sqlite3.Connection) -> dict[str, str]:
    try:
        rows = conn.execute("SELECT key, value FROM transfer_manifest").fetchall()
    except sqlite3.DatabaseError:
        return {}
    return {row["key"]: row["value"] for row in rows}
