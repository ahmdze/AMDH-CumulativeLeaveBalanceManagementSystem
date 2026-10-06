"""إدارة المؤسسات: إنشاء/تعديل، استيراد وتصدير Excel، ومستخدم مرتبط تلقائياً.

المبدأ: كل مؤسسة لها مستخدم مرتبط بها (دور «مدخل بيانات») مقيَّد بمؤسسته، فيستطيع
إدخال موظفي مؤسسته وإجازاتهم وتصدير ملف نقل ليستورده مدير المركز.
"""

from __future__ import annotations

import random
import re
import string
from datetime import date, datetime
from pathlib import Path

from ..exporters import excel as X
from ..logging_setup import get_logger
from ..models import AppUser, Institution, Issue
from . import security as sec

LOG = get_logger("institutions")

# حقول ملف Excel
INSTITUTION_FIELDS: list[tuple[str, str, list[str]]] = [
    ("name", "اسم المؤسسة *", ["name", "اسم المؤسسة", "المؤسسة", "الاسم", "institution"]),
    ("code", "الرمز", ["code", "الرمز", "الكود", "رمز المؤسسة", "id"]),
    ("kind", "النوع", ["kind", "النوع", "نوع المؤسسة", "التصنيف"]),
    ("manager", "المدير/المسؤول", ["manager", "المدير", "المسؤول", "مدير المؤسسة"]),
    ("phone", "الهاتف", ["phone", "الهاتف", "الموبايل", "رقم الهاتف"]),
    ("address", "العنوان", ["address", "العنوان", "الموقع"]),
    ("notes", "ملاحظات", ["notes", "ملاحظات", "الملاحظات"]),
    ("username", "اسم المستخدم", ["username", "اسم المستخدم", "المستخدم"]),
    ("active", "مُفعَّلة", ["active", "مفعلة", "مُفعَّلة", "الحالة"]),
]

KINDS = ("مركز الدائرة", "مستشفى", "مركز صحي", "قسم", "مؤسسة")
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


# ---------------------------------------------------------------------------
# أدوات
# ---------------------------------------------------------------------------
def generate_password(length: int = 8) -> str:
    return "".join(random.choice(PASSWORD_ALPHABET) for _ in range(length))


def slugify(value: str, fallback: str = "inst") -> str:
    """يحوّل الرمز إلى اسم مستخدم لاتيني صالح (a-z0-9._-)."""
    text = re.sub(r"[^A-Za-z0-9._-]+", "", str(value or "").strip().lower())
    return text or fallback


def unique_username(db, base: str) -> str:
    candidate = slugify(base)
    if not candidate or candidate == "inst":
        candidate = "inst"
    existing = {user.username.lower() for user in db.list_users()}
    if candidate.lower() not in existing:
        return candidate
    index = 2
    while f"{candidate}{index}".lower() in existing:
        index += 1
    return f"{candidate}{index}"


def suggest_code(db, name: str) -> str:
    """يقترح رمزاً فريداً للمؤسسة (يُستخدم في اسم المستخدم)."""
    existing = {inst.code for inst in db.list_institutions() if inst.code}
    base = slugify(name, "inst").upper()[:6] or "INST"
    candidate = base
    index = 2
    while candidate in existing:
        candidate = f"{base}{index}"
        index += 1
    return candidate


def institution_rows(db) -> list[list]:
    """صفوف جاهزة للتصدير/العرض."""
    status = {item["name"]: item for item in institutions_status(db)}
    rows = []
    for inst in db.list_institutions():
        info = status.get(inst.name, {})
        rows.append([
            inst.name, inst.code, inst.kind, inst.manager, inst.phone, inst.address,
            inst.notes, inst.username, "نعم" if inst.active else "لا", inst.employees,
            inst.last_import_at or "—",
            "نعم" if info.get("reported_this_month") else "لا",
            inst.last_export_at or "—",
            "مركز الدائرة" if inst.is_center else "",
        ])
    return rows


EXPORT_HEADERS = ["اسم المؤسسة", "الرمز", "النوع", "المدير/المسؤول", "الهاتف", "العنوان",
                  "ملاحظات", "اسم المستخدم", "مُفعَّلة", "عدد الموظفين", "آخر استيراد",
                  "أرسلت هذا الشهر", "آخر تصدير", "مركز الدائرة"]


