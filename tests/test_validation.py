"""اختبارات التحقق من المدخلات وكشف التعارضات."""

from __future__ import annotations

from datetime import date

from amdh_leave import config
from amdh_leave.services import validation
from tests.conftest import make_leave


def messages(issues):
    return " | ".join(issue.message for issue in issues)


def test_valid_leave_has_no_errors(employee, policy):
    leave = make_leave(start_date=date(2026, 7, 1), end_date=date(2026, 7, 10), days_actual=10)
    issues = validation.validate_leave(leave, employee, employee.leaves, policy)
    assert not [i for i in issues if i.is_error]


def test_negative_amount_rejected_for_normal_type(employee, policy):
    """الإدخال السالب ممنوع للأنواع العادية (والتسوية لها مسار خاص)."""
    leave = make_leave(amount=-5, days_actual=-5)
    issues = validation.validate_leave(leave, employee, employee.leaves, policy)
    assert any(i.is_error and "أكبر من صفر" in i.message for i in issues)


def test_zero_amount_rejected(employee, policy):
    leave = make_leave(amount=0, days_actual=0)
    issues = validation.validate_leave(leave, employee, employee.leaves, policy)
    assert any(i.is_error for i in issues)


def test_adjustment_accepts_negative_but_requires_reason(employee, policy):
    leave = make_leave(type=config.ADJUSTMENT_TYPE, amount=-5, days_actual=-5,
                       is_adjustment=True, reason="")
    issues = validation.validate_leave(leave, employee, employee.leaves, policy)
    assert any(i.is_error and "سبب" in i.message for i in issues)

    leave.reason = "تصحيح إداري"
    issues = validation.validate_leave(leave, employee, employee.leaves, policy)
    assert not [i for i in issues if i.is_error]


def test_adjustment_zero_rejected(employee, policy):
    leave = make_leave(type=config.ADJUSTMENT_TYPE, amount=0, days_actual=0,
                       is_adjustment=True, reason="x")
    issues = validation.validate_leave(leave, employee, employee.leaves, policy)
    assert any(i.is_error and "صفر" in i.message for i in issues)


def test_requires_order_rule_enforced(employee, policy):
    leave = make_leave(type="مرضية", order="", days_actual=5)
    issues = validation.validate_leave(leave, employee, employee.leaves, policy)
    assert any(i.is_error and "رقم الأمر" in i.message for i in issues)


def test_duplicate_order_number_warns(employee, policy):
    leave = make_leave(start_date=date(2027, 1, 1), end_date=date(2027, 1, 5),
                       order="205", days_actual=5)
    issues = validation.validate_leave(leave, employee, employee.leaves, policy)
    assert any(i.level == "warning" and "رقم الأمر" in i.message for i in issues)


def test_overlapping_leave_warns(employee, policy):
    leave = make_leave(start_date=date(2026, 5, 1), end_date=date(2026, 5, 10), days_actual=10)
    issues = validation.validate_leave(leave, employee, employee.leaves, policy)
    assert any(i.level == "warning" and "تتقاطع" in i.message for i in issues)


def test_overlap_ignored_for_the_edited_leave(employee, policy):
    existing = employee.leaves[1]
    issues = validation.validate_leave(existing, employee, employee.leaves, policy,
                                       leave_id=existing.id)
    assert not any("تتقاطع" in i.message for i in issues)


def test_leave_before_hire_date_warns(employee, policy):
    leave = make_leave(start_date=date(2010, 1, 1), end_date=date(2010, 1, 10), days_actual=10)
    issues = validation.validate_leave(leave, employee, [], policy)
    assert any(i.level == "warning" and "قبل تاريخ المباشرة" in i.message for i in issues)


def test_end_before_start_is_error(employee, policy):
    leave = make_leave(start_date=date(2026, 5, 10), end_date=date(2026, 5, 1), days_actual=5)
    issues = validation.validate_leave(leave, employee, [], policy)
    assert any(i.is_error and "النهاية قبل" in i.message for i in issues)


def test_invalid_unit_is_error(employee, policy):
    leave = make_leave(unit="أسبوع")
    issues = validation.validate_leave(leave, employee, [], policy)
    assert any(i.is_error and "الوحدة" in i.message for i in issues)


