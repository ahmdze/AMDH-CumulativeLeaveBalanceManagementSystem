"""التحقق من صحة المدخلات وكشف التعارضات.

مبدأ مهم: **الرصيد السالب مشروع** حسب الضوابط الإدارية، ولذلك لا يُمنع ولا يُسجَّل كخطأ.
التحقق هنا يخصّ سلامة الإدخال (كميات وأتواريخ وتعليمات مكررة) وكشف التعارضات.
"""

from __future__ import annotations

from datetime import date

from .. import config
from ..models import Balance, Employee, Issue, Leave
from ..rules import Policy
from . import balance as B
from . import dates as D
from ..i18n import tr, trf


# ---------------------------------------------------------------------------
# الموظف
# ---------------------------------------------------------------------------
def validate_employee(fields: dict, emp_id: str, *, edit_mode: bool = False,
                      exists=None) -> list[Issue]:
    issues: list[Issue] = []
    if not emp_id or not str(emp_id).strip():
        issues.append(Issue("error", tr("الرقم الوظيفي إلزامي.")))
    if not (fields.get("name") or "").strip():
        issues.append(Issue("error", tr("الاسم الكامل إلزامي.")))
    if not edit_mode and exists is not None and callable(exists) and exists(emp_id):
        issues.append(Issue("error", tr("الرقم الوظيفي مسجل مسبقاً.")))

    start = D.parse_iso(fields.get("start_date"))
    end = D.parse_iso(fields.get("end_date"))
    if not start:
        issues.append(Issue("error", tr("تاريخ المباشرة إلزامي وبصيغة صحيحة.")))
    else:
        if start > date.today():
            issues.append(Issue("warning", tr("تاريخ المباشرة في المستقبل.")))
    if end and start and end < start:
        issues.append(Issue("error", tr("تاريخ انتهاء الخدمة قبل تاريخ المباشرة.")))
    if fields.get("gender") not in ("ذكر", "أنثى"):
        issues.append(Issue("error", tr("الجنس غير محدد بشكل صحيح.")))
    if fields.get("status") and fields["status"] not in ("active", "leave", "retired"):
        issues.append(Issue("warning", tr("حالة الموظف غير معروفة.")))
    return issues


# ---------------------------------------------------------------------------
# الإجازة
# ---------------------------------------------------------------------------
def validate_leave(leave: Leave, employee: Employee, existing: list[Leave], policy: Policy,
                   leave_id: int | None = None) -> list[Issue]:
    issues: list[Issue] = []
    rule = policy.rule(leave.type)

    if not leave.type:
        issues.append(Issue("error", tr("نوع الإجازة إلزامي.")))
    elif leave.type not in policy.rules:
        issues.append(Issue("warning", trf("النوع «{v0}» غير معرّف في الضوابط، وسيُعامل معاملة اعتيادية.", v0=leave.type)))

    if leave.unit not in config.UNITS:
        issues.append(Issue("error", tr("الوحدة يجب أن تكون يوماً أو شهراً أو سنة.")))

    if leave.is_adjustment or rule.is_adjustment:
        if leave.amount == 0:
            issues.append(Issue("error", tr("قيمة التسوية لا يمكن أن تكون صفراً.")))
        if not (leave.reason or "").strip():
            issues.append(Issue("error", tr("التسوية تتطلب سبباً/سنداً إدارياً.")))
    else:
        if leave.amount is None or leave.amount <= 0:
            issues.append(Issue("error", tr("العدد يجب أن يكون أكبر من صفر (للتسويات استخدم نوع «تسوية رصيد»).")))

    if not leave.start_date:
        issues.append(Issue("error", tr("تاريخ بدء الإجازة إلزامي.")))
    else:
        if employee.start_date and leave.start_date < employee.start_date:
            issues.append(Issue("warning",
                                trf("تاريخ البدء قبل تاريخ المباشرة ({v0}).", v0=D.to_iso(employee.start_date))))
        if employee.end_date and leave.start_date > employee.end_date:
            issues.append(Issue("warning", tr("تاريخ البدء بعد تاريخ انتهاء الخدمة.")))

    if leave.end_date and leave.start_date and leave.end_date < leave.start_date:
        issues.append(Issue("error", tr("تاريخ النهاية قبل تاريخ البداية.")))

    if rule.requires_order and not (leave.order or "").strip():
        issues.append(Issue("error", trf("نوع «{v0}» يتطلب رقم الأمر.", v0=leave.type)))

    if not leave.is_adjustment and leave.days_actual == 0:
        issues.append(Issue("error", tr("الأيام المؤثرة صفر — تحقق من العدد والوحدة والتواريخ.")))

    # تكرار رقم الأمر
    order = (leave.order or "").strip()
    if order:
        for other in existing:
            if other.is_deleted or _same_record(other, leave_id):
                continue
            if (other.order or "").strip() == order:
                issues.append(Issue("warning",
                                    trf("رقم الأمر «{v0}» مستخدم مسبقاً في إجازة ({v1}).", v0=order, v1=D.to_iso(other.start_date))))
                break

    # تقاطع المدى مع إجازات أخرى
    if leave.start_date and not leave.is_adjustment:
        start = leave.start_date
        end = leave.end_date or leave.start_date
        for other in existing:
            if other.is_deleted or other.is_adjustment or _same_record(other, leave_id):
                continue
            if other.status == "rejected":
                continue
            o_start, o_end = B.leave_span(other)
            if D.overlaps(start, end, o_start, o_end):
                issues.append(Issue("warning",
                                    trf("تتقاطع مع إجازة «{v0}» من {v1} إلى {v2}.", v0=other.type, v1=D.to_iso(o_start), v2=D.to_iso(o_end))))
                break

    # السقف الخاص بالنوع
    if rule.quota_days and not leave.is_adjustment:
        used = quota_used(leave.type, leave, existing, rule.quota_period, leave_id)
        if used + max(0, leave.days_actual) > rule.quota_days:
            issues.append(Issue("warning",
                                f"تجاوز السقف المحدد للنوع «{leave.type}» ({rule.quota_days} يوم): "
                                f"المستخدم {used} يوم."))
    return issues


