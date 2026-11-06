"""اختبارات التصدير: Excel و PDF و HTML (مع تهريب آمن للبيانات)."""

from __future__ import annotations

from datetime import date

import pytest

from amdh_leave.exporters import excel as X
from amdh_leave.exporters import html as H
from amdh_leave.exporters import pdf as P
from amdh_leave.services import balance as B
from amdh_leave.services import reports


@pytest.fixture()
def report_rows(employee, policy):
    return reports.global_report([employee], policy, date(2026, 10, 6))


def test_excel_export_employees_is_numeric_and_rtl(tmp_path, report_rows):
    if not X.HAS_XLSX:
        pytest.skip("openpyxl غير مثبت")
    path = tmp_path / "employees.xlsx"
    X.export_employees(path, report_rows)
    assert path.exists() and path.stat().st_size > 3000

    import openpyxl
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    assert ws.sheet_view.rightToLeft is True
    assert ws["A1"].value == "الرقم الوظيفي"
    assert ws["A2"].value == "57454545"
    # الأرقام تُصدَّر أرقاماً لا نصوصاً (خلاف الإصدار السابق)
    values = {ws.cell(row=1, column=c).value: ws.cell(row=2, column=c).value
              for c in range(1, ws.max_column + 1)}
    assert values["أيام الخدمة"] == 2716
    assert values["الرصيد"] == 69
    assert values["المستحقة"] == 89
    assert ws.auto_filter.ref
    wb.close()


def test_excel_export_leaves_includes_summary_sheet(tmp_path, employee, policy):
    if not X.HAS_XLSX:
        pytest.skip("openpyxl غير مثبت")
    path = tmp_path / "leaves.xlsx"
    X.export_leaves(path, employee, policy, date(2026, 10, 6))
    import openpyxl
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ["سجل الإجازات", "ملخص"]
    ws = wb["سجل الإجازات"]
    assert ws["B2"].value == "5 سنوات"
    assert ws["G2"].value == 1825
    summary = {row[0].value: row[1].value for row in wb["ملخص"].iter_rows()}
    assert summary["الرصيد المتبقي"] == 69
    wb.close()


def test_excel_statement_audit_alerts_and_template(tmp_path, employee, policy, report_rows):
    if not X.HAS_XLSX:
        pytest.skip("openpyxl غير مثبت")
    rows = reports.statement_rows(employee, policy, date(2026, 10, 6))
    balance = B.compute_balance(employee, employee.leaves, policy, date(2026, 10, 6))
    for path, call in (
        (tmp_path / "statement.xlsx", lambda p: X.export_statement(p, employee, policy, rows, balance)),
        (tmp_path / "audit.xlsx", lambda p: X.export_audit(p, [])),
        (tmp_path / "alerts.xlsx", lambda p: X.export_alerts(p, [])),
        (tmp_path / "template.xlsx", X.export_template),
    ):
        call(path)
        assert path.exists() and path.stat().st_size > 1000

    import openpyxl
    wb = openpyxl.load_workbook(tmp_path / "template.xlsx")
    ws = wb.active
    assert [cell.value for cell in ws[1]][:3] == ["emp_id", "name", "job_title"]
    assert ws["A2"].value == "1001"
    wb.close()


def test_excel_read_table_roundtrip(tmp_path, report_rows):
    if not X.HAS_XLSX:
        pytest.skip("openpyxl غير مثبت")
    path = tmp_path / "template.xlsx"
    X.export_template(path)
    assert X.sheet_names(path) == ["قالب الموظفين"]
    headers, rows = X.read_table(path)
    assert "emp_id" in headers
    assert rows and rows[0]["emp_id"] == "1001"
    assert rows[0]["start_date"] == "2019-04-30"


def test_html_escapes_user_data(tmp_path, employee, policy):
    """البيانات المدخلة من المستخدم لا تكسر التقرير ولا تُنفَّذ كوسوم."""
    employee.name = "<script>alert('x')</script>"
    employee.notes = "ملاحظة & خطرة"
    balance = B.compute_balance(employee, employee.leaves, policy, date(2026, 10, 6))
    content = H.employee_detail_html(employee, policy, balance, auto_print=False)
    assert "<script>alert" not in content
    assert "&lt;script&gt;" in content
    assert "ملاحظة &amp; خطرة" in content
    assert balance.balance.__str__() in content


def test_html_reports_are_written_to_reports_dir(tmp_path, report_rows, policy):
    path = H.save(H.global_report_html(report_rows, policy), tmp_path / "reports", "r.html")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert 'dir="rtl"' in text and "احمد زياد رحيمه" in text
    assert "الرصيد السالب مسموح" in text
    assert "الإجمالي" in text


def test_html_alerts_and_calendar(tmp_path, employee, policy):
    alerts = reports.collect_alerts([employee], policy, date(2026, 10, 6))
    text = H.alerts_html(alerts, policy)
    assert "تقرير الإشعارات" in text
    data = reports.calendar_month([employee], policy, 2026, 5)
    calendar_html = H.calendar_html(data, policy)
    assert "تقويم الإجازات" in calendar_html
    assert "احمد زياد رحيمه" in calendar_html


@pytest.mark.skipif(not P.available()[0], reason="خط عربي أو مكتبة PDF غير متوفرة")
def test_pdf_exports_are_created(tmp_path, employee, policy, report_rows):
    path = tmp_path / "employee.pdf"
    P.export_employee_leaves(path, employee, policy)
    assert path.exists() and path.stat().st_size > 5000
    report = tmp_path / "report.pdf"
    P.export_report(report, report_rows, policy)
    assert report.exists() and report.stat().st_size > 5000
    rows = reports.statement_rows(employee, policy, date(2026, 10, 6))
    balance = B.compute_balance(employee, employee.leaves, policy, date(2026, 10, 6))
    statement = tmp_path / "statement.pdf"
    P.export_statement(statement, employee, policy, rows, balance)
    assert statement.exists() and statement.stat().st_size > 3000


def test_pdf_arabic_reshaping_helper():
    if not P.HAS_BIDI:
        pytest.skip("python-bidi غير مثبت")
    assert P.ar("") == ""
    assert P.ar(None) == ""
    assert P.ar("إجازة") != ""
