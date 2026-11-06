"""منطق حساب الأرصدة: الاحتساب المتواصل، الترصيد السنوي، كشف الحساب، تصفية نهاية الخدمة.

ملاحظات ضوابطية:
  * الرصيد السالب **مشروع** حسب الضوابط الإدارية ولا يُعد خطأً ولا يُمنع.
  * التسويات (نوع خاص) قد تكون قيمتها سالبة لتصحيح أرصدة سابقة.
  * سقف المعدل السنوي لا يُفرض إلا إذا فعّله المستخدم صراحةً، حفاظاً على الأرقام المعتمدة.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from .. import config as cfg
from ..models import Balance, Employee, Leave, Settlement, Statement, YearLine
from ..rules import LeaveRule, Policy
from . import dates as D


# ---------------------------------------------------------------------------
# أدوات داخلية
# ---------------------------------------------------------------------------
def active_leaves(leaves: list[Leave], include_pending: bool = False) -> list[Leave]:
    out = []
    for lv in leaves:
        if lv.is_deleted:
            continue
        if lv.status == "rejected":
            continue
        if lv.status == "pending" and not include_pending:
            continue
        out.append(lv)
    return out


def rule_of(policy: Policy, lv: Leave) -> LeaveRule:
    return policy.rule(lv.type)


def is_service_exclusion(policy: Policy, lv: Leave) -> bool:
    """هل تُستبعد أيام هذه الإجازة من أيام الخدمة؟"""
    if lv.is_adjustment:
        return False
    return bool(lv.outside_balance or rule_of(policy, lv).service_exclusion)


def consumes_balance(policy: Policy, lv: Leave) -> bool:
    """هل تؤثر هذه الإجازة في الرصيد (سلباً أو إيجاباً)؟"""
    return bool(rule_of(policy, lv).consumes_balance or lv.is_adjustment)


def leave_effect(policy: Policy, lv: Leave) -> tuple[int, int]:
    """يعيد (أيام مستبعدة من الخدمة، أيام مخصومة من الرصيد)."""
    days = int(lv.days_actual or 0)
    if is_service_exclusion(policy, lv):
        return max(0, days), 0
    if consumes_balance(policy, lv):
        return 0, days
    return 0, 0


def leave_span(lv: Leave) -> tuple[date | None, date | None]:
    start = lv.start_date
    end = lv.end_date or start
    return start, end


def _cap(earned: int, net_days: int, policy: Policy) -> int:
    """تطبيق سقف المعدل السنوي (اختياري، مُعطَّل افتراضياً)."""
    if not policy.enforce_annual_cap or not policy.max_annual:
        return earned
    full_years = net_days // 365
    remainder = net_days % 365
    cap = full_years * policy.max_annual + min(remainder // policy.days_per_leave, policy.max_annual)
    return min(earned, cap)


def attribute_days(total: int, start: date | None, end: date | None,
                   spans: list[tuple[int, date, date]]) -> dict[int, int]:
    """توزيع (total) يوماً على فترات سنوات الخدمة بحسب نسبة التداخل، بلا فقد أو تكرار.

    spans: [(index, from, to)] — فترات سنوات الخدمة. مجموع النواتج = total دائماً.
    """
    if not start or total == 0:
        return {}
    if not end or end < start:
        end = start
    span_total = max(1, (end - start).days + 1)
    overlaps: list[tuple[int, int]] = []
    for idx, lo, hi in spans:
        o_lo, o_hi = max(start, lo), min(end, hi)
        if o_lo <= o_hi:
            overlaps.append((idx, (o_hi - o_lo).days + 1))
    if not overlaps:
        for idx, lo, hi in spans:
            if lo <= start <= hi:
                return {idx: total}
        return {}

    sign = -1 if total < 0 else 1
    magnitude = abs(total)
    result: dict[int, int] = {}
    allocated = 0
    for i, (idx, days) in enumerate(overlaps):
        share = magnitude - allocated if i == len(overlaps) - 1 else int(round(magnitude * days / span_total))
        share = max(0, min(share, magnitude - allocated))
        allocated += share
        if share:
            result[idx] = result.get(idx, 0) + sign * share
    return result


# ---------------------------------------------------------------------------
# الرصيد الرئيسي (متواصل) — يطابق تماماً منطق الإصدار السابق عند الإعدادات الافتراضية
# ---------------------------------------------------------------------------
def compute_continuous(employee: Employee, leaves: list[Leave], policy: Policy,
                       today: date | None = None) -> Balance:
    today = today or date.today()
    start = employee.start_date
    if not start:
        return Balance(extra={"no_start_date": True})

    limit = min(today, employee.end_date) if employee.end_date else today
    raw_days = max(0, (limit - start).days)

    outside = 0
    taken = 0
    for lv in leaves:
        excluded, consumed = leave_effect(policy, lv)
        outside += excluded
        taken += consumed
    net_days = max(0, raw_days - outside)

    if employee.has_opening_balance:
        cutoff = employee.opening_balance_date
        calc_start = max(start, cutoff + timedelta(days=1)) if cutoff else start
        service_after = max(0, (limit - calc_start).days)
        outside_after = 0
        taken_after = 0
        for lv in leaves:
            s, e = leave_span(lv)
            if not s:
                continue
            excluded, consumed = leave_effect(policy, lv)
            if cutoff and s <= cutoff:
                # إجازة مستبعدة من الخدمة تمتد بعد التاريخ: نحسب الجزء الواقع بعده فقط
                if excluded and e and e > cutoff:
                    rule = policy.rule(lv.type)
                    partial = D.days_count(cutoff + timedelta(days=1), e, rule.count_mode,
                                           policy.weekend, policy.holidays)
                    outside_after += min(excluded, partial)
                # ما يخصم من الرصيد قبل/عند التاريخ ممنوع أصلاً
                continue
            outside_after += excluded
            taken_after += consumed
        net_after = max(0, service_after - outside_after)
        earned_after = _cap(net_after // policy.days_per_leave, net_after, policy)
        final = int(employee.opening_balance or 0) + earned_after - taken_after
        return Balance(
            raw_days=raw_days, outside=outside, net_days=net_days,
            earned=earned_after, taken=taken_after, balance=final,
            opening_balance=int(employee.opening_balance or 0), opening_date=cutoff,
            earned_after=earned_after, taken_after=taken_after,
            service_days_after=service_after, net_days_after=net_after, has_opening=True,
            extra={
                "opening_by": employee.opening_balance_by,
                "opening_note": employee.opening_balance_note,
                "full_outside": outside,
                "full_taken": taken,
                "full_net_days": net_days,
                "outside_after": outside_after,
            })

    earned = _cap(net_days // policy.days_per_leave, net_days, policy)
    return Balance(raw_days=raw_days, outside=outside, net_days=net_days,
                   earned=earned, taken=taken, balance=earned - taken,
                   earned_after=earned, taken_after=taken, service_days_after=raw_days,
                   net_days_after=net_days, has_opening=False)


# ---------------------------------------------------------------------------
# كشف الحساب السنوي + الترحيل والصلاحية
# ---------------------------------------------------------------------------
def _year_lines(employee: Employee, items: list[Leave], policy: Policy,
                limit: date, max_years: int, start_override: date | None = None,
                initial_carry: int = 0) -> list[YearLine]:
    """يبني سطور سنوات الخدمة (بلا أي استدعاء للرصيد ⇒ لا ارتداد)."""
    start = start_override or employee.start_date
    if not start or limit < start:
        return []
    lines: list[YearLine] = []
    spans = D.service_years_bounds(start, max_years)
    indexed_spans = [(i, lo, hi) for i, (lo, hi) in enumerate(spans)]
    current_index = 0
    for i, (lo, _hi) in enumerate(spans):
        if lo <= limit:
            current_index = i

    outside_by_year: dict[int, int] = {}
    taken_by_year: dict[int, int] = {}
    for lv in items:
        s, e = leave_span(lv)
        if not s:
            continue
        excluded, consumed = leave_effect(policy, lv)
        days = excluded or consumed
        if not days:
            continue
        bucket = outside_by_year if excluded else taken_by_year
        e_eff = min(e or s, limit)
        if s > limit:
            shares = attribute_days(days, s, e, indexed_spans)
        else:
            shares = attribute_days(days, s, e_eff, indexed_spans)
            leftover = days - sum(shares.values())
            if leftover:
                shares[current_index] = shares.get(current_index, 0) + leftover
        for idx, share in shares.items():
            bucket[idx] = bucket.get(idx, 0) + share

    carry = initial_carry
    for idx, (lo, hi) in enumerate(spans):
        if lo > limit:
            break
        hi_eff = min(hi, limit)
        outside = outside_by_year.get(idx, 0)
        taken = taken_by_year.get(idx, 0)

        service = max(0, (hi_eff - lo).days + 1)
        net = max(0, service - outside)
        earned = net // policy.days_per_leave
        if policy.max_annual:
            earned = min(earned, policy.max_annual)

        expired = 0
        if policy.expiry_years and idx >= policy.expiry_years:
            expiry_idx = idx - policy.expiry_years
            if 0 <= expiry_idx < len(lines):
                expired = max(0, lines[expiry_idx].carry_out)

        remaining = carry + earned - expired - taken
        if policy.carryover_cap:
            remaining = min(remaining, policy.carryover_cap)
        lines.append(YearLine(
            index=idx + 1, start=lo, end=hi_eff, service_days=service, outside_days=outside,
            net_days=net, earned=earned, taken=taken, expired=expired,
            carry_in=carry, carry_out=remaining, is_current=hi >= limit))
        carry = remaining
    return lines


def yearly_statement(employee: Employee, leaves: list[Leave], policy: Policy,
                     today: date | None = None, max_years: int = 60) -> Statement:
    today = today or date.today()
    items = active_leaves(leaves)
    base = compute_continuous(employee, items, policy, today)
    start = employee.start_date
    if not start:
        return Statement(employee=employee, balance=base, lines=[],
                         policy_note="لا يوجد تاريخ مباشرة")
    cutoff = employee.opening_balance_date if employee.has_opening_balance else None
    opening_fields = {
        "opening_balance": int(employee.opening_balance or 0) if cutoff else 0,
        "opening_date": cutoff,
        "opening_by": employee.opening_balance_by if cutoff else "",
        "opening_note": employee.opening_balance_note if cutoff else "",
    }
    calc_start = (cutoff + timedelta(days=1)) if cutoff else start
    calc_start = max(calc_start, start)
    limit = min(today, employee.end_date) if employee.end_date else today
    if limit < calc_start:
        return Statement(employee=employee, balance=base, lines=[],
                         policy_note="تاريخ المباشرة بعد تاريخ الحساب", **opening_fields)

    # الإجازات السابقة/المشملة في الرصيد الافتتاحي لا تُحسب مرة ثانية
    if cutoff:
        adjusted: list[Leave] = []
        for lv in items:
            s, e = leave_span(lv)
            if not s:
                continue
            rule = policy.rule(lv.type)
            if s <= cutoff:
                if (e and e > cutoff and rule.service_exclusion
                        and not (rule.consumes_balance or lv.is_adjustment)):
                    partial = D.days_count(cutoff + timedelta(days=1), e, rule.count_mode,
                                           policy.weekend, policy.holidays)
                    if partial > 0:
                        adjusted.append(replace(
                            lv, start_date=cutoff + timedelta(days=1), end_date=e,
                            days_actual=min(int(lv.days_actual or 0), partial),
                            working_days=D.count_working_days(
                                cutoff + timedelta(days=1), e, policy.weekend, policy.holidays)))
                continue
            adjusted.append(lv)
        items = adjusted
    lines = _year_lines(employee, items, policy, limit, max_years,
                        start_override=calc_start,
                        initial_carry=opening_fields["opening_balance"])
    balance = base
    if policy.basis == cfg.BASIS_ANNUAL and lines:
        earned = sum(line.earned for line in lines) - sum(line.expired for line in lines)
        taken = sum(line.taken for line in lines)
        balance = replace(base, earned=earned, taken=taken,
                          earned_after=earned, taken_after=taken,
                          balance=lines[-1].carry_out)
    note = ("الاحتساب المتواصل (من تاريخ المباشرة حتى اليوم)"
            if policy.basis == cfg.BASIS_CONTINUOUS else "الترصيد السنوي (سنة خدمة)")
    if cutoff:
        note += f" | الرصيد الافتتاحي كما في {D.to_iso(cutoff)}"
    return Statement(employee=employee, balance=balance, lines=lines,
                     policy_note=note, **opening_fields)


def compute_annual(employee: Employee, leaves: list[Leave], policy: Policy,
                   today: date | None = None) -> Balance:
    """الرصيد بمنهج الترصيد السنوي (مجموع الاستحقاق − المنتهي − المأخوذ)."""
    return yearly_statement(employee, leaves, policy, today).balance


def compute_balance(employee: Employee, leaves: list[Leave], policy: Policy,
                    today: date | None = None, include_pending: bool = False) -> Balance:
    """الحساب المعتمد حسب السياسة (متواصل أو سنوي)."""
    items = active_leaves(leaves, include_pending=include_pending)
    if policy.basis == cfg.BASIS_ANNUAL:
        return compute_annual(employee, items, policy, today)
    return compute_continuous(employee, items, policy, today)


def taken_this_year(employee: Employee, leaves: list[Leave], policy: Policy,
                    today: date | None = None) -> int:
    today = today or date.today()
    first = today.replace(month=1, day=1)
    total = 0
    for lv in active_leaves(leaves):
        s, _e = leave_span(lv)
        if s and first <= s <= today:
            _excluded, consumed = leave_effect(policy, lv)
            total += consumed
    return total


def period_totals(employee: Employee, leaves: list[Leave], policy: Policy,
                  start: date, end: date) -> dict[str, int]:
    """إجماليات فترة مخصّصة (للتقارير)."""
    out = {"outside": 0, "taken": 0, "count": 0}
    for lv in active_leaves(leaves):
        s, e = leave_span(lv)
        if not s or not e or not D.overlaps(s, e, start, end):
            continue
        excluded, consumed = leave_effect(policy, lv)
        out["outside"] += excluded
        out["taken"] += consumed
        out["count"] += 1
    return out


# ---------------------------------------------------------------------------
# تصفية نهاية الخدمة
# ---------------------------------------------------------------------------
def settlement(employee: Employee, leaves: list[Leave], policy: Policy,
               today: date | None = None, day_value: float | None = None,
               as_of_end_of_service: bool = True) -> Settlement:
    as_of = today or date.today()
    if as_of_end_of_service and employee.end_date:
        as_of = employee.end_date
    bal = compute_balance(employee, leaves, policy, as_of)
    amount = None
    if day_value is not None:
        amount = round(bal.balance * float(day_value), 2)
    return Settlement(employee=employee, balance_days=bal.balance, service_days=bal.net_days,
                      earned=bal.earned, taken=bal.taken, day_value=day_value, amount=amount)


# ---------------------------------------------------------------------------
# قوائم مساعدة للواجهة
# ---------------------------------------------------------------------------
def employees_in_leave(employees: list[Employee], policy: Policy,
                       day: date | None = None) -> list[tuple[Employee, Leave]]:
    """الموظفون الذين هم في إجازة بتاريخ معيّن."""
    day = day or date.today()
    out: list[tuple[Employee, Leave]] = []
    for emp in employees:
        for lv in active_leaves(emp.leaves):
            s, e = leave_span(lv)
            if s and e and s <= day <= e and not is_service_exclusion(policy, lv):
                out.append((emp, lv))
    return out
