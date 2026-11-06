"""التصدير والاستيراد عبر Excel (openpyxl) مع أوراق عربية RTL."""

from __future__ import annotations

from pathlib import Path

from .. import config
from ..logging_setup import get_logger
from ..models import Employee
from ..rules import Policy
from ..services import balance as B
from ..services import dates as D

LOG = get_logger("excel")

try:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    HAS_XLSX = True
except ImportError:  # pragma: no cover
    HAS_XLSX = False

HEADER_FILL = "1C2D3E"
HEADER_FONT = "7DD3C8"
ALT_FILL = "F1F5F9"
NEG_FONT = "DC2626"
POS_FONT = "0D9488"


def _check() -> None:
    if not HAS_XLSX:
        raise RuntimeError("مكتبة openpyxl غير مثبتة — لا يمكن التصدير إلى Excel.")


def _build_custom(path: str | Path, headers: list[str], rows: list[list], title: str = "تقرير مخصص") -> Path:
    """تصدير تقرير مخصص إلى Excel."""
    _check()
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = title[:31]
    _style_sheet(sheet, headers, rows)
    path = Path(path)
    workbook.save(path)
    return path


def _style_sheet(
    ws,
    headers: list[str],
    rows: list[list],
    widths: list[int] | None = None,
    negative_columns: tuple[int, ...] = (),
) -> None:
    ws.sheet_view.rightToLeft = True
    ws.append(headers)
    thin = Side(style="thin", color="CBD5E1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for _idx, cell in enumerate(ws[1], start=1):
        cell.font = Font(bold=True, color=HEADER_FONT)
        cell.fill = PatternFill("solid", fgColor=HEADER_FILL)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    for r_i, row in enumerate(rows, start=2):
        ws.append(row)
        for c_i, cell in enumerate(ws[r_i], start=1):
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border
            if r_i % 2 == 0:
                cell.fill = PatternFill("solid", fgColor=ALT_FILL)
            if c_i in negative_columns:
                try:
                    cell.font = Font(bold=True, color=NEG_FONT if float(cell.value) < 0 else POS_FONT)
                except (TypeError, ValueError):
                    pass
    for i, width in enumerate(widths or [], start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"


EMPLOYEE_MASTER_HEADERS = [
    "الرقم الوظيفي",
    "الاسم",
    "العنوان الوظيفي",
    "مكان العمل",
    "المؤسسة/القسم",
    "الجنس",
    "الحالة",
    "تاريخ المباشرة",
    "تاريخ انتهاء الخدمة",
    "ملاحظات",
    "له رصيد افتتاحي",
    "الرصيد الافتتاحي (أيام)",
    "تاريخ احتساب الرصيد",
    "من قام بالحساب",
    "تفاصيل الرصيد",
]
STATUS_LABELS = {"active": "على الملاك", "leave": "بإجازة", "retired": "متقاعد/منتهية خدمته"}


def export_employee_master(path: str | Path, employees: list[Employee]) -> Path:
    """تصدير بيانات الموظفين كاملة (الحقول القابلة للإدخال) إلى Excel."""
    _check()
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "الموظفون"
    rows = []
    for employee in employees:
        rows.append(
            [
                employee.emp_id,
                employee.name,
                employee.job_title,
                employee.workplace,
                employee.institution,
                employee.gender,
                STATUS_LABELS.get(employee.status, employee.status),
                D.to_iso(employee.start_date),
                D.to_iso(employee.end_date),
                employee.notes,
                "نعم" if employee.has_opening_balance else "لا",
                int(employee.opening_balance or 0) if employee.has_opening_balance else "",
                D.to_iso(employee.opening_balance_date) if employee.has_opening_balance else "",
                employee.opening_balance_by if employee.has_opening_balance else "",
                employee.opening_balance_note if employee.has_opening_balance else "",
            ]
        )
    _style_sheet(
        sheet,
        EMPLOYEE_MASTER_HEADERS,
        rows,
        widths=[14, 26, 20, 18, 20, 8, 16, 13, 13, 28, 12, 14, 13, 20, 30],
    )
    path = Path(path)
    workbook.save(path)
    return path


def export_employee_template(path: str | Path) -> Path:
    """قالب فارغ لاستيراد الموظفين بنفس الحقول."""
    _check()
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "الموظفون"
    example = [
        "1001",
        "مثال: أحمد زياد",
        "تقني طبي",
        "المركز الصحي",
        "مستشفى الكرامة",
        "ذكر",
        "على الملاك",
        "2019-04-30",
        "",
        "ملاحظة",
        "نعم",
        20,
        "2025-12-31",
        "اسم المحاسب",
        "آخر رصيد معتمد",
    ]
    _style_sheet(
        sheet,
        EMPLOYEE_MASTER_HEADERS,
        [example],
        widths=[14, 26, 20, 18, 20, 8, 16, 13, 13, 28, 12, 14, 13, 20, 30],
    )
    note = workbook.create_sheet("تعليمات")
    note.sheet_view.rightToLeft = True
    for line in (
        "الأعمدة الإلزامية: الرقم الوظيفي، الاسم، تاريخ المباشرة.",
        "الحالة: على الملاك / بإجازة / متقاعد.",
        "إذا «له رصيد افتتاحي = نعم» فيجب إدخال الرصيد وتاريخ الاحتساب ومن قام بالحساب.",
        "الرصيد الافتتاحي هو المتبقي كما في تاريخ الاحتساب، ويُحسب من اليوم التالي.",
        "لا تُدخل إجازات تخصم من الرصيد قبل/عند تاريخ الاحتساب.",
        "الخانات الفارغة في الرصيد الافتتاحي تعني عدم تغيير رصيد الموظف الموجود.",
    ):
        note.append([line])
    note.column_dimensions["A"].width = 100
    path = Path(path)
    workbook.save(path)
    return path


def export_employees(path: str | Path, rows: list[dict], *, title: str = "الموظفون") -> Path:
    _check()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    headers = [
        "الرقم الوظيفي",
        "الاسم",
        "العنوان الوظيفي",
        "مكان العمل",
        "المؤسسة",
        "الجنس",
        "تاريخ المباشرة",
        "انتهاء الخدمة",
        "أيام الخدمة",
        "خارج الرصيد",
        "أيام الدوام المحسوبة",
        "المستحقة",
        "المأخوذة",
        "الرصيد",
        "عدد الإجازات",
        "ملاحظات",
    ]
    data = [
        [
            r["emp_id"],
            r["name"],
            r["job_title"],
            r["workplace"],
            r["institution"],
            r["gender"],
            r["start_date"],
            r.get("end_date", ""),
            r["raw_days"],
            r["outside"],
            r["net_days"],
            r["earned"],
            r["taken"],
            r["balance"],
            r.get("leaves_count", 0),
            r.get("notes", ""),
        ]
        for r in rows
    ]
    _style_sheet(
        ws,
        headers,
        data,
        widths=[14, 26, 20, 18, 20, 8, 13, 13, 11, 12, 16, 10, 10, 10, 11, 28],
        negative_columns=(14,),
    )
    path = Path(path)
    wb.save(path)
    return path


def export_leaves(path: str | Path, employee: Employee, policy: Policy, today=None) -> Path:
    _check()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "سجل الإجازات"
    headers = [
        "#",
        "النوع",
        "من",
        "إلى",
        "العدد",
        "الوحدة",
        "الأيام المؤثرة",
        "أيام العمل",
        "خارج الرصيد",
        "الحالة",
        "الأمر",
        "تاريخ الأمر",
        "السبب",
        "أُضيفت في",
        "أُضيفت بواسطة",
    ]
    leaves = [lv for lv in employee.leaves if not lv.is_deleted]
    data = []
    for i, lv in enumerate(leaves, 1):
        start, end = B.leave_span(lv)
        data.append(
            [
                i,
                lv.type,
                D.to_iso(start),
                D.to_iso(end),
                lv.amount,
                lv.unit,
                lv.days_actual,
                lv.working_days,
                "نعم" if B.is_service_exclusion(policy, lv) else "لا",
                config.LEAVE_STATUS_LABELS.get(lv.status, lv.status),
                lv.order,
                D.to_iso(lv.order_date),
                lv.reason,
                lv.added_date,
                lv.created_by,
            ]
        )
    _style_sheet(ws, headers, data, widths=[5, 16, 13, 13, 9, 8, 13, 11, 12, 12, 16, 13, 26, 18, 14])
    info = wb.create_sheet("ملخص")
    info.sheet_view.rightToLeft = True
    bal = B.compute_balance(employee, employee.leaves, policy, today)
    for label, value in (
        ("الرقم الوظيفي", employee.emp_id),
        ("الاسم", employee.name),
        ("العنوان الوظيفي", employee.job_title),
        ("مكان العمل", employee.workplace),
        ("المؤسسة", employee.institution),
        ("تاريخ المباشرة", D.to_iso(employee.start_date)),
        ("أيام الخدمة الكلية", bal.raw_days),
        ("أيام خارج الرصيد", bal.outside),
        ("أيام الدوام المحسوبة", bal.net_days),
        ("الإجازات المستحقة", bal.earned),
        ("الإجازات المأخوذة", bal.taken),
        ("الرصيد المتبقي", bal.balance),
    ):
        info.append([label, value])
    info.column_dimensions["A"].width = 24
    info.column_dimensions["B"].width = 24
    for row in info.iter_rows(min_row=1, max_row=info.max_row):
        row[0].font = Font(bold=True)
    path = Path(path)
    wb.save(path)
    return path


def export_alerts(path: str | Path, alerts: list) -> Path:
    _check()
    from ..services.reports import SEVERITY_LABELS

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "التنبيهات"
    headers = ["الأهمية", "الموظف", "الرقم الوظيفي", "المؤسسة", "النوع", "التاريخ", "التنبيه"]
    data = [
        [
            SEVERITY_LABELS.get(a.severity, a.severity),
            a.name,
            a.emp_id,
            a.institution,
            a.kind,
            D.to_iso(a.day),
            a.message,
        ]
        for a in alerts
    ]
    _style_sheet(ws, headers, data, widths=[10, 24, 14, 20, 16, 13, 60])
    path = Path(path)
    wb.save(path)
    return path


def export_audit(path: str | Path, entries: list) -> Path:
    _check()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "سجل التدقيق"
    headers = ["#", "التاريخ والوقت", "المستخدم", "الإجراء", "الكيان", "المعرّف", "التفاصيل"]
    data = [[e.id, e.ts, e.username, e.action, e.entity, e.entity_id, e.details] for e in entries]
    _style_sheet(ws, headers, data, widths=[7, 20, 16, 14, 14, 14, 50])
    path = Path(path)
    wb.save(path)
    return path


def export_statement(
    path: str | Path, employee: Employee, policy: Policy, statement_rows: list[dict], balance
) -> Path:
    _check()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "كشف الحساب"
    headers = [
        "سنة الخدمة",
        "من",
        "إلى",
        "أيام الخدمة",
        "خارج الرصيد",
        "صافي الدوام",
        "المستحق",
        "المأخوذ",
        "منتهي",
        "الرصيد المرحّل",
    ]
    data = [
        [
            r["index"],
            r["start"],
            r["end"],
            r["service_days"],
            r["outside_days"],
            r["net_days"],
            r["earned"],
            r["taken"],
            r["expired"],
            r["carry_out"],
        ]
        for r in statement_rows
    ]
    _style_sheet(ws, headers, data, widths=[12, 13, 13, 13, 13, 13, 10, 10, 10, 14])
    summary = wb.create_sheet("الملخص")
    summary.sheet_view.rightToLeft = True
    rows = [("الاسم", employee.name), ("الرقم الوظيفي", employee.emp_id)]
    if getattr(balance, "has_opening", False):
        rows.extend(
            [
                ("الرصيد الافتتاحي", balance.opening_balance),
                ("تاريخ الاحتساب", D.to_iso(balance.opening_date)),
                ("من قام بالحساب", balance.extra.get("opening_by", "")),
            ]
        )
    rows.extend(
        [
            ("أيام الخدمة الكلية", balance.raw_days),
            ("خارج الرصيد", balance.outside),
            ("الدوام المحسوبة", balance.net_days),
            ("المستحقة بعد الافتتاحي", balance.earned),
            ("المأخوذة بعد الافتتاحي", balance.taken),
            ("الرصيد", balance.balance),
        ]
    )
    for label, value in rows:
        summary.append([label, value])
    summary.column_dimensions["A"].width = 22
    summary.column_dimensions["B"].width = 22
    path = Path(path)
    wb.save(path)
    return path


EMPLOYEE_TEMPLATE_HEADERS = [
    "emp_id",
    "name",
    "job_title",
    "workplace",
    "institution",
    "gender",
    "start_date",
    "end_date",
    "notes",
]


def export_template(path: str | Path) -> Path:
    _check()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "قالب الموظفين"
    ws.sheet_view.rightToLeft = True
    ws.append(EMPLOYEE_TEMPLATE_HEADERS)
    ws.append(
        [
            "1001",
            "مثال: أحمد زياد",
            "تقني طبي",
            "المركز الصحي",
            "دائرة الصحة",
            "ذكر",
            "2019-04-30",
            "",
            "ملاحظة اختيارية",
        ]
    )
    for cell in ws[1]:
        cell.font = Font(bold=True, color=HEADER_FONT)
        cell.fill = PatternFill("solid", fgColor=HEADER_FILL)
    for i, width in enumerate([14, 26, 20, 18, 20, 8, 14, 14, 28], start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    path = Path(path)
    wb.save(path)
    return path


def write_table(
    path: str | Path,
    headers: list[str],
    rows: list[list],
    *,
    sheet: str = "ورقة1",
    widths: list[int] | None = None,
    rtl: bool = True,
) -> Path:
    """كتابة جدول عام إلى Excel (يُستخدم للتقارير والسجلات)."""
    _check()
    path = Path(path)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.sheet_view.rightToLeft = rtl
    ws.append(list(headers))
    for row in rows:
        ws.append(list(row))
    for cell in ws[1]:
        cell.font = Font(bold=True, color=HEADER_FONT)
        cell.fill = PatternFill("solid", fgColor=HEADER_FILL)
        cell.alignment = Alignment(horizontal="center")
    for index, header in enumerate(headers, start=1):
        width = (
            widths[index - 1] if widths and index <= len(widths) else max(12, min(42, len(str(header)) + 8))
        )
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{ws.max_row}"
    wb.save(path)
    return path


def read_table(path: str | Path, sheet: str | None = None) -> tuple[list[str], list[dict]]:
    """قراءة ملف Excel: يعيد (العناوين، الصفوف كقواميس)."""
    _check()
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers_raw = next(rows_iter)
    except StopIteration:
        return [], []
    headers = [str(h).strip() if h is not None else f"عمود{i + 1}" for i, h in enumerate(headers_raw)]
    out = []
    for raw in rows_iter:
        if raw is None or all(v is None or str(v).strip() == "" for v in raw):
            continue
        row = {}
        for i, header in enumerate(headers):
            row[header] = raw[i] if i < len(raw) else None
        out.append(row)
    wb.close()
    return headers, out


def sheet_names(path: str | Path) -> list[str]:
    _check()
    wb = openpyxl.load_workbook(path, read_only=True)
    names = list(wb.sheetnames)
    wb.close()
    return names
