"""تصدير تقارير HTML جاهزة للطباعة (مع تهريب آمن لكل بيانات المستخدم)."""

from __future__ import annotations

import html
import webbrowser
from datetime import date
from pathlib import Path

from .. import config
from ..models import Employee
from ..rules import Policy
from ..services import balance as B
from ..services import dates as D

_PRINT_CSS = """
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Tahoma, Arial, sans-serif; direction: rtl; margin: 24px; color: #16213a; }
h1 { font-size: 20px; border-bottom: 3px solid #0D9488; padding-bottom: 8px; color: #0f3460; }
h2 { font-size: 16px; color: #0f3460; margin-bottom: 6px; }
table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 12px; }
th, td { border: 1px solid #cbd5e1; padding: 6px 8px; text-align: center; }
th { background: #1C2D3E; color: #7dd3c8; }
tr:nth-child(even) td { background: #f8fafc; }
.grid { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 12px; }
.item { min-width: 150px; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 10px; }
.item label { display: block; font-size: 11px; color: #64748b; }
.item span { font-size: 14px; font-weight: bold; }
.neg { color: #dc2626; }
.pos { color: #0d9488; }
.muted { color: #64748b; font-size: 11px; }
.balance { font-size: 20px; }
.signatures { display: flex; justify-content: space-between; margin-top: 48px; font-size: 13px; font-weight: bold; }
.toolbar { margin: 0 0 16px; }
.toolbar button { padding: 8px 16px; font-size: 14px; cursor: pointer; border-radius: 6px;
                  border: 1px solid #0d9488; background: #0d9488; color: #fff; font-weight: bold; }
tr.group td { background: #e2e8f0; font-weight: bold; text-align: right; }
@media print {
    .toolbar { display: none; }
    body { margin: 10px; }
    tr { break-inside: avoid; page-break-inside: avoid; }
    thead { display: table-header-group; }
}
"""


def esc(value) -> str:
    """تهريب آمن: يمنع كسر التقرير أو حقن وسوم من بيانات المستخدم."""
    return html.escape("" if value is None else str(value), quote=True)


