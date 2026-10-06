"""اختبارات التنبيهات والتقارير ولوحة المؤشرات والتقويم."""

from __future__ import annotations

from datetime import date, timedelta

from amdh_leave.models import Employee, Leave
from amdh_leave.services import balance as B
from amdh_leave.services import reports
from tests.conftest import LEGACY_TODAY, make_leave

TODAY = LEGACY_TODAY


def kinds(alerts):
    return [alert.kind for alert in alerts]


def test_no_alerts_for_healthy_employee(employee, policy):
    assert reports.collect_alerts([employee], policy, TODAY) == []


def test_negative_balance_is_informational_not_error(employee, policy):
    big = make_leave(start_date=date(2026, 5, 1), end_date=date(2026, 8, 31), days_actual=200)
    employee.leaves.append(big)
    alerts = reports.collect_alerts([employee], policy, TODAY)
    negative = [a for a in alerts if a.kind == "negative_balance"]
    assert negative and negative[0].severity == "info"
    assert "مسموح" in negative[0].message
    assert negative[0].emp_id == "57454545"


def test_low_balance_alert(policy):
    """موظف رصيده 2 يوم ⇒ تنبيه «رصيد منخفض» بمستوى متوسط."""
    employee = Employee(emp_id="1", name="منخفض", start_date=date(2020, 1, 1))
    employee.leaves = [make_leave(start_date=date(2026, 1, 1), end_date=date(2026, 1, 10),
                                  days_actual=244)]
    alerts = reports.collect_alerts([employee], policy, TODAY)
    low = [a for a in alerts if a.kind == "low_balance"]
    assert low and low[0].severity == "medium"
    assert "رصيد منخفض" in low[0].message


def test_ending_soon_and_started_today(policy):
    employee = Employee(emp_id="2", name="سارة", institution="صحة ب", start_date=date(2020, 1, 1))
    employee.leaves = [
        make_leave(start_date=TODAY - timedelta(days=8), end_date=TODAY + timedelta(days=2),
                   days_actual=11),
        make_leave(start_date=TODAY, end_date=TODAY + timedelta(days=5), days_actual=6),
    ]
    alerts = reports.collect_alerts([employee], policy, TODAY)
    assert "ending_soon" in kinds(alerts)
    assert "started_today" in kinds(alerts)
    ending = [a for a in alerts if a.kind == "ending_soon"][0]
    assert ending.severity == "medium" and "تنبيه" not in ending.message
    assert "تنتهي بعد 2 يوم" in ending.message


def test_service_exclusion_leave_does_not_trigger_ending_soon(employee, policy):
    employee.leaves = [make_leave(type="5 سنوات", start_date=TODAY - timedelta(days=100),
                                  end_date=TODAY + timedelta(days=1), days_actual=101,
                                  outside_balance=True)]
    assert "ending_soon" not in kinds(reports.collect_alerts([employee], policy, TODAY))


def test_pending_leave_alert(policy):
    employee = Employee(emp_id="3", name="معلق", start_date=date(2020, 1, 1))
    employee.leaves = [make_leave(id=42, start_date=date(2026, 12, 1), end_date=date(2026, 12, 5),
                                  days_actual=5, status="pending")]
    alerts = reports.collect_alerts([employee], policy, TODAY)
    pending = [a for a in alerts if a.kind == "pending"]
    assert pending and pending[0].severity == "medium"
    assert pending[0].leave_id == 42


def test_missing_start_date_alert(policy):
    employee = Employee(emp_id="4", name="بلا تاريخ", start_date=None)
    alerts = reports.collect_alerts([employee], policy, TODAY)
    assert "missing_data" in kinds(alerts)
    assert alerts[0].severity == "medium"


def test_service_ending_alert(policy):
    employee = Employee(emp_id="5", name="متقاعد", start_date=date(1990, 1, 1),
                        end_date=TODAY + timedelta(days=10))
    alerts = reports.collect_alerts([employee], policy, TODAY)
    assert "service_ending" in kinds(alerts)


def test_alerts_sorted_by_severity_and_lines_rendered(employee, policy):
    other = Employee(emp_id="6", name="معلومة", start_date=date(2020, 1, 1))
    other.leaves = [make_leave(start_date=date(2026, 1, 1), end_date=date(2026, 1, 10),
                               days_actual=500)]
    alerts = reports.collect_alerts([employee, other], policy, TODAY)
    severities = [a.severity for a in alerts]
    assert severities == sorted(severities, key=lambda s: reports.SEVERITY_ORDER[s])
    lines = reports.alert_lines(alerts)
    assert all(any(icon in line for icon in "⛔⚠️ℹ️") for line in lines)