def test_unknown_type_is_warning_not_blocker(employee, policy):
    leave = make_leave(type="نوع مبتكر", days_actual=3)
    issues = validation.validate_leave(leave, employee, [], policy)
    assert any(i.level == "warning" for i in issues)
    assert not [i for i in issues if i.is_error]


def test_quota_warning(employee, policy):
    from dataclasses import replace
    policy = replace(policy, rules={**policy.rules,
                                    "مرضية": replace(policy.rule("مرضية"), quota_days=20,
                                                     quota_period="year")})
    existing = make_leave(type="مرضية", start_date=date(2026, 2, 1), end_date=date(2026, 2, 15),
                          days_actual=15, order="1")
    new = make_leave(type="مرضية", start_date=date(2026, 3, 1), end_date=date(2026, 3, 10),
                     days_actual=10, order="2")
    issues = validation.validate_leave(new, employee, [existing], policy)
    assert any(i.level == "warning" and "السقف" in i.message for i in issues)


def test_preview_balance_excludes_edited_leave(employee, policy):
    leave = employee.leaves[1]
    before = validation.preview_balance(employee, employee.leaves, policy, None,
                                        today=date(2026, 10, 6), exclude_id=leave.id)
    after = validation.preview_balance(employee, employee.leaves, policy, leave,
                                       today=date(2026, 10, 6))
    assert before.balance == 89      # بدون الإجازة الاعتيادية: لا شيء مأخوذ
    assert before.taken == 0
    assert after.balance == 69


def test_balance_note_reports_negative_as_allowed(employee, policy):
    from amdh_leave.models import Balance
    note, key = validation.balance_note(Balance(balance=-12), policy)
    assert key == "neg" and "مسموح" in note
    note, key = validation.balance_note(Balance(balance=3), policy)
    assert key == "gold"
    note, key = validation.balance_note(Balance(balance=40), policy)
    assert key == "pos"
    note, key = validation.balance_note(Balance(extra={"no_start_date": True}), policy)
    assert key == "muted"


def test_employee_validation():
    issues = validation.validate_employee({"name": "", "gender": "ذكر"}, "", edit_mode=False)
    assert len([i for i in issues if i.is_error]) >= 2

    ok = validation.validate_employee(
        {"name": "أحمد", "gender": "ذكر", "start_date": "2020-01-01", "status": "active"},
        "100", edit_mode=False, exists=lambda _e: False)
    assert not [i for i in ok if i.is_error]

    dup = validation.validate_employee(
        {"name": "أحمد", "gender": "ذكر", "start_date": "2020-01-01"}, "100",
        edit_mode=False, exists=lambda _e: True)
    assert any("مسجل مسبقاً" in i.message for i in dup)

    bad_dates = validation.validate_employee(
        {"name": "أحمد", "gender": "ذكر", "start_date": "2020-01-01", "end_date": "2019-01-01"},
        "100", edit_mode=False)
    assert any("قبل تاريخ المباشرة" in i.message for i in bad_dates)

    future = validation.validate_employee(
        {"name": "أحمد", "gender": "ذكر", "start_date": "2099-01-01"}, "100", edit_mode=False)
    assert any("المستقبل" in i.message for i in future)


def test_import_row_validation():
    ok = validation.validate_import_row(
        {"emp_id": "1", "name": "أ", "start_date": "2020-01-01", "gender": "ذكر"}, set(), set())
    assert not [i for i in ok if i.is_error]

    problems = validation.validate_import_row(
        {"emp_id": "", "name": "", "start_date": "bad", "gender": "x"}, set(), set())
    assert len([i for i in problems if i.is_error]) == 4

    duplicated = validation.validate_import_row(
        {"emp_id": "1", "name": "أ", "start_date": "2020-01-01"}, set(), {"1"})
    assert any("مكرر" in i.message for i in duplicated)

    existing = validation.validate_import_row(
        {"emp_id": "1", "name": "أ", "start_date": "2020-01-01"}, {"1"}, set())
    assert any(i.level == "info" for i in existing)