def _same_record(leave: Leave, leave_id: int | None) -> bool:
    """هل هذا هو السجل نفسه الذي يُعدَّل؟ (آمن عندما يكون المعرّف None)."""
    return leave_id is not None and leave.id == leave_id


def quota_used(leave_type: str, candidate: Leave, existing: list[Leave],
               period: str, leave_id: int | None = None) -> int:
    total = 0
    ref = candidate.start_date
    for lv in existing:
        if lv.is_deleted or lv.type != leave_type or lv.status == "rejected":
            continue
        if _same_record(lv, leave_id):
            continue
        if period == "year" and ref and lv.start_date and lv.start_date.year != ref.year:
            continue
        total += max(0, int(lv.days_actual or 0))
    return total


# ---------------------------------------------------------------------------
# معاينة الرصيد بعد التسجيل (بلا حوارات ولا مخاطر)
# ---------------------------------------------------------------------------
def preview_balance(employee: Employee, existing: list[Leave], policy: Policy,
                    candidate: Leave | None, today: date | None = None,
                    include_pending: bool = True, exclude_id: int | None = None) -> Balance:
    items = []
    for lv in existing:
        if lv.is_deleted:
            continue
        if exclude_id is not None and lv.id == exclude_id:
            continue
        if candidate is not None and (lv is candidate or
                                      (candidate.id is not None and lv.id == candidate.id)):
            continue
        items.append(lv)
    if candidate is not None:
        items.append(candidate)
    return B.compute_balance(employee, items, policy, today, include_pending=include_pending)


def balance_note(balance: Balance, policy: Policy) -> tuple[str, str]:
    """يعيد (نص توضيحي، مفتاح لون) لعرض الرصيد في الواجهة.

    الرصيد السالب لا يُعرض كخطأ: يُعرض كمعلومة نظامية.
    """
    if balance.extra.get("no_start_date"):
        return "لا يوجد تاريخ مباشرة — تعذّر الحساب", "muted"
    if balance.balance < 0:
        return "رصيد سالب (مسموح حسب الضوابط الإدارية)", "neg"
    if balance.balance <= policy.low_balance_days:
        return "رصيد منخفض", "gold"
    return "الرصيد سليم", "pos"


# ---------------------------------------------------------------------------
# استيراد الموظفين من Excel
# ---------------------------------------------------------------------------
def validate_import_row(row: dict, existing_ids: set[str], seen_ids: set[str]) -> list[Issue]:
    issues: list[Issue] = []
    emp_id = str(row.get("emp_id") or "").strip()
    if not emp_id:
        issues.append(Issue("error", tr("الرقم الوظيفي فارغ.")))
    elif emp_id in seen_ids:
        issues.append(Issue("error", tr("الرقم الوظيفي مكرر داخل الملف.")))
    elif emp_id in existing_ids:
        issues.append(Issue("info", tr("الموظف موجود مسبقاً (سيُحدَّث حسب الوضع المختار).")))
    if not str(row.get("name") or "").strip():
        issues.append(Issue("error", tr("الاسم فارغ.")))
    if not D.parse_iso(row.get("start_date")):
        issues.append(Issue("error", tr("تاريخ المباشرة غير صالح.")))
    if row.get("gender") not in ("ذكر", "أنثى", None, ""):
        issues.append(Issue("error", tr("الجنس يجب أن يكون «ذكر» أو «أنثى».")))
    return issues