# ---------------------------------------------------------------------------
def test_global_report_values_and_sorting(employee, policy):
    other = Employee(emp_id="7", name="أصغر", start_date=date(2025, 1, 1))
    rows = reports.global_report([employee, other], policy, TODAY)
    assert len(rows) == 2
    assert rows[0]["balance"] >= rows[1]["balance"]
    top = rows[0]
    assert top["emp_id"] == "57454545"
    assert (top["raw_days"], top["outside"], top["net_days"], top["earned"], top["taken"],
            top["balance"]) == (2716, 1825, 891, 89, 20, 69)
    assert top["leaves_count"] == 2
    assert top["start_date"] == "2019-04-30"


def test_deleted_employee_excluded_from_reports(employee, policy):
    employee.deleted_at = "2026-01-01 00:00:00"
    assert reports.global_report([employee], policy, TODAY) == []


def test_dashboard_data_kpis(employee, policy):
    data = reports.dashboard_data([employee], policy, TODAY)
    kpis = data["kpis"]
    assert kpis["employees"] == 1
    assert kpis["balance"] == 69 and kpis["earned"] == 89 and kpis["taken"] == 20
    assert kpis["negative"] == 0 and kpis["on_leave_today"] == 0
    assert kpis["institutions"] == 1
    assert data["year"] == TODAY.year
    assert data["top"][0]["emp_id"] == "57454545"
    assert data["by_type"]["5 سنوات"]["days"] == 1825
    assert data["by_type"]["اعتيادية"]["days"] == 20
    assert data["monthly"][3] == 20           # نيسان 2026
    assert sum(data["monthly"]) == 20
    assert "دائرة صحة المحافظة" in data["by_institution"]


def test_dashboard_counts_negative_and_on_leave(policy):
    employee = Employee(emp_id="8", name="سالب", institution="جهة", start_date=date(2020, 1, 1))
    employee.leaves = [make_leave(start_date=TODAY - timedelta(days=3),
                                  end_date=TODAY + timedelta(days=3), days_actual=400)]
    data = reports.dashboard_data([employee], policy, TODAY)
    assert data["kpis"]["negative"] == 1
    assert data["kpis"]["on_leave_today"] == 1
    assert len(data["on_leave"]) == 1
    assert data["on_leave"][0]["name"] == "سالب"


def test_calendar_month_grid_and_days(employee, policy):
    data = reports.calendar_month([employee], policy, 2026, 5)
    assert data["year"] == 2026 and data["month"] == 5
    assert data["weekdays"][0] == "السبت"
    first_week = data["grid"][0]
    assert first_week[6] == date(2026, 5, 1)     # 1 أيار 2026 جمعة ⇒ آخر عمود
    assert len(data["per_day"]) == 19            # 1-19 أيار من الإجازة الاعتيادية
    assert date(2026, 5, 19) in data["per_day"]
    assert date(2026, 5, 20) not in data["per_day"]
    entries = data["per_day"][date(2026, 5, 10)]
    assert entries[0][0].emp_id == "57454545"
    assert entries[0][1].type == "اعتيادية"


def test_calendar_excludes_deleted_and_rejected(policy):
    employee = Employee(emp_id="9", name="محذوف", start_date=date(2020, 1, 1))
    employee.leaves = [
        make_leave(start_date=date(2026, 5, 1), end_date=date(2026, 5, 5), days_actual=5,
                   deleted_at="2026-05-01 10:00:00"),
        make_leave(start_date=date(2026, 5, 6), end_date=date(2026, 5, 8), days_actual=3,
                   status="rejected"),
    ]
    data = reports.calendar_month([employee], policy, 2026, 5)
    assert data["per_day"] == {}


def test_statement_rows_shape(employee, policy):
    rows = reports.statement_rows(employee, policy, TODAY)
    assert len(rows) == 8
    assert rows[0]["start"] == "2019-04-30"
    assert set(rows[0]) >= {"index", "service_days", "earned", "taken", "carry_out", "current"}
    assert rows[-1]["current"] is True
