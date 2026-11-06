"""بناء بيانات التقارير، التنبيهات، ولوحة المؤشرات."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..models import Employee, Leave
from ..rules import Policy
from . import balance as B
from . import dates as D


# ---------------------------------------------------------------------------
# التنبيهات
# ---------------------------------------------------------------------------
@dataclass
class Alert:
    kind: str
    severity: str  # high | medium | info
    message: str
    emp_id: str = ""
    name: str = ""
    institution: str = ""
    day: date | None = None
    leave_id: int | None = None


SEVERITY_LABELS = {"high": "مهم", "medium": "متوسط", "info": "معلومة"}
SEVERITY_ORDER = {"high": 0, "medium": 1, "info": 2}


def collect_alerts(employees: list[Employee], policy: Policy, today: date | None = None) -> list[Alert]:
    today = today or date.today()
    alerts: list[Alert] = []
    ahead = policy.warn_leaving_soon_days

    for emp in employees:
        if emp.is_deleted:
            continue
        bal = B.compute_balance(emp, emp.leaves, policy, today)

        if bal.extra.get("no_start_date"):
            alerts.append(
                Alert(
                    "missing_data",
                    "medium",
                    "لا يوجد تاريخ مباشرة — تعذّر حساب الرصيد",
                    emp.emp_id,
                    emp.name,
                    emp.institution,
                )
            )
        elif bal.balance < 0:
            alerts.append(
                Alert(
                    "negative_balance",
                    "info",
                    f"الرصيد سالب ({bal.balance} يوم) — مسموح حسب الضوابط الإدارية",
                    emp.emp_id,
                    emp.name,
                    emp.institution,
                )
            )
        elif bal.balance <= policy.low_balance_days:
            alerts.append(
                Alert(
                    "low_balance",
                    "medium",
                    f"رصيد منخفض ({bal.balance} يوم)",
                    emp.emp_id,
                    emp.name,
                    emp.institution,
                )
            )

        if emp.end_date and 0 <= (emp.end_date - today).days <= 30:
            alerts.append(
                Alert(
                    "service_ending",
                    "medium",
                    f"انتهاء الخدمة بعد {(emp.end_date - today).days} يوم ({D.to_iso(emp.end_date)})",
                    emp.emp_id,
                    emp.name,
                    emp.institution,
                    emp.end_date,
                )
            )

        for lv in emp.leaves:
            if lv.is_deleted:
                continue
            if lv.status == "pending":
                alerts.append(
                    Alert(
                        "pending",
                        "medium",
                        f"إجازة «{lv.type}» قيد الانتظار ({D.to_iso(lv.start_date)})",
                        emp.emp_id,
                        emp.name,
                        emp.institution,
                        lv.start_date,
                        lv.id,
                    )
                )
                continue
            if lv.status == "rejected" or B.is_service_exclusion(policy, lv):
                continue
            start, end = B.leave_span(lv)
            if not start or not end:
                continue
            remaining = (end - today).days
            if 0 <= remaining <= ahead:
                when = "تنتهي اليوم" if remaining == 0 else f"تنتهي بعد {remaining} يوم"
                alerts.append(
                    Alert(
                        "ending_soon",
                        "medium",
                        f"إجازة «{lv.type}» {when} (حتى {D.to_iso(end)})",
                        emp.emp_id,
                        emp.name,
                        emp.institution,
                        end,
                        lv.id,
                    )
                )
            if start == today:
                alerts.append(
                    Alert(
                        "started_today",
                        "info",
                        f"بدء إجازة «{lv.type}» اليوم حتى {D.to_iso(end)}",
                        emp.emp_id,
                        emp.name,
                        emp.institution,
                        start,
                        lv.id,
                    )
                )

    alerts.sort(key=lambda a: (SEVERITY_ORDER.get(a.severity, 9), a.name))
    return alerts


def alert_lines(alerts: list[Alert]) -> list[str]:
    icons = {"high": "⛔", "medium": "⚠️", "info": "ℹ️"}
    out = []
    for a in alerts:
        who = f"{a.name} - {a.institution}" if a.institution else a.name
        out.append(f"{icons.get(a.severity, '•')} {who} : {a.message}")
    return out


# ---------------------------------------------------------------------------
# التقارير
# ---------------------------------------------------------------------------
def global_report(employees: list[Employee], policy: Policy, today: date | None = None) -> list[dict]:
    today = today or date.today()
    rows = []
    for emp in employees:
        if emp.is_deleted:
            continue
        bal = B.compute_balance(emp, emp.leaves, policy, today)
        rows.append(
            {
                "emp_id": emp.emp_id,
                "name": emp.name,
                "job_title": emp.job_title,
                "workplace": emp.workplace,
                "institution": emp.institution,
                "gender": emp.gender,
                "start_date": D.to_iso(emp.start_date),
                "raw_days": bal.raw_days,
                "outside": bal.outside,
                "net_days": bal.net_days,
                "earned": bal.earned,
                "taken": bal.taken,
                "balance": bal.balance,
                "leaves_count": len([lv for lv in emp.leaves if not lv.is_deleted]),
                "notes": emp.notes,
            }
        )
    rows.sort(key=lambda r: (-r["balance"], r["name"]))
    return rows


def statement_rows(employee: Employee, policy: Policy, today: date | None = None) -> list[dict]:
    st = B.yearly_statement(employee, employee.leaves, policy, today)
    return [
        {
            "index": line.index,
            "start": D.to_iso(line.start),
            "end": D.to_iso(line.end),
            "service_days": line.service_days,
            "outside_days": line.outside_days,
            "net_days": line.net_days,
            "earned": line.earned,
            "taken": line.taken,
            "expired": line.expired,
            "carry_in": line.carry_in,
            "carry_out": line.carry_out,
            "current": line.is_current,
        }
        for line in st.lines
    ]


def dashboard_data(employees: list[Employee], policy: Policy, today: date | None = None) -> dict:
    today = today or date.today()
    live = [e for e in employees if not e.is_deleted]
    rows = global_report(live, policy, today)

    total_balance = sum(r["balance"] for r in rows)
    negatives = [r for r in rows if r["balance"] < 0]
    on_leave = B.employees_in_leave(live, policy, today)
    pending = [lv for e in live for lv in e.leaves if not lv.is_deleted and lv.status == "pending"]

    by_institution: dict[str, dict] = {}
    for r in rows:
        key = r["institution"] or "(غير محددة)"
        item = by_institution.setdefault(key, {"count": 0, "balance": 0, "negative": 0})
        item["count"] += 1
        item["balance"] += r["balance"]
        item["negative"] += 1 if r["balance"] < 0 else 0

    by_type: dict[str, dict] = {}
    monthly = [0] * 12
    for emp in live:
        for lv in emp.leaves:
            if lv.is_deleted or lv.status == "rejected":
                continue
            excluded, consumed = B.leave_effect(policy, lv)
            if not consumed and not excluded:
                continue
            item = by_type.setdefault(lv.type or "غير محددة", {"count": 0, "days": 0})
            item["count"] += 1
            item["days"] += consumed or excluded
            if lv.start_date and lv.start_date.year == today.year:
                monthly[lv.start_date.month - 1] += consumed or excluded

    return {
        "kpis": {
            "employees": len(live),
            "leaves": sum(len([lv for lv in e.leaves if not lv.is_deleted]) for e in live),
            "earned": sum(r["earned"] for r in rows),
            "taken": sum(r["taken"] for r in rows),
            "balance": total_balance,
            "negative": len(negatives),
            "on_leave_today": len(on_leave),
            "pending": len(pending),
            "institutions": len(by_institution),
            "low_balance": len([r for r in rows if 0 <= r["balance"] <= policy.low_balance_days]),
        },
        "rows": rows,
        "top": rows[:10],
        "worst": sorted(rows, key=lambda r: r["balance"])[:10],
        "by_institution": dict(sorted(by_institution.items(), key=lambda kv: -kv[1]["count"])),
        "by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1]["days"])),
        "monthly": monthly,
        "on_leave": [
            {
                "emp_id": e.emp_id,
                "name": e.name,
                "institution": e.institution,
                "type": lv.type,
                "start": D.to_iso(lv.start_date),
                "end": D.to_iso(lv.end_date),
            }
            for e, lv in on_leave
        ],
        "year": today.year,
    }


def calendar_month(
    employees: list[Employee], policy: Policy, year: int, month: int, first_day_of_week: int | None = None
) -> dict:
    """بيانات شبكة التقويم: كل يوم -> قائمة (موظف، إجازة)."""
    first_day_of_week = policy.first_day_of_week if first_day_of_week is None else first_day_of_week
    grid = D.month_grid(year, month, first_day_of_week)
    month_start, month_end = D.month_bounds(date(year, month, 1))
    per_day: dict[date, list[tuple[Employee, Leave]]] = {}
    live = [e for e in employees if not e.is_deleted]
    for emp in live:
        for lv in B.active_leaves(emp.leaves):
            start, end = B.leave_span(lv)
            if not start or not end:
                continue
            lo, hi = max(start, month_start), min(end, month_end)
            if lo > hi:
                continue
            day = lo
            while day <= hi:
                per_day.setdefault(day, []).append((emp, lv))
                day += timedelta(days=1)
    return {
        "grid": grid,
        "per_day": per_day,
        "weekdays": D.weekday_labels(first_day_of_week),
        "year": year,
        "month": month,
    }


def advanced_statistics(employees: list[Employee], policy: Policy, today: date | None = None) -> dict:
    """إحصائيات متقدمة: متوسط الإجازات، أكثر الأنواع، التوزيع حسب المؤسسة، إلخ."""
    today = today or date.today()
    live = [e for e in employees if not e.is_deleted]
    rows = global_report(live, policy, today)

    if not rows:
        return {
            "avg_balance": 0,
            "avg_taken": 0,
            "avg_earned": 0,
            "most_used_type": "",
            "most_used_count": 0,
            "consumption_rate": 0,
            "by_institution_stats": {},
            "yearly_trend": [],
        }

    # المتوسطات
    avg_balance = sum(r["balance"] for r in rows) / len(rows)
    avg_taken = sum(r["taken"] for r in rows) / len(rows)
    avg_earned = sum(r["earned"] for r in rows) / len(rows)

    # أكثر الأنواع استخداماُ
    by_type: dict[str, int] = {}
    for emp in live:
        for lv in emp.leaves:
            if lv.is_deleted or lv.status == "rejected":
                continue
            by_type[lv.type or "غير محددة"] = by_type.get(lv.type or "غير محددة", 0) + 1
    most_used_type = max(by_type, key=by_type.get) if by_type else ""
    most_used_count = by_type.get(most_used_type, 0)

    # نسبة الاستهلاك
    total_earned = sum(r["earned"] for r in rows)
    total_taken = sum(r["taken"] for r in rows)
    consumption_rate = (total_taken / total_earned * 100) if total_earned > 0 else 0

    # التوزيع حسب المؤسسة
    by_inst: dict[str, dict] = {}
    for r in rows:
        key = r["institution"] or "(غير محددة)"
        item = by_inst.setdefault(key, {"count": 0, "balance": 0, "taken": 0, "earned": 0})
        item["count"] += 1
        item["balance"] += r["balance"]
        item["taken"] += r["taken"]
        item["earned"] += r["earned"]
    for item in by_inst.values():
        c = item["count"]
        item["avg_balance"] = item["balance"] / c if c else 0
        item["avg_taken"] = item["taken"] / c if c else 0

    # الاتجاه السنوي
    yearly_trend = []
    for year in range(today.year - 4, today.year + 1):
        year_taken = 0
        year_count = 0
        for emp in live:
            for lv in emp.leaves:
                if lv.is_deleted or lv.status == "rejected":
                    continue
                if lv.start_date and lv.start_date.year == year:
                    excluded, consumed = B.leave_effect(policy, lv)
                    year_taken += consumed or excluded
                    year_count += 1
        yearly_trend.append({"year": year, "taken": year_taken, "count": year_count})

    return {
        "avg_balance": round(avg_balance, 1),
        "avg_taken": round(avg_taken, 1),
        "avg_earned": round(avg_earned, 1),
        "most_used_type": most_used_type,
        "most_used_count": most_used_count,
        "consumption_rate": round(consumption_rate, 1),
        "by_institution_stats": by_inst,
        "yearly_trend": yearly_trend,
    }
