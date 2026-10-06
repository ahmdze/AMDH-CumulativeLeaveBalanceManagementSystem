"""اختبار معالج استيراد Excel من الواجهة (headless) — مسار الاستيراد كاملاً."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6")
pytest.importorskip("openpyxl")

from PyQt6.QtWidgets import QApplication                      # noqa: E402

from amdh_leave.exporters import excel as X                   # noqa: E402
from amdh_leave.ui import dialogs_db as DDB                   # noqa: E402
from amdh_leave.ui import widgets as W                        # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def silencer(monkeypatch):
    """يُسكت حوارات الرسائل كي لا توقف الاختبار."""
    for name in ("info", "warn", "error"):
        monkeypatch.setattr(W, name, lambda *a, **k: None)
    monkeypatch.setattr(W, "confirm", lambda *a, **k: True)
    return True


def _write_book(path, rows, headers=None):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "الموظفون"
    ws.append(headers or ["emp_id", "name", "job_title", "workplace", "institution",
                          "gender", "start_date"])
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def test_import_wizard_adds_and_updates(qapp, ctx, silencer, tmp_path):
    source = _write_book(tmp_path / "in.xlsx", [
        ["1001", "موظف جديد", "ممرض", "مركز أ", "صحة أ", "ذكر", "2022-03-01"],
        ["57454545", "احمد زياد رحيمه (محدّث)", "تقني طبي", "المركز الصحي",
         "دائرة صحة المحافظة", "ذكر", "2019-04-30"],
        ["", "بلا رقم", "", "", "", "ذكر", "2020-01-01"],          # صف خطأ
    ])
    wizard = DDB.ImportWizardDialog(None, ctx)
    wizard.path = source
    wizard.cb_sheet.clear()
    wizard.cb_sheet.addItem("الموظفون")
    wizard._load_rows("الموظفون")
    assert len(wizard.raw_rows) == 3
    # التلقين التلقائي لمطابقة الأعمدة
    assert wizard.mapping["emp_id"].currentData() == "emp_id"
    assert wizard.mapping["start_date"].currentData() == "start_date"

    wizard._validate()
    assert wizard.btn_import.isEnabled() is True
    levels = [row["level"] for row in wizard._validated]
    assert levels == ["ok", "update", "error"]

    wizard.cb_mode.setCurrentIndex(0)     # تحديث الموجود وإضافة الجديد
    wizard._run_import()

    assert ctx.db.employee_exists("1001")
    assert ctx.db.get_employee("1001").start_date.isoformat() == "2022-03-01"
    assert "محدّث" in ctx.db.get_employee("57454545").name
    # عدد الموظفين = 2 (الصف الخطأ تُجوهل)
    assert ctx.db.stats()["employees"] == 2
    assert any(e.action == "استيراد" for e in ctx.db.list_audit())
    wizard.close()


def test_import_wizard_skip_mode(qapp, ctx, silencer, tmp_path):
    source = _write_book(tmp_path / "in2.xlsx", [
        ["57454545", "لن يُحدَّث", "", "", "", "ذكر", "2019-04-30"],
        ["2002", "موظف ثانٍ", "", "", "", "أنثى", "2023-05-05"],
    ])
    wizard = DDB.ImportWizardDialog(None, ctx)
    wizard.path = source
    wizard.cb_sheet.addItem("الموظفون")
    wizard._load_rows("الموظفون")
    wizard._validate()
    wizard.cb_mode.setCurrentIndex(1)     # إضافة الجديد فقط
    wizard._run_import()

    assert ctx.db.get_employee("57454545").name != "لن يُحدَّث"
    assert ctx.db.employee_exists("2002")
    wizard.close()


def test_import_wizard_handles_arabic_headers(qapp, ctx, silencer, tmp_path):
    source = _write_book(tmp_path / "in3.xlsx", [
        ["3003", "اسم عربي", "عنوان", "مكان", "مؤسسة", "أنثى", "2024-01-02"],
    ], headers=["الرقم الوظيفي", "الاسم", "العنوان الوظيفي", "مكان العمل",
                "المؤسسة", "الجنس", "تاريخ المباشرة"])
    wizard = DDB.ImportWizardDialog(None, ctx)
    wizard.path = source
    wizard.cb_sheet.addItem("الموظفون")
    wizard._load_rows("الموظفون")
    assert wizard.mapping["emp_id"].currentData() == "الرقم الوظيفي"
    assert wizard.mapping["name"].currentData() == "الاسم"
    assert wizard.mapping["start_date"].currentData() == "تاريخ المباشرة"
    wizard._validate()
    wizard._run_import()
    employee = ctx.db.get_employee("3003")
    assert employee.name == "اسم عربي"
    assert employee.gender == "أنثى"
    assert employee.start_date.isoformat() == "2024-01-02"
    wizard.close()


def test_import_wizard_requires_validation_first(qapp, ctx, silencer, tmp_path):
    wizard = DDB.ImportWizardDialog(None, ctx)
    wizard._run_import()          # بلا تحقق ⇒ لا شيء
    assert ctx.db.stats()["employees"] == 1
    wizard.close()


def test_excel_reader_sheet_names(qapp, tmp_path):
    source = _write_book(tmp_path / "sheets.xlsx", [["1", "أ", "", "", "", "ذكر", "2020-01-01"]])
    assert X.sheet_names(source) == ["الموظفون"]
    headers, rows = X.read_table(source, "الموظفون")
    assert "start_date" in headers and len(rows) == 1
