"""اختبارات واجهة المؤسسات والاستيراد (بلا عرض فعلي — offscreen).

تُبنى النوافذ وتُستدعى مساراتها الداخلية بلا حوارات ملفات، لأن أعطال هذه المسارات
(استيراد ناقص، اسم وحدة مفقود) لا تظهر إلا عند فتح النافذة فعلياً.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtCore import QSettings                             # noqa: E402
from PyQt6.QtWidgets import QApplication                       # noqa: E402

from amdh_leave.context import AppContext                      # noqa: E402
from amdh_leave.db import Database                             # noqa: E402
from amdh_leave.services import backup as BK                   # noqa: E402
from amdh_leave.services import institutions as INST           # noqa: E402
from amdh_leave.services import security as sec                # noqa: E402
from amdh_leave.services import transfer as T                  # noqa: E402
from amdh_leave.ui import dialogs_import as DI                 # noqa: E402
from amdh_leave.ui import dialogs_institutions as DINST        # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def ui_ctx(tmp_path, qapp) -> AppContext:
    db = Database(tmp_path / "center.db", tmp_path / "backups")
    db.set_meta({"auth_enabled": "0", "center_institution": "مركز الدائرة"})
    db.save_institution({"name": "مركز الدائرة", "code": "C0", "kind": "مركز الدائرة"}, "admin")
    db.save_institution({"name": "مستشفى الكرامة", "code": "H1"}, "admin")
    db.set_center_institution("مركز الدائرة")
    paths = type("Paths", (), {"db_path": db.path, "data_dir": tmp_path,
                               "backups_dir": tmp_path / "backups",
                               "attachments_dir": tmp_path / "attachments",
                               "reports_dir": tmp_path / "reports"})()
    (tmp_path / "attachments").mkdir(exist_ok=True)
    account = db.get_user("admin")
    return AppContext(paths=paths, db=db, backup=BK.BackupService(db, tmp_path / "backups"),
                      session=sec.make_session(account, False),
                      settings=QSettings("MyCompany", "AMDH-UI-Test"))


def test_institutions_dialog_builds_and_filters(ui_ctx):
    dialog = DINST.InstitutionsDialog(None, ui_ctx)
    assert dialog.table.table.rowCount() == 2
    assert "المؤسسات: 2" in dialog.lbl_summary.text()

    dialog.e_search.setText("الكرامة")
    assert dialog.table.table.rowCount() == 1
    dialog.e_search.setText("")
    dialog.cb_filter.setCurrentIndex(1)                 # أرسلت هذا الشهر
    assert dialog.table.table.rowCount() == 0
    dialog.cb_filter.setCurrentIndex(0)
    dialog.close()


def test_institution_dialog_creates_user(ui_ctx):
    dialog = DINST.InstitutionDialog(None, ui_ctx)
    dialog.e_name.setText("مستشفى النور")
    dialog.e_code.setText("H7")
    dialog.e_manager.setText("د. سارة")
    dialog.chk_user.setChecked(True)
    dialog._save()
    assert dialog.result_data is not None
    assert dialog.created_user is not None
    assert dialog.created_user["username"] == "h7"
    institution = ui_ctx.db.get_institution("مستشفى النور")
    assert institution is not None and institution.username == "h7"
    account = ui_ctx.db.get_user("h7")
    assert account is not None and account.institution == "مستشفى النور"
    assert sec.verify_password(dialog.created_user["password"], account.password_hash,
                               account.salt, account.iterations)
    dialog.close()


def test_import_institutions_dialog_preview(ui_ctx, tmp_path):
    template = INST.export_template(tmp_path / "template.xlsx")
    dialog = DINST.ImportInstitutionsDialog(None, ui_ctx, template)
    assert dialog.rows, "القالب يحوي صفوفاً"
    assert "مستشفى الكرامة" in dialog.preview.toPlainText()
    dialog.chk_users.setChecked(True)
    dialog.chk_update.setChecked(True)
    dialog._import()
    assert dialog.result is not None
    assert dialog.result["added"] == 1, "مستشفى الكرامة موجود مسبقاً فيُحدَّث"
    assert dialog.result["updated"] == 1
    assert len(dialog.result["users"]) == 2
    assert ui_ctx.db.get_institution("مركز صحي النور") is not None
    dialog.close()


def test_transfer_import_dialog_preview_and_report(ui_ctx, tmp_path):
    # مؤسسة تجهّز ملف نقل
    hospital = Database(tmp_path / "h.db", tmp_path / "b")
    hospital.save_institution({"name": "مستشفى الكرامة", "code": "H1"}, "admin")
    hospital.add_employee("3300", {"name": "سالم محمد", "institution": "مستشفى الكرامة",
                                   "start_date": "2018-03-01"}, "h1")
    hospital.add_leave("3300", {"type": "عادية", "start_date": "2026-05-01",
                                "end_date": "2026-05-10", "days_actual": 10,
                                "amount": 10, "order": "T-1"}, "h1")
    manifest = T.export_transfer(hospital, tmp_path / "transfer.amdhz",
                                 institution="مستشفى الكرامة", user="h1",
                                 attachments_dir=tmp_path / "att")
    path = Path(manifest["path"])
    hospital.close()

    dialog = DI.TransferImportDialog(None, ui_ctx)
    dialog.path = path
    dialog.e_path.setText(str(path))
    dialog.e_institution.setText("مستشفى الكرامة")
    dialog._preview()
    assert dialog.report is not None
    assert dialog.report.employees_added == 1 and dialog.report.leaves_added == 1
    assert "موظفون" in dialog.summary.toPlainText()
    assert dialog.btn_apply.isEnabled()
    assert "سيُضاف" in dialog.details.toPlainText()

    # التنفيذ الفعلي (بلا حوارات)
    report = T.apply_transfer(ui_ctx.db, path, dialog._options(), user="admin",
                              attachments_dir=tmp_path / "attachments")
    assert report.leaves_added == 1
    assert ui_ctx.db.get_employee("3300") is not None

    report_dialog = DI.ReportDialog(None, ui_ctx, report)
    assert report_dialog.tabs.count() == 5
    report_dialog.close()
    history = DI.ImportHistoryDialog(None, ui_ctx)
    assert history.table.table.rowCount() >= 1
    history.close()
    dialog.close()


def test_employee_dialog_uses_institution_combo(ui_ctx):
    from amdh_leave.ui.dialogs_employee import EmployeeDialog
    ui_ctx.db.add_employee("4400", {"name": "هدى", "institution": "مستشفى الكرامة",
                                    "start_date": "2019-01-01"}, "admin")
    dialog = EmployeeDialog(None, ui_ctx, emp_id="4400")
    items = [dialog.e_institution.itemText(index)
             for index in range(dialog.e_institution.count())]
    assert any("مستشفى الكرامة" in item for item in items)
    assert dialog.e_institution.currentData() == "مستشفى الكرامة"
    assert dialog._fields()["institution"] == "مستشفى الكرامة"
    dialog.close()


def test_institution_row_export_and_status(ui_ctx, tmp_path):
    path = INST.export_excel(tmp_path / "institutions.xlsx", ui_ctx.db)
    headers, rows = INST.read_excel(path)
    assert len(rows) == 2
    status = INST.institutions_status(ui_ctx.db)
    assert len(status) == 2
    assert any(row["is_center"] for row in status)
    credentials = INST.export_credentials(tmp_path / "c.xlsx",
                                         [{"institution": "أ", "username": "h1",
                                           "password": "12345678"}])
    assert credentials.exists()


def test_ui_scoped_editor_cannot_see_institutions_dialog(ui_ctx):
    """المستخدم المقيّد لا يملك صلاحية إدارة المؤسسات ولا الاستيراد."""
    institution = ui_ctx.db.get_institution("مستشفى الكرامة")
    account, _password = INST.create_user_for_institution(ui_ctx.db, institution, user="admin")
    session = sec.make_session(account, False)
    assert session.can("export_transfer") is True
    assert session.can("import_transfer") is False
    assert session.can("manage_institutions") is False
    assert session.scoped_institution == "مستشفى الكرامة"