def export_excel(path: str | Path, db) -> Path:
    path = Path(path)
    if not X.HAS_XLSX:
        raise RuntimeError("مكتبة openpyxl غير مثبتة.")
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "المؤسسات"
    sheet.sheet_view.rightToLeft = True
    sheet.append(EXPORT_HEADERS)
    for row in institution_rows(db):
        sheet.append(row)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="7DD3C8")
        cell.fill = PatternFill("solid", fgColor="1C2D3E")
        cell.alignment = Alignment(horizontal="center")
    widths = [28, 10, 14, 20, 14, 22, 24, 16, 10, 12, 18, 14, 18, 14]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    if len(institution_rows(db)):
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(EXPORT_HEADERS))}{sheet.max_row}"
    workbook.save(path)
    return path


def export_template(path: str | Path) -> Path:
    path = Path(path)
    if not X.HAS_XLSX:
        raise RuntimeError("مكتبة openpyxl غير مثبتة.")
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "المؤسسات"
    sheet.sheet_view.rightToLeft = True
    sheet.append(["name", "code", "kind", "manager", "phone", "address", "notes", "username",
                  "active"])
    sheet.append(["مستشفى الكرامة", "H1", "مستشفى", "د. علي حسين", "07701234567",
                  "مركز المدينة", "ملاحظة اختيارية", "", "نعم"])
    sheet.append(["مركز صحي النور", "PH2", "مركز صحي", "د. سارة", "", "", "", "", "نعم"])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="7DD3C8")
        cell.fill = PatternFill("solid", fgColor="1C2D3E")
        cell.alignment = Alignment(horizontal="center")
    for index, width in enumerate([28, 10, 14, 20, 14, 22, 24, 16, 10], start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    workbook.save(path)
    return path


def read_excel(path: str | Path) -> tuple[list[str], list[dict]]:
    return X.read_table(path)


def guess_mapping(headers: list[str]) -> dict[str, str]:
    """يخمّن ربط أعمدة الملف بحقول المؤسسة (عربي/إنجليزي)."""
    mapping: dict[str, str] = {}
    lowered = {header.strip().lower(): header for header in headers}
    for key, _label, synonyms in INSTITUTION_FIELDS:
        found = ""
        for synonym in synonyms:
            if synonym.strip().lower() in lowered:
                found = lowered[synonym.strip().lower()]
                break
        if not found:
            for header in headers:
                if any(synonym.strip().lower() in header.strip().lower() for synonym in synonyms):
                    found = header
                    break
        mapping[key] = found
    return mapping


def normalize_row(raw: dict, mapping: dict[str, str]) -> dict:
    """يحوّل صفاً خاماً إلى حقول مؤسسة بالأنواع الصحيحة."""
    def value(key: str) -> str:
        header = mapping.get(key)
        if not header:
            return ""
        item = raw.get(header)
        return str(item).strip() if item is not None else ""

    active_text = value("active").strip().lower()
    active = active_text not in {"لا", "0", "false", "no", "معطلة", "معطّلة", "غير مفعلة"}
    kind = value("kind") or "مستشفى"
    if kind not in KINDS:
        kind = "مؤسسة"
    return {
        "name": value("name"),
        "code": value("code"),
        "kind": kind,
        "manager": value("manager"),
        "phone": value("phone"),
        "address": value("address"),
        "notes": value("notes"),
        "username": value("username"),
        "active": active,
    }


def validate_row(row: dict, existing_names: set[str], seen: set[str]) -> list[Issue]:
    issues: list[Issue] = []
    name = str(row.get("name") or "").strip()
    if not name:
        issues.append(Issue("error", "اسم المؤسسة فارغ."))
    elif name in seen:
        issues.append(Issue("error", "اسم المؤسسة مكرر داخل الملف."))
    elif name in existing_names:
        issues.append(Issue("info", "المؤسسة موجودة مسبقاً (ستُحدَّث بياناتها)."))
    return issues


# ---------------------------------------------------------------------------
# المستخدم المرتبط
# ---------------------------------------------------------------------------
def create_user_for_institution(db, institution: Institution, *, password: str = "",
                                role: str = "editor", user: str = "") -> tuple[AppUser, str]:
    """ينشئ (أو يحدّث) مستخدماً مرتبطاً بالمؤسسة ويعيده مع كلمة المرور الصريحة."""
    if not institution.code:
        institution.code = suggest_code(db, institution.name)
    username = institution.username or unique_username(db, institution.code or institution.name)
    explicit = password or generate_password()
    existing = db.get_user(username)
    if existing:
        # إعادة تعيين كلمة المرور وربط المؤسسة والدور
        existing.password_hash, existing.salt, existing.iterations = sec.hash_password(explicit)
        existing.display_name = institution.name
        existing.role = role
        existing.institution = institution.name
        existing.active = True
        db.save_user(existing)
        account = existing
    else:
        password_hash, salt, iterations = sec.hash_password(explicit)
        account = AppUser(username=username, display_name=institution.name, role=role,
                          institution=institution.name, password_hash=password_hash, salt=salt,
                          iterations=iterations, active=True)
        db.save_user(account)
    institution.username = username
    db.save_institution(institution.to_fields(), user)
    db.log(user or "—", "مستخدم مؤسسة", "user", username, f"مرتبط بـ {institution.name}")
    return account, explicit


# ---------------------------------------------------------------------------
# الاستيراد من Excel
# ---------------------------------------------------------------------------
def import_from_rows(db, rows: list[dict], mapping: dict[str, str], *, user: str = "",
                     create_users: bool = True, password_mode: str = "generate",
                     unified_password: str = "", update_existing: bool = True) -> dict:
    """ينشئ/يحدّث المؤسسات من صفوف Excel، وينشئ مستخدماً لكل مؤسسة جديدة."""
    result = {"added": 0, "updated": 0, "skipped": 0, "users": [], "errors": []}
    existing = {inst.name: inst for inst in db.list_institutions()}
    seen: set[str] = set()
    for index, raw in enumerate(rows, start=1):
        row = normalize_row(raw, mapping)
        issues = validate_row(row, set(existing), seen)
        seen.add(str(row.get("name") or ""))
        errors = [issue.message for issue in issues if issue.is_error]
        if errors:
            result["skipped"] += 1
            result["errors"].append(f"صف {index}: " + " ".join(errors))
            continue
        name = row["name"]
        current = existing.get(name)
        if current and not update_existing:
            result["skipped"] += 1
            continue
        if current and not row.get("code"):
            row["code"] = current.code
        if not row.get("code"):
            row["code"] = suggest_code(db, name)
        merged = dict(current.to_fields()) if current else {}
        merged.update(row)
        if current:
            merged["username"] = current.username
        institution = db.save_institution(merged, user)
        result["updated" if current else "added"] += 1
        if create_users:
            password = unified_password if password_mode == "unified" else ""
            account, plain = create_user_for_institution(db, institution, password=password,
                                                         user=user)
            result["users"].append({"institution": name, "username": account.username,
                                    "password": plain if password_mode != "unified" else "موحّدة"})
    return result


def credentials_rows(users: list[dict]) -> list[list]:
    return [[item["institution"], item["username"], item["password"]] for item in users]


def export_credentials(path: str | Path, users: list[dict]) -> Path:
    """ملف Excel ببيانات دخول المستخدمين المُنشأين (لتوزيعها على المؤسسات)."""
    path = Path(path)
    if not X.HAS_XLSX:
        raise RuntimeError("مكتبة openpyxl غير مثبتة.")
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "بيانات الدخول"
    sheet.sheet_view.rightToLeft = True
    sheet.append(["اسم المؤسسة", "اسم المستخدم", "كلمة المرور"])
    for item in users:
        sheet.append([item["institution"], item["username"], item["password"]])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="7DD3C8")
        cell.fill = PatternFill("solid", fgColor="1C2D3E")
        cell.alignment = Alignment(horizontal="center")
    for index, width in enumerate([30, 20, 20], start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    workbook.save(path)
    return path


# ---------------------------------------------------------------------------
# حالة الإرسال الشهري
# ---------------------------------------------------------------------------
def institutions_status(db, month: str = "") -> list[dict]:
    """حالة كل مؤسسة: هل أرسلت بياناتها هذا الشهر؟ ومتى آخر استيراد؟"""
    today = date.today()
    month = month or today.strftime("%Y-%m")
    rows: list[dict] = []
    for inst in db.list_institutions():
        last = inst.last_import_at or ""
        recorded = db.last_import_for(inst.name)
        rows.append({
            "name": inst.name,
            "code": inst.code,
            "kind": inst.kind,
            "employees": inst.employees,
            "last_import_at": last,
            "last_import_user": inst.last_import_user,
            "last_import_file": inst.last_import_file,
            "reported_this_month": last.startswith(month),
            "last_record_id": recorded.id if recorded else None,
            "is_center": inst.is_center,
            "active": inst.active,
        })
    return rows


def pending_institutions(db, month: str = "") -> list[dict]:
    """المؤسسات التي لم تُرسل بياناتها في الشهر المطلوب (باستثناء مركز الدائرة)."""
    return [row for row in institutions_status(db, month)
            if not row["reported_this_month"] and not row["is_center"] and row["active"]]


def month_label(month: str = "") -> str:
    month = month or date.today().strftime("%Y-%m")
    try:
        parsed = datetime.strptime(month, "%Y-%m")
        return parsed.strftime("%m/%Y")
    except ValueError:
        return month