def _page(title: str, body: str, auto_print: bool = True) -> str:
    script = (
        (
            "<script>window.addEventListener('load',function(){"
            "setTimeout(function(){window.print();},250);});</script>"
        )
        if auto_print
        else ""
    )
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{_PRINT_CSS}</style>
</head>
<body>
<div class="toolbar"><button onclick="window.print()">🖨 طباعة / حفظ PDF</button></div>
{body}
<p class="muted">تاريخ التقرير: {esc(date.today().strftime("%Y-%m-%d"))} — {esc(config.APP_NAME)}</p>
{script}
</body>
</html>"""


def save_and_open(content: str, reports_dir: Path, filename: str) -> Path:
    """يحفظ التقرير في مجلد التقارير ويفتحه في المتصفح برابط مطلق صحيح."""
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / filename
    path.write_text(content, encoding="utf-8")
    try:
        webbrowser.open(path.resolve().as_uri())
    except Exception:  # pragma: no cover
        pass
    return path


def save(content: str, reports_dir: Path, filename: str) -> Path:
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# التقارير
# ---------------------------------------------------------------------------
def global_report_html(
    rows: list[dict], policy: Policy, title: str = "تقرير الأرصدة التراكمية", institution: str = ""
) -> str:
    head = (
        "<tr><th>#</th><th>الرقم الوظيفي</th><th>الاسم</th><th>العنوان الوظيفي</th>"
        "<th>مكان العمل</th><th>المؤسسة</th><th>أيام الخدمة</th><th>خارج الرصيد</th>"
        "<th>الدوام المحسوبة</th><th>المستحقة</th><th>المأخوذة</th><th>الرصيد</th></tr>"
    )
    body_rows = []
    totals = {"raw": 0, "outside": 0, "net": 0, "earned": 0, "taken": 0, "balance": 0}
    for i, r in enumerate(rows, 1):
        cls = "neg" if r["balance"] < 0 else "pos"
        body_rows.append(
            f"<tr><td>{i}</td><td>{esc(r['emp_id'])}</td><td>{esc(r['name'])}</td>"
            f"<td>{esc(r['job_title'])}</td><td>{esc(r['workplace'])}</td><td>{esc(r['institution'])}</td>"
            f"<td>{r['raw_days']}</td><td>{r['outside']}</td><td>{r['net_days']}</td>"
            f"<td>{r['earned']}</td><td>{r['taken']}</td>"
            f"<td class='{cls}'><b>{r['balance']}</b></td></tr>"
        )
        totals["raw"] += r["raw_days"]
        totals["outside"] += r["outside"]
        totals["net"] += r["net_days"]
        totals["earned"] += r["earned"]
        totals["taken"] += r["taken"]
        totals["balance"] += r["balance"]
    total_row = (
        f"<tr class='group'><td colspan='6'>الإجمالي ({len(rows)} موظف)</td>"
        f"<td>{totals['raw']}</td><td>{totals['outside']}</td><td>{totals['net']}</td>"
        f"<td>{totals['earned']}</td><td>{totals['taken']}</td>"
        f"<td><b>{totals['balance']}</b></td></tr>"
    )
    scope = f"<p class='muted'>النطاق: {esc(institution) if institution else 'كل المؤسسات'}</p>"
    note = (
        "<p class='muted'>ملاحظة: الرصيد السالب مسموح حسب الضوابط الإدارية المعتمدة.</p>"
        f"<p class='muted'>{esc(policy.annual_rate_note)}</p>"
    )
    body = (
        f"<h1>{esc(title)}</h1>{scope}<table><thead>{head}</thead><tbody>"
        f"{''.join(body_rows)}{total_row}</tbody></table>{note}"
    )
    return _page(title, body, auto_print=False)


def employee_detail_html(
    employee: Employee,
    policy: Policy,
    balance,
    statement=None,
    attachments: list | None = None,
    auto_print: bool = True,
) -> str:
    leaves = [lv for lv in employee.leaves if not lv.is_deleted]
    rows = []
    for i, lv in enumerate(leaves, 1):
        start, end = B.leave_span(lv)
        rows.append(
            f"<tr><td>{i}</td><td>{esc(lv.type)}</td><td>{esc(D.to_iso(start))}</td>"
            f"<td>{esc(D.to_iso(end))}</td><td>{esc(lv.amount)} {esc(lv.unit)}</td>"
            f"<td>{lv.days_actual}</td><td>{esc('نعم' if B.is_service_exclusion(policy, lv) else 'لا')}</td>"
            f"<td>{esc(config.LEAVE_STATUS_LABELS.get(lv.status, lv.status))}</td>"
            f"<td>{esc(lv.order)}</td><td>{esc(D.to_iso(lv.order_date))}</td>"
            f"<td>{esc(lv.reason)}</td><td>{esc(lv.added_date)}</td></tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='12' class='muted'>لا توجد إجازات مسجلة</td></tr>")

    bal_class = "neg" if balance.balance < 0 else "pos"
    info = {
        "الرقم الوظيفي": employee.emp_id,
        "العنوان الوظيفي": employee.job_title or "-",
        "مكان العمل": employee.workplace or "-",
        "المؤسسة": employee.institution or "-",
        "الجنس": employee.gender,
        "تاريخ المباشرة": D.to_iso(employee.start_date) or "-",
        "انتهاء الخدمة": D.to_iso(employee.end_date) or "-",
        "ملاحظات": employee.notes or "-",
    }
    nums = {
        "أيام الخدمة الكلية": balance.raw_days,
        "أيام خارج الرصيد": balance.outside,
        "أيام الدوام المحسوبة": balance.net_days,
        "الإجازات المستحقة بعد الافتتاحي" if balance.has_opening else "الإجازات المستحقة": balance.earned,
        "الإجازات المأخوذة بعد الافتتاحي" if balance.has_opening else "الإجازات المأخوذة": balance.taken,
    }
    if balance.has_opening:
        info["الرصيد الافتتاحي"] = (
            f"{balance.opening_balance} يوم كما في {D.to_iso(balance.opening_date)}"
            + (f" — حسبه: {balance.extra.get('opening_by')}" if balance.extra.get("opening_by") else "")
        )
    info_html = "".join(
        f"<div class='item'><label>{esc(k)}</label><span>{esc(v)}</span></div>" for k, v in info.items()
    )
    nums_html = "".join(
        f"<div class='item'><label>{esc(k)}</label><span>{v} يوم</span></div>" for k, v in nums.items()
    )
    nums_html += (
        f"<div class='item'><label>الرصيد المتبقي</label>"
        f"<span class='balance {bal_class}'>{balance.balance} يوم</span></div>"
    )

    st_html = ""
    if statement and statement.lines:
        srows = "".join(
            f"<tr><td>{line.index}</td><td>{esc(D.to_iso(line.start))}</td><td>{esc(D.to_iso(line.end))}</td>"
            f"<td>{line.service_days}</td><td>{line.outside_days}</td><td>{line.net_days}</td>"
            f"<td>{line.earned}</td><td>{line.taken}</td><td>{line.expired}</td>"
            f"<td>{line.carry_out}</td></tr>"
            for line in statement.lines
        )
        st_html = (
            f"<h2>كشف الحساب السنوي</h2><table><thead><tr><th>سنة الخدمة</th><th>من</th><th>إلى</th>"
            f"<th>أيام الخدمة</th><th>خارج الرصيد</th><th>صافي الدوام</th><th>المستحق</th>"
            f"<th>المأخوذ</th><th>منتهي</th><th>الرصيد المرحّل</th></tr></thead><tbody>{srows}</tbody></table>"
            f"<p class='muted'>{esc(statement.policy_note)}</p>"
        )

    att_html = ""
    if attachments:
        items = "".join(
            f"<li>{esc(a.filename)} <span class='muted'>({esc(a.added_at)})</span></li>" for a in attachments
        )
        att_html = f"<h2>المرفقات</h2><ul>{items}</ul>"

    body = (
        f"<h1>البيانات التفصيلية لسجل الإجازات والرصيد التراكمي<br>"
        f"{esc(employee.job_title)} - {esc(employee.name)}</h1>"
        f"<div class='grid'>{info_html}</div>"
        f"<h2>ملخص الرصيد</h2><div class='grid'>{nums_html}</div>"
        f"{st_html}{att_html}"
        f"<h2>سجل الإجازات</h2><table><thead><tr><th>#</th><th>النوع</th><th>من</th><th>إلى</th>"
        f"<th>العدد</th><th>الأيام المؤثرة</th><th>خارج الرصيد</th><th>الحالة</th><th>الأمر</th>"
        f"<th>تاريخ الأمر</th><th>السبب</th><th>تاريخ الإضافة</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        f"<div class='signatures'><div>توقيع الموظف: ______________</div>"
        f"<div>الموظف المسؤول: ______________</div></div>"
    )
    return _page(f"سجل إجازات {employee.name}", body, auto_print=auto_print)


def alerts_html(alerts: list, policy: Policy) -> str:
    from ..services.reports import SEVERITY_LABELS

    rows = "".join(
        f"<tr><td>{esc(SEVERITY_LABELS.get(a.severity, a.severity))}</td>"
        f"<td>{esc(a.name)}</td><td>{esc(a.institution)}</td><td>{esc(a.message)}</td></tr>"
        for a in alerts
    )
    if not rows:
        rows = "<tr><td colspan='4' class='muted'>لا توجد تنبيهات</td></tr>"
    body = (
        f"<h1>تقرير الإشعارات والتنبيهات ({len(alerts)})</h1>"
        f"<table><thead><tr><th>الأهمية</th><th>الموظف</th><th>المؤسسة</th><th>التنبيه</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )
    return _page("تقرير التنبيهات", body, auto_print=False)


def calendar_html(data: dict, policy: Policy, institution: str = "") -> str:
    grid = data["grid"]
    per_day = data["per_day"]
    weekdays = data["weekdays"]
    head = "".join(f"<th>{esc(w)}</th>" for w in weekdays)
    body_rows = []
    for week in grid:
        cells = []
        for day in week:
            if day is None:
                cells.append("<td class='muted'></td>")
                continue
            items = per_day.get(day, [])
            weekend = D.is_weekend(day, policy.weekend)
            style = "background:#f1f5f9;" if weekend else ""
            names = "<br>".join(
                f"{esc(e.name)} <span class='muted'>({esc(lv.type)})</span>" for e, lv in items
            )
            cells.append(
                f"<td style='{style}vertical-align:top;text-align:right'><b>{day.day}</b><br>{names}</td>"
            )
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    title = f"تقويم الإجازات {data['month']:02d}/{data['year']}"
    body = (
        f"<h1>{esc(title)}</h1>"
        f"<p class='muted'>النطاق: {esc(institution) if institution else 'كل المؤسسات'}</p>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
    )
    return _page(title, body, auto_print=False)


def statement_html(employee: Employee, policy: Policy, statement, balance) -> str:
    return employee_detail_html(employee, policy, balance, statement, auto_print=True)
