"""اختبارات حسابات الرصيد: الحفاظ على الأرقام المعتمدة + القواعد الجديدة."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from amdh_leave import config
from amdh_leave.models import Employee, Leave
from amdh_leave.services import balance as B
from tests.conftest import LEGACY_TODAY, make_leave


def test_legacy_numbers_are_preserved(employee, policy):
    """الأرقام المعتمدة في النظام الحالي: 2716/1825/891/89/20/69."""
    result = B.compute_balance(employee, employee.leaves, policy, LEGACY_TODAY)
    assert (result.raw_days, result.outside, result.net_days) == (2716, 1825, 891)
    assert (result.earned, result.taken, result.balance) == (89, 20, 69)


def test_rule_semantics_match_legacy_behaviour(policy):
    """«5 سنوات» تُستبعد من الخدمة ولا تُخصم من الرصيد؛ «اعتيادية» تُخصم."""
    five = policy.rule("5 سنوات")
    normal = policy.rule("اعتيادية")
    assert five.service_exclusion and not five.consumes_balance
    assert normal.consumes_balance and not normal.service_exclusion


def test_negative_balance_is_allowed(employee, policy):
    """الرصيد السالب مشروع حسب الضوابط الإدارية ولا يُمنع."""
    extra = make_leave(start_date=date(2026, 5, 1), end_date=date(2026, 8, 31),
                       amount=123, days_actual=123)
    result = B.compute_balance(employee, employee.leaves + [extra], policy, LEGACY_TODAY)
    assert result.balance == 69 - 123 == -54
    assert result.is_negative


def test_adjustment_can_be_negative_and_increases_balance(employee, policy):
    adjustment = make_leave(type=config.ADJUSTMENT_TYPE, start_date=date(2026, 6, 1),
                            end_date=date(2026, 6, 1), amount=-5, days_actual=-5,
                            is_adjustment=True, reason="تصحيح رصيد سابق")
    result = B.compute_balance(employee, employee.leaves + [adjustment], policy, LEGACY_TODAY)
    assert result.taken == 15          # 20 - 5
    assert result.balance == 69 + 5    # الرصيد يزيد بالتصحيح السالب
    assert result.outside == 1825      # التسوية لا تمسّ أيام الخدمة


def test_service_exclusion_not_deducted_from_balance(employee, policy):
    exclusion = make_leave(type="5 سنوات", start_date=date(2026, 1, 1), end_date=date(2026, 1, 10),
                           days_actual=10, outside_balance=True)
    result = B.compute_balance(employee, [exclusion], policy, LEGACY_TODAY)
    assert result.taken == 0
    assert result.outside == 10
    assert result.balance == result.earned


def test_no_start_date_returns_flag(policy):
    employee = Employee(emp_id="X", start_date=None)
    result = B.compute_balance(employee, [], policy, LEGACY_TODAY)
    assert result.extra.get("no_start_date") is True
    assert result.balance == 0


def test_end_of_service_stops_accrual(employee, policy):
    ended = replace(employee, end_date=date(2025, 4, 29))
    result = B.compute_balance(ended, employee.leaves, policy, LEGACY_TODAY)
    assert result.raw_days == (date(2025, 4, 29) - date(2019, 4, 30)).days


def test_pending_leaves_excluded_by_default(employee, policy):
    pending = make_leave(start_date=date(2026, 6, 1), end_date=date(2026, 6, 10),
                         days_actual=10, status="pending")
    leaves = employee.leaves + [pending]
    assert B.compute_balance(employee, leaves, policy, LEGACY_TODAY).taken == 20
    assert B.compute_balance(employee, leaves, policy, LEGACY_TODAY, include_pending=True).taken == 30


def test_rejected_leaves_never_count(employee, policy):
    rejected = make_leave(start_date=date(2026, 6, 1), end_date=date(2026, 6, 10),
                          days_actual=10, status="rejected")
    assert B.compute_balance(employee, employee.leaves + [rejected], policy, LEGACY_TODAY).taken == 20


def test_deleted_leaves_never_count(employee, policy):
    deleted = make_leave(start_date=date(2026, 6, 1), end_date=date(2026, 6, 10),
                         days_actual=10, deleted_at="2026-06-01 10:00:00")
    assert B.compute_balance(employee, employee.leaves + [deleted], policy, LEGACY_TODAY).taken == 20


def test_annual_cap_not_enforced_by_default(employee, policy):
    """السقف السنوي معطَّل افتراضياً فلا تتغير الأرقام المعتمدة."""
    assert policy.enforce_annual_cap is False
    capped = replace(policy, enforce_annual_cap=True)
    assert B.compute_balance(employee, employee.leaves, policy, LEGACY_TODAY).earned == 89
    assert B.compute_balance(employee, employee.leaves, capped, LEGACY_TODAY).earned == 88


def test_statement_reconciles_with_headline(employee, policy):
    """كشف الحساب السنوي يجب أن يطابق الرصيد في خارج الرصيد والمأخوذة."""
    statement = B.yearly_statement(employee, employee.leaves, policy, LEGACY_TODAY)
    assert len(statement.lines) == 8
    assert sum(line.outside_days for line in statement.lines) == 1825
    assert sum(line.taken for line in statement.lines) == 20
    assert statement.lines[0].start == date(2019, 4, 30)
    assert statement.lines[-1].is_current
    assert statement.policy_note


def test_statement_distributes_long_exclusion_across_years(employee, policy):
    """إجازة 5 سنوات تُوزَّع على سنوات الخدمة التي تغطيها ولا تُحمَّل على سنة واحدة."""
    statement = B.yearly_statement(employee, employee.leaves, policy, LEGACY_TODAY)
    outside_per_year = [line.outside_days for line in statement.lines]
    assert max(outside_per_year) < 1825
    assert len([value for value in outside_per_year if value]) >= 5


def test_attribute_days_never_loses_or_duplicates():
    spans = [(0, date(2020, 1, 1), date(2020, 12, 31)), (1, date(2021, 1, 1), date(2021, 12, 31))]
    shares = B.attribute_days(730, date(2020, 1, 1), date(2021, 12, 31), spans)
    assert sum(shares.values()) == 730
    assert shares[0] == 365 and shares[1] == 365
    # لا فقد ولا تكرار مهما كان التوزيع
    odd = B.attribute_days(101, date(2020, 6, 1), date(2021, 6, 30), spans)
    assert sum(odd.values()) == 101
    negative = B.attribute_days(-10, date(2021, 6, 1), date(2021, 6, 10), spans)
    assert sum(negative.values()) == -10
    assert negative == {1: -10}
    outside = B.attribute_days(5, date(2019, 1, 1), date(2019, 1, 5), spans)
    assert outside == {}      # خارج سنوات الخدمة المعروضة


def test_annual_basis_close_to_continuous(employee, policy):
    annual = replace(policy, basis=config.BASIS_ANNUAL)
    continuous = B.compute_balance(employee, employee.leaves, policy, LEGACY_TODAY)
    result = B.compute_balance(employee, employee.leaves, annual, LEGACY_TODAY)
    assert abs(result.balance - continuous.balance) <= 2
    assert result.taken == continuous.taken


def test_expiry_and_carryover_cap(employee, policy):
    expiring = replace(policy, basis=config.BASIS_ANNUAL, expiry_years=2)
    capped = replace(policy, basis=config.BASIS_ANNUAL, carryover_cap=30)
    without = B.compute_balance(employee, employee.leaves, expiring, LEGACY_TODAY)
    with_cap = B.compute_balance(employee, employee.leaves, capped, LEGACY_TODAY)
    assert without.earned <= B.compute_balance(employee, employee.leaves, policy, LEGACY_TODAY).earned
    assert with_cap.balance <= with_cap.earned


def test_taken_this_year_and_period_totals(employee, policy):
    assert B.taken_this_year(employee, employee.leaves, policy, LEGACY_TODAY) == 20
    totals = B.period_totals(employee, employee.leaves, policy,
                             date(2020, 1, 1), date(2020, 12, 31))
    assert totals["count"] == 1
    assert totals["outside"] == 1825


def test_settlement_supports_day_value(employee, policy):
    result = B.settlement(employee, employee.leaves, policy, today=LEGACY_TODAY,
                          day_value=25000, as_of_end_of_service=False)
    assert result.balance_days == 69
    assert result.amount == 69 * 25000


def test_employees_in_leave_today(employee, policy):
    on_leave = B.employees_in_leave([employee], policy, date(2026, 5, 5))
    assert len(on_leave) == 1
    assert B.employees_in_leave([employee], policy, date(2027, 5, 5)) == []


def test_working_day_count_mode_changes_days(policy):
    working = replace(policy, rules={**policy.rules,
                                     "اعتيادية": replace(policy.rule("اعتيادية"), count_mode="working")})
    leave = make_leave(days_actual=8, working_days=8)
    employee = Employee(emp_id="T", start_date=date(2019, 4, 30))
    assert B.compute_balance(employee, [leave], working, LEGACY_TODAY).taken == 8
    assert B.leave_effect(working, leave) == (0, 8)
