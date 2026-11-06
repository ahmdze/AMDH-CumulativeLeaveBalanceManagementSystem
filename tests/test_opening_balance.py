"""اختبارات الرصيد الافتتاحي (المتبقي) ومنع الإجازات المتعارضة."""

from __future__ import annotations

from datetime import date

from amdh_leave.db import Database
from amdh_leave.exporters import excel as X
from amdh_leave.models import Employee, Leave
from amdh_leave.services import balance as B
from amdh_leave.services import validation

TODAY = date(2026, 10, 23)


def make_db(tmp_path):
    db = Database(tmp_path / "opening.db", tmp_path / "backups")
    db.add_employee("1001", {
        "name": "موظف افتتاحي", "institution": "مؤسسة", "start_date": "2019-04-30",
        "gender": "أنثى",
        "opening_balance_set": 1, "opening_balance": 41,
        "opening_balance_date": "2025-12-31", "opening_balance_by": "المحاسب",
        "opening_balance_note": "آخر رصيد معتمد",
    }, "admin")
    return db


def test_opening_balance_is_carried_and_new_service_added(tmp_path):
    db = make_db(tmp_path)
    employee = db.get_employee("1001")
    result = B.compute_balance(employee, employee.leaves, db.policy(), TODAY)
    assert result.has_opening is True
    assert result.opening_balance == 41
    assert result.service_days_after == (TODAY - date(2026, 1, 1)).days
    assert result.earned_after == 29
    assert result.balance == 70
    db.close()


def test_opening_balance_subtracts_only_leaves_after_date(tmp_path):
    db = make_db(tmp_path)
    db.add_leave("1001", {"type": "اعتيادية", "start_date": "2026-02-01",
                          "end_date": "2026-02-05", "amount": 5, "unit": "يوم",
                          "days_actual": 5, "status": "approved"}, "admin")
    employee = db.get_employee("1001")
    result = B.compute_balance(employee, employee.leaves, db.policy(), TODAY)
    assert result.taken_after == 5
    assert result.balance == 65
    db.close()


def test_leave_before_opening_date_is_rejected(tmp_path):
    db = make_db(tmp_path)
    employee = db.get_employee("1001")
    leave = Leave(emp_id="1001", type="اعتيادية", start_date=date(2025, 12, 31),
                  end_date=date(2026, 1, 2), amount=3, unit="يوم", days_actual=3)
    issues = validation.validate_leave(leave, employee, [], db.policy())
    assert any(issue.is_error and "الرصيد الافتتاحي" in issue.message for issue in issues)
    db.close()


def test_statement_has_opening_line_and_years_after(tmp_path):
    db = make_db(tmp_path)
    employee = db.get_employee("1001")
    statement = B.yearly_statement(employee, employee.leaves, db.policy(), TODAY)
    assert statement.opening_balance == 41
    assert statement.opening_date == date(2025, 12, 31)
    assert statement.lines and statement.lines[0].start == date(2026, 1, 1)
    assert statement.balance.balance == 70
    db.close()


def test_edit_opening_balance_is_audited(tmp_path):
    db = make_db(tmp_path)
    fields = db.get_employee("1001").to_fields()
    fields["opening_balance"] = 50
    db.update_employee("1001", fields, "admin")
    assert db.get_employee("1001").opening_balance == 50
    history = db.conn.execute(
        "SELECT old_balance, new_balance, changed_by FROM employee_opening_history "
        "WHERE emp_id='1001'").fetchall()
    assert history and history[-1][0] == 41 and history[-1][1] == 50
    db.close()


def test_opening_conflict_helper_detects_existing_leave(tmp_path):
    db = make_db(tmp_path)
    fields = db.get_employee("1001").to_fields()
    leave = Leave(emp_id="1001", type="اعتيادية", start_date=date(2025, 12, 31),
                  end_date=date(2026, 1, 2), amount=3, unit="يوم", days_actual=3)
    issues = validation.validate_opening_against_leaves(fields, [leave], db.policy())
    assert any(issue.is_error for issue in issues)
    db.close()


def test_maternity_is_service_exclusion_without_balance_deduction(tmp_path):
    db = make_db(tmp_path)
    policy = db.policy()
    rule = policy.rule("أمومة")
    assert rule.consumes_balance is False
    assert rule.service_exclusion is True
    employee = db.get_employee("1001")
    maternity = Leave(emp_id="1001", type="أمومة", start_date=date(2026, 1, 1),
                      end_date=date(2026, 3, 1), amount=60, unit="يوم", days_actual=60,
                      order="1")
    issues = validation.validate_leave(maternity, employee, [], policy)
    assert not any(issue.is_error for issue in issues)
    result = B.compute_balance(employee, [maternity], policy, TODAY)
    assert result.taken_after == 0
    assert result.balance < 70          # أيام الأمومة لا تُحتسب خدمةً
    assert result.balance == 41 + max(0, (TODAY - date(2026, 1, 1)).days - 60) // 10
    db.close()


def test_maternity_before_opening_is_allowed_without_recounting(tmp_path):
    db = make_db(tmp_path)
    employee = db.get_employee("1001")
    maternity = Leave(emp_id="1001", type="أمومة", start_date=date(2025, 6, 1),
                      end_date=date(2025, 7, 30), amount=60, unit="يوم", days_actual=60,
                      order="2")
    issues = validation.validate_leave(maternity, employee, [], db.policy())
    assert not any(issue.is_error for issue in issues)
    result = B.compute_balance(employee, [maternity], db.policy(), TODAY)
    assert result.balance == 70
    assert result.taken_after == 0
    db.close()


def test_employee_master_excel_contains_all_fields(tmp_path):
    db = make_db(tmp_path)
    employee = db.get_employee("1001")
    path = X.export_employee_master(tmp_path / "employees.xlsx", [employee])
    import openpyxl
    workbook = openpyxl.load_workbook(path)
    sheet = workbook["الموظفون"]
    headers = [cell.value for cell in sheet[1]]
    assert "له رصيد افتتاحي" in headers and "من قام بالحساب" in headers
    values = {headers[index]: cell.value for index, cell in enumerate(sheet[2])}
    assert values["الرصيد الافتتاحي (أيام)"] == 41
    assert values["من قام بالحساب"] == "المحاسب"
    workbook.close()
    template = X.export_employee_template(tmp_path / "template.xlsx")
    assert template.exists() and template.stat().st_size > 1000
    db.close()
