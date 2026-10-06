"""تصدير PDF بالعربية (reportlab + arabic_reshaper + python-bidi).

يُبحث عن الخط العربي تلقائياً في مسارات النظام بدل الاعتماد على وجود arial.ttf
في مجلد التشغيل (سبب فشل التصدير في الإصدار السابق).
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from .. import config
from ..logging_setup import get_logger
from ..models import Employee
from ..rules import Policy
from ..services import balance as B
from ..services import dates as D

LOG = get_logger("pdf")

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    HAS_PDF = True
except ImportError:  # pragma: no cover
    HAS_PDF = False

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    HAS_BIDI = True
except ImportError:  # pragma: no cover
    HAS_BIDI = False

FONT_NAME = "ArabicFont"
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]
_registered: str | None = None
_tried = False


def register_font() -> str | None:
    """يسجّل أول خط عربي متاح. يعيد اسم الخط أو None."""
    global _registered, _tried
    if _registered or _tried:
        return _registered
    _tried = True
    if not HAS_PDF:
        return None
    candidates = list(_FONT_CANDIDATES) + [str(p) for p in Path(".").glob("*.ttf")]
    for candidate in candidates:
        if not os.path.exists(candidate):
            continue
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, candidate))
            _registered = FONT_NAME
            LOG.info("خط PDF: %s", candidate)
            return _registered
        except Exception:  # pragma: no cover
            continue
    LOG.warning("لم يُعثر على خط عربي لتصدير PDF")
    return None


def ar(text) -> str:
    """تهيئة النص العربي للعرض في PDF (تشكيل + اتجاه)."""
    if text is None:
        return ""
    text = str(text)
    if not text:
        return ""
    if HAS_BIDI:
        try:
            return get_display(arabic_reshaper.reshape(text))
        except Exception:  # pragma: no cover
            return text
    return text


def available() -> tuple[bool, str]:
    if not HAS_PDF:
        return False, "مكتبة reportlab غير مثبتة."
    if not HAS_BIDI:
        return False, "لتصدير PDF بالعربية ثبّت: pip install arabic-reshaper python-bidi"
    if not register_font():
        return False, "لم يُعثر على خط عربي (TTF) في النظام."
    return True, ""


def _styles():
    base = getSampleStyleSheet()
    title = ParagraphStyle("ArTitle", parent=base["Title"], fontName=FONT_NAME, fontSize=15, alignment=1)
    info = ParagraphStyle("ArInfo", parent=base["Normal"], fontName=FONT_NAME, fontSize=10, alignment=1)
    return title, info


def _build(path: Path, title: str, subtitle: str, headers: list[str], rows: list[list],
           landscape_mode: bool = True, widths: list[float] | None = None) -> Path:
    _, info_style = _styles()
    pagesize = landscape(A4) if landscape_mode else A4
    doc = SimpleDocTemplate(str(path), pagesize=pagesize,
                            rightMargin=1.2 * cm, leftMargin=1.2 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    story = [Paragraph(ar(title), _styles()[0]), Spacer(1, 0.2 * cm)]
    if subtitle:
        story.append(Paragraph(ar(subtitle), info_style))
        story.append(Spacer(1, 0.3 * cm))
    data = [[ar(h) for h in reversed(headers)]]
    for row in rows:
        data.append([ar(v) for v in reversed(row)])
    table = Table(data, repeatRows=1, colWidths=widths)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1C2D3E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#7DD3C8")),
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94A3B8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(ar(f"تاريخ التقرير: {D.to_iso(date.today())} — {config.APP_NAME}"),
                           info_style))
    doc.build(story)
    return path


def export_employee_leaves(path: str | Path, employee: Employee, policy: Policy) -> Path:
    ok, message = available()
    if not ok:
        raise RuntimeError(message)
    bal = B.compute_balance(employee, employee.leaves, policy)
    headers = ["#", "النوع", "من", "إلى", "العدد", "الأيام المؤثرة", "خارج الرصيد", "الحالة", "الأمر", "السبب"]
    rows = []
    for i, lv in enumerate([x for x in employee.leaves if not x.is_deleted], 1):
        start, end = B.leave_span(lv)
        rows.append([i, lv.type, D.to_iso(start), D.to_iso(end), f"{lv.amount} {lv.unit}",
                     lv.days_actual, "نعم" if B.is_service_exclusion(policy, lv) else "لا",
                     config.LEAVE_STATUS_LABELS.get(lv.status, lv.status), lv.order, lv.reason])
    subtitle = (f"{employee.job_title} - {employee.name} | الرقم الوظيفي: {employee.emp_id} | "
                f"المؤسسة: {employee.institution} | الخدمة: {bal.net_days} يوم | المستحقة: {bal.earned} | "
                f"المأخوذة: {bal.taken} | الرصيد: {bal.balance} يوم")
    return _build(Path(path), f"سجل إجازات: {employee.name}", subtitle, headers, rows)


def export_report(path: str | Path, rows: list[dict], policy: Policy,
                  title: str = "تقرير الأرصدة التراكمية", institution: str = "") -> Path:
    ok, message = available()
    if not ok:
        raise RuntimeError(message)
    headers = ["#", "الرقم الوظيفي", "الاسم", "العنوان الوظيفي", "المؤسسة",
               "أيام الخدمة", "خارج الرصيد", "الدوام المحسوبة", "المستحقة", "المأخوذة", "الرصيد"]
    data = [[i, r["emp_id"], r["name"], r["job_title"], r["institution"], r["raw_days"],
             r["outside"], r["net_days"], r["earned"], r["taken"], r["balance"]]
            for i, r in enumerate(rows, 1)]
    subtitle = (f"النطاق: {institution or 'كل المؤسسات'} | عدد الموظفين: {len(rows)} | "
                f"إجمالي الرصيد: {sum(r['balance'] for r in rows)} يوم | {policy.annual_rate_note}")
    return _build(Path(path), title, subtitle, headers, data)


def export_statement(path: str | Path, employee: Employee, policy: Policy, statement_rows: list[dict],
                     balance) -> Path:
    ok, message = available()
    if not ok:
        raise RuntimeError(message)
    headers = ["سنة الخدمة", "من", "إلى", "أيام الخدمة", "خارج الرصيد", "صافي الدوام",
               "المستحق", "المأخوذ", "منتهي", "الرصيد المرحّل"]
    data = [[r["index"], r["start"], r["end"], r["service_days"], r["outside_days"], r["net_days"],
             r["earned"], r["taken"], r["expired"], r["carry_out"]] for r in statement_rows]
    subtitle = (f"{employee.name} | الرقم الوظيفي: {employee.emp_id} | المستحقة: {balance.earned} | "
                f"المأخوذة: {balance.taken} | الرصيد: {balance.balance} يوم")
    return _build(Path(path), "كشف حساب الرصيد التراكمي", subtitle, headers, data, landscape_mode=False)
