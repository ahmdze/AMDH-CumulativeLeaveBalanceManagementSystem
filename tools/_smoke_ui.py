"""فحص شامل للواجهة (headless) — يبني كل النوافذ ويتحقق من الأرقام."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QSettings, QTimer                      # noqa: E402
from PyQt6.QtWidgets import QApplication                        # noqa: E402

from amdh_leave import config                                   # noqa: E402
from amdh_leave.context import AppContext                       # noqa: E402
from amdh_leave.db import Database                              # noqa: E402
from amdh_leave.logging_setup import setup_logging              # noqa: E402
from amdh_leave.services import balance as B                    # noqa: E402
from amdh_leave.services.backup import BackupService            # noqa: E402
from amdh_leave.services.security import make_session           # noqa: E402
from amdh_leave.ui import theme                                 # noqa: E402
from amdh_leave.ui import dialogs_admin as DA                   # noqa: E402
from amdh_leave.ui import dialogs_about as DAB                  # noqa: E402
from amdh_leave.ui import dialogs_login as DLG                  # noqa: E402
from amdh_leave.ui import dialogs_base as DB_                   # noqa: E402
from amdh_leave.ui import dialogs_db as DDB                     # noqa: E402
from amdh_leave.ui import dialogs_employee as DE                # noqa: E402
from amdh_leave.ui import dialogs_leave as DL                   # noqa: E402
from amdh_leave.ui.calendar_view import CalendarDialog          # noqa: E402
from amdh_leave.ui.dashboard import DashboardDialog             # noqa: E402
from amdh_leave.ui.main_window import MainWindow                # noqa: E402
from amdh_leave.ui.notifications import NotificationsDialog      # noqa: E402
from amdh_leave.ui.register import LeavesRegisterDialog          # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="amdh_ui_"))
from tests.conftest import create_legacy_db                       # noqa: E402
create_legacy_db(TMP / "employees_leave.db")

app = QApplication(sys.argv[:1])
setup_logging(TMP / "logs")
theme.set_theme("dark")
app.setStyleSheet(theme.stylesheet())

# الواجهة عربية فقط باتجاه من اليمين إلى اليسار
from PyQt6.QtCore import Qt as _Qt                              # noqa: E402
app.setLayoutDirection(_Qt.LayoutDirection.RightToLeft)

paths = config.Paths(TMP).ensure()
db = Database(paths.db_path, paths.backups_dir)
policy = db.policy(refresh=True)
ctx = AppContext(paths=paths, db=db, backup=BackupService(db, paths.backups_dir),
                 session=make_session(None, False),
                 settings=QSettings("MyCompany", "AMDH-UITest"))

out: list[str] = []
errors: list[str] = []


def check(name, factory):
    try:
        widget = factory()
        out.append(f"OK   {name}: {type(widget).__name__}")
        return widget
    except Exception as exc:  # noqa: BLE001
        import traceback
        errors.append(f"FAIL {name}: {exc}\n{traceback.format_exc()}")
        return None


def probe():
    window = MainWindow(ctx)
    window.show()
    window._refresh()
    out.append(f"rows in table: {window.table.table.rowCount()}")
    out.append(f"status: {window.lbl_status.text()}")

    # اختيار أول صف والتحقق من ألوان لوحة التفاصيل (المشكلة القديمة: نص أسود)
    window.table.table.setCurrentCell(0, 0)
    window._on_selection()
    for key in ("name", "raw_days", "balance"):
        widget = window.detail_widgets[key]
        out.append(f"detail {key}: style={widget.value.styleSheet()} text={widget.value.text()}")
        if "#000000" in widget.value.styleSheet():
            errors.append(f"لون أسود غير مقروء في: {key}")

    # تجربة كل الثيمات الخمسة
    for theme_key, theme_label in theme.theme_choices():
        window.set_theme(theme_key)
        window._on_selection()
        style = window.detail_widgets["balance"].value.styleSheet()
        if "#000000" in style:
            errors.append(f"الثيم {theme_key}: لون الرصيد أسود")
        out.append(f"theme {theme_key} ({theme_label}): ok | balance color={style}")
    window.set_theme("dark")

    # قائمة الثيمات (كانت مساراً غير مغطّى وتسبّبت في NameError)
    theme_keys = [action.data() for action in window.theme_actions()]
    out.append(f"theme menu: {theme_keys}")
    if len(theme_keys) != 5:
        errors.append(f"عدد الثيمات في القائمة ليس 5: {theme_keys}")

    # مسار كلمة المرور الخاطئة في نافذة الدخول (كان يُسقط البرنامج)
    login = DLG.LoginDialog(window, ctx)
    login.e_user.setText("admin")
    login.e_pass.setText("كلمة-خاطئة")
    login._login()
    if login.user is not None or not login.lbl_error.text():
        errors.append("مسار كلمة المرور الخاطئة لم يعمل كما هو متوقع")
    out.append(f"login failure message: {login.lbl_error.text()[:60]!r}")
    login._locked = False
    login.close()

    emp_id = window.rows[0][0]
    employee = db.get_employee(emp_id)
    balance = B.compute_balance(employee, employee.leaves, policy)
    out.append(f"BALANCE({emp_id}) = {balance}")
    from datetime import date as _today
    expected_raw = (min(_today.today(), employee.end_date) if employee.end_date else _today.today()) - employee.start_date
    expected_raw = max(0, expected_raw.days)
    expected_outside = 1825
    expected_net = max(0, expected_raw - expected_outside)
    expected_earned = expected_net // policy.days_per_leave
    if (balance.raw_days, balance.outside, balance.net_days, balance.earned, balance.taken,
            balance.balance) != (expected_raw, expected_outside, expected_net, expected_earned, 20,
                                 expected_earned - 20):
        errors.append(f"انحرفت الأرقام المعتمدة: {balance} (المتوقع earned={expected_earned}, "
                      f"taken=20)")
    out.append(f"expected: raw={expected_raw} outside={expected_outside} net={expected_net} "
               f"earned={expected_earned} taken=20 balance={expected_earned - 20}")

    check("AboutDialog", lambda: DAB.AboutDialog(window, ctx))
    check("SettingsDialog", lambda: DB_.SettingsDialog(window, ctx))
    check("TrashDialog", lambda: DB_.TrashDialog(window, ctx))
    check("EmployeeDialog(add)", lambda: DE.EmployeeDialog(window, ctx))
    check("EmployeeDialog(edit)", lambda: DE.EmployeeDialog(window, ctx, emp_id))
    check("LeaveDialog(add)", lambda: DL.LeaveDialog(window, ctx, emp_id))
    check("StatementDialog", lambda: DL.StatementDialog(window, ctx, emp_id))
    check("SettlementDialog", lambda: DL.SettlementDialog(window, ctx, emp_id))
    check("LeavesRegisterDialog", lambda: LeavesRegisterDialog(window, ctx, emp_id))
    check("DashboardDialog", lambda: DashboardDialog(window, ctx))
    check("CalendarDialog", lambda: CalendarDialog(window, ctx))
    check("NotificationsDialog", lambda: NotificationsDialog(window, ctx))
    check("RulesEditorDialog", lambda: DA.RulesEditorDialog(window, ctx))
    check("RuleEditDialog", lambda: DA.RuleEditDialog(window, ctx, None, set()))
    check("HolidaysDialog", lambda: DA.HolidaysDialog(window, ctx))
    check("UsersDialog", lambda: DA.UsersDialog(window, ctx))
    check("UserEditDialog", lambda: DA.UserEditDialog(window, ctx, None))
    check("LoginDialog", lambda: DLG.LoginDialog(window, ctx))
    check("AuditDialog", lambda: DA.AuditDialog(window, ctx))
    check("DatabaseOperationsDialog", lambda: DDB.DatabaseOperationsDialog(window, ctx))
    check("ImportWizardDialog", lambda: DDB.ImportWizardDialog(window, ctx))

    leaves = db.list_leaves(emp_id)
    if leaves:
        check("AttachmentsDialog", lambda: DL.AttachmentsDialog(window, ctx, leaves[0].id, emp_id))

    # اختبار حوار الإجازة حسابياً (تسجيل إجازة ثم التراجع)
    dialog = DL.LeaveDialog(window, ctx, emp_id)
    dialog.sp_amount.setValue(3)
    dialog.cb_unit.setCurrentText("يوم")
    candidate = dialog._candidate()
    out.append(f"candidate: {candidate.start_date} -> {candidate.end_date} days={candidate.days_actual}")
    if candidate.days_actual != 3:
        errors.append(f"حساب أيام الإجازة خطأ: {candidate.days_actual}")

    # شهر / سنة بدقة تقويمية
    from datetime import date as _date
    from amdh_leave.services import dates as _D
    checks = [
        (_D.end_date_for(_date(2026, 1, 31), 1, "شهر"), _date(2026, 2, 27)),
        (_D.end_date_for(_date(2026, 2, 1), 1, "شهر"), _date(2026, 2, 28)),
        (_D.end_date_for(_date(2024, 1, 31), 1, "شهر"), _date(2024, 2, 28)),
        (_D.end_date_for(_date(2026, 1, 15), 1, "شهر"), _date(2026, 2, 14)),
        (_D.end_date_for(_date(2020, 4, 30), 5, "سنة"), _date(2025, 4, 29)),
        (_D.days_inclusive(_date(2026, 1, 1), _date(2026, 1, 10)), 10),
    ]
    for got, want in checks:
        if got != want:
            errors.append(f"تاريخ غير متوقع: {got} != {want}")
    out.append("calendar math: ok")

    # ملفات Excel/PDF/HTML
    rows = window._report_rows_from_table()
    from amdh_leave.exporters import excel as X
    from amdh_leave.exporters import html as H
    from amdh_leave.exporters import pdf as P
    p1 = TMP / "out.xlsx"
    X.export_employees(p1, rows)
    X.export_leaves(TMP / "leaves.xlsx", employee, policy)
    X.export_template(TMP / "template.xlsx")
    out.append(f"excel: {p1.stat().st_size} bytes")
    ok, message = P.available()
    if ok:
        P.export_employee_leaves(TMP / "out.pdf", employee, policy)
        P.export_report(TMP / "report.pdf", rows, policy)
        out.append(f"pdf: {(TMP / 'out.pdf').stat().st_size} bytes")
    else:
        out.append(f"pdf unavailable: {message}")
    H.save(H.global_report_html(rows, policy), TMP / "reports", "r.html")
    H.save(H.employee_detail_html(employee, policy, balance), TMP / "reports", "e.html")
    out.append("html: ok")

    window.close()
    app.quit()


QTimer.singleShot(300, probe)
app.exec()

print("\n".join(out))
if errors:
    print("\n=== ERRORS ===")
    print("\n".join(errors))
print(f"\nTMP: {TMP}")
print("RESULT:", "FAIL" if errors else "PASS")
sys.exit(1 if errors else 0)
