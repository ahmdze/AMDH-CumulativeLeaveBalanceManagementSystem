"""النافذة الرئيسية: الجدول، الفلاتر، التفاصيل، الشريط الجانبي، والاختصارات."""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QFont, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMenu, QScrollArea, QVBoxLayout, QWidget,
)

from .. import config
from ..exporters import excel as X
from ..exporters import html as H
from ..exporters import pdf as P
from ..services import balance as B
from ..services import dates as D
from ..services import reports
from . import theme, widgets as W
from .calendar_view import CalendarDialog
from .dashboard import DashboardDialog
from .dialogs_admin import AuditDialog, HolidaysDialog, RulesEditorDialog, UsersDialog
from .dialogs_base import AboutDialog, SettingsDialog, TrashDialog
from .dialogs_db import DatabaseOperationsDialog
from .dialogs_employee import EmployeeDialog
from .dialogs_leave import AttachmentsDialog, LeaveDialog, SettlementDialog, StatementDialog
from .notifications import NotificationsDialog
from .register import LeavesRegisterDialog

COLUMNS = [
    ("الرقم الوظيفي", 120), ("الاسم", 200), ("العنوان الوظيفي", 150), ("مكان العمل", 140),
    ("المؤسسة", 160), ("الجنس", 60), ("المباشرة", 100), ("انتهاء الخدمة", 100),
    ("أيام الخدمة", 90), ("خارج الرصيد", 90), ("الدوام المحسوبة", 110), ("المستحقة", 85),
    ("المأخوذة", 85), ("الرصيد", 85),
]
NUMERIC_COLUMNS = {8, 9, 10, 11, 12, 13}
DETAIL_ITEMS = [
    ("name", "الاسم"), ("job_title", "العنوان الوظيفي"), ("workplace", "مكان العمل"),
    ("institution", "المؤسسة"), ("gender", "الجنس"), ("start_date", "تاريخ المباشرة"),
    ("end_date", "انتهاء الخدمة"), ("raw_days", "أيام الخدمة"), ("outside", "خارج الرصيد"),
    ("net_days", "الدوام المحسوبة"), ("earned", "المستحقة"), ("taken", "المأخوذة"),
    ("balance", "الرصيد"),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.policy = ctx.db.policy(refresh=True)
        self.rows: list[dict] = []
        self.setWindowTitle(f"{config.APP_NAME} — الإصدار {config.APP_VERSION}")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(1360, 820)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._refresh)
        self._build()
        self._restore_state()
        self._load_filters()
        self._refresh()
        self._startup_tasks()

    # ==================================================================
    # البناء
    # ==================================================================
    def _build(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())
        body = QHBoxLayout()
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(10)
        body.addWidget(self._sidebar())
        body.addLayout(self._center(), 1)
        root.addLayout(body, 1)
        self._status()

    # -- الترويسة -------------------------------------------------------
    def _header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("Surface")
        header.setFixedHeight(56)
        layout = QHBoxLayout(header)
        self.lbl_title = QLabel(config.APP_NAME)
        self.lbl_title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.lbl_title.setStyleSheet(theme.label_style("accent", 18, bold=True))
        layout.addWidget(self.lbl_title)
        layout.addStretch()
        self.lbl_policy = W.muted_label(self.policy.annual_rate_note)
        layout.addWidget(self.lbl_policy)
        layout.addWidget(W.separator())
        self.lbl_user = W.muted_label(self._user_text())
        layout.addWidget(self.lbl_user)
        layout.addWidget(W.button("🌓 الوضع", "Ghost", self._toggle_theme, width=100,
                                  tooltip="تبديل الوضع الداكن/الفاتح"))
        return header

    def _user_text(self) -> str:
        session = self.ctx.session
        scope = session.scoped_institution or "كل المؤسسات"
        return f"المستخدم: {session.display_name} ({config.ROLE_LABELS.get(session.role, session.role)}) — {scope}"

    # -- الشريط الجانبي --------------------------------------------------
    def _sidebar(self) -> QScrollArea:
        area = QScrollArea()
        area.setFixedWidth(228)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        holder = QWidget()
        area.setWidget(holder)
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        def add(text: str, style: str, slot, permission: str | None = None) -> None:
            btn = W.button(text, style, slot)
            if permission and not self.ctx.can(permission):
                btn.setEnabled(False)
                btn.setToolTip("لا تملك صلاحية هذا الإجراء")
            layout.addWidget(btn)

        add("➕  إضافة موظف جديد", "Accent", self._add_employee, "edit_employee")
        add("✏  تعديل الموظف", "Ghost", self._edit_employee, "edit_employee")
        add("🗑  حذف الموظف", "Warn", self._delete_employee, "delete_employee")
        layout.addWidget(W.separator())
        add("📝  تسجيل إجازة", "Blue", self._quick_leave, "edit_leave")
        add("📅  سجل الإجازات", "Ghost", self._open_register)
        add("📎  مرفقات الإجازة", "Ghost", self._open_attachments, "manage_attachments")
        layout.addWidget(W.separator())
        add("📊  لوحة المؤشرات", "Gold", self._open_dashboard)
        add("🗓  تقويم الإجازات", "Ghost", self._open_calendar)
        add("🔔  التنبيهات", "Ghost", self._open_notifications)
        add("📄  تقرير إجمالي", "Ghost", self._global_report)
        add("🧾  كشف حساب الموظف", "Ghost", self._open_statement)
        add("📤  تصفية نهاية الخدمة", "Ghost", self._open_settlement)
        layout.addWidget(W.separator())
        add("📋  ضوابط أنواع الإجازات", "Ghost", self._open_rules, "edit_rules")
        add("🗓  العطل الرسمية", "Ghost", self._open_holidays, "manage_holidays")
        add("👥  المستخدمون", "Ghost", self._open_users, "manage_users")
        add("📜  سجل التدقيق", "Ghost", self._open_audit, "view_audit")
        add("🗄️  عمليات قاعدة البيانات", "Ghost", self._open_db_ops)
        add("🗑  سلة المحذوفات", "Ghost", self._open_trash, "purge")
        layout.addWidget(W.separator())
        add("⚙  الإعدادات", "Ghost", self._open_settings)
        add("ℹ  حول", "Ghost", self._open_about)
        layout.addWidget(W.button("🚪  خروج", "Warn", self.close))
        layout.addStretch()
        return area

    # -- المنطقة الوسطى -------------------------------------------------
    def _center(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(8)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("البحث:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("الاسم أو الرقم الوظيفي أو العنوان (Ctrl+F)")
        self.search.textChanged.connect(lambda: self._search_timer.start())
        self.search.setClearButtonEnabled(True)
        filters.addWidget(self.search, 3)
        filters.addWidget(QLabel("مكان العمل:"))
        self.cb_workplace = QComboBox()
        self.cb_workplace.setMinimumWidth(140)
        self.cb_workplace.currentTextChanged.connect(self._refresh)
        filters.addWidget(self.cb_workplace)
        filters.addWidget(QLabel("المؤسسة:"))
        self.cb_institution = QComboBox()
        self.cb_institution.setMinimumWidth(150)
        self.cb_institution.currentTextChanged.connect(self._refresh)
        filters.addWidget(self.cb_institution)
        filters.addWidget(W.button("✖ مسح الفلاتر", "Ghost", self._clear_filters))
        filters.addStretch()
        filters.addWidget(W.button("📊 تصدير المعروض", "Gold", lambda: self._export(False)))
        filters.addWidget(W.button("📊 تصدير الكل", "Gold", lambda: self._export(True)))
        layout.addLayout(filters)

        self.table = W.TablePanel([c[0] for c in COLUMNS])
        self.table.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.table.customContextMenuRequested.connect(self._context_menu)
        header = self.table.table.horizontalHeader()
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._column_menu)
        self.table.table.itemSelectionChanged.connect(self._on_selection)
        self.table.table.doubleClicked.connect(lambda _i: self._open_register())
        for i, (_name, width) in enumerate(COLUMNS):
            self.table.table.setColumnWidth(i, width)
        layout.addWidget(self.table, 1)

        details = W.card()
        details.setFixedHeight(150)
        grid = QGridLayout(details)
        grid.setSpacing(4)
        self.detail_widgets: dict[str, W.LabeledValue] = {}
        for i, (key, title) in enumerate(DETAIL_ITEMS):
            widget = W.LabeledValue(title)
            grid.addWidget(widget, i // 7, i % 7)
            self.detail_widgets[key] = widget
        layout.addWidget(details)
        return layout

    def _status(self) -> None:
        bar = self.statusBar()
        self.lbl_status = QLabel("")
        bar.addWidget(self.lbl_status)
        self.lbl_path = QLabel(f"قاعدة البيانات: {self.ctx.paths.db_path}")
        bar.addPermanentWidget(self.lbl_path)

    # ==================================================================
    # البيانات
    # ==================================================================
    def _load_filters(self) -> None:
        for combo, values in ((self.cb_workplace, self.ctx.workplaces()),
                              (self.cb_institution, self.ctx.institutions())):
            combo.blockSignals(True)
            current = combo.currentText()
            combo.clear()
            combo.addItem("الكل")
            combo.addItems(values)
            if current and combo.findText(current) >= 0:
                combo.setCurrentText(current)
            combo.blockSignals(False)

    def _clear_filters(self) -> None:
        self.search.clear()
        self.cb_workplace.setCurrentIndex(0)
        self.cb_institution.setCurrentIndex(0)
        self._refresh()

    def _filters(self) -> tuple[str, str, str]:
        workplace = self.cb_workplace.currentText().strip()
        institution = self.cb_institution.currentText().strip()
        return (self.search.text().strip(),
                "" if workplace == "الكل" else workplace,
                "" if institution == "الكل" else institution)

    def _refresh(self) -> None:
        self.policy = self.ctx.db.policy(refresh=True)
        q, workplace, institution = self._filters()
        employees = self.ctx.employees(q, workplace, institution)
        rows, colors = [], {}
        totals = {"raw": 0, "outside": 0, "net": 0, "earned": 0, "taken": 0, "balance": 0,
                  "negative": 0}
        for r, emp in enumerate(employees):
            balance = B.compute_balance(emp, emp.leaves, self.policy)
            rows.append([
                emp.emp_id, emp.name, emp.job_title, emp.workplace, emp.institution, emp.gender,
                D.to_iso(emp.start_date), D.to_iso(emp.end_date), balance.raw_days, balance.outside,
                balance.net_days, balance.earned, balance.taken, balance.balance,
            ])
            colors[(r, 13)] = theme.balance_color(balance.balance, self.policy.low_balance_days)
            totals["raw"] += balance.raw_days
            totals["outside"] += balance.outside
            totals["net"] += balance.net_days
            totals["earned"] += balance.earned
            totals["taken"] += balance.taken
            totals["balance"] += balance.balance
            totals["negative"] += 1 if balance.balance < 0 else 0
        self.rows = rows
        footer = (f"عدد الموظفين المعروضين: {len(rows)} | إجمالي المستحقة: {totals['earned']} يوم | "
                  f"المأخوذة: {totals['taken']} يوم | إجمالي الرصيد: {totals['balance']} يوم | "
                  f"أرصدة سالبة: {totals['negative']} (مسموح حسب الضوابط)")
        self.table.set_rows(rows, numeric_columns=NUMERIC_COLUMNS, colors=colors,
                            empty_text="لا يوجد موظفون مطابقون للبحث أو الفلاتر", footer=footer)
        if hasattr(self, "lbl_status"):
            self.lbl_status.setText(f"الموظفون: {len(rows)} — آخر تحديث: "
                                    f"{date.today().strftime('%Y-%m-%d')}")
        self._on_selection()

    def _current_id(self) -> str | None:
        row = self.table.table.currentRow()
        if row < 0 or row >= len(self.rows):
            return None
        return self.rows[row][0]

    def _on_selection(self) -> None:
        emp_id = self._current_id()
        if not emp_id:
            for widget in self.detail_widgets.values():
                widget.set_value("—", "muted")
            return
        employee = self.ctx.db.get_employee(emp_id)
        if not employee:
            return
        balance = B.compute_balance(employee, employee.leaves, self.policy)
        for key, widget in self.detail_widgets.items():
            if key in ("raw_days", "outside", "net_days", "earned", "taken", "balance"):
                value = getattr(balance, key)
                color_key = "text"
                if key == "earned":
                    color_key = "pos"
                elif key == "taken":
                    color_key = "gold"
                elif key == "balance":
                    color_key = theme.balance_color(balance.balance, self.policy.low_balance_days)
                widget.set_value(value, color_key, " يوم")
            elif key in ("start_date", "end_date"):
                widget.set_value(D.to_iso(getattr(employee, key)) or "—", "text")
            else:
                widget.set_value(getattr(employee, key) or "—", "text")

    # ==================================================================
    # الإجراءات
    # ==================================================================
    def _require(self, emp_id: str | None) -> str | None:
        if not emp_id:
            W.warn(self, "حدد موظفاً من الجدول أولاً.")
            return None
        return emp_id

    def _add_employee(self) -> None:
        EmployeeDialog(self, self.ctx, on_save=self._after_change).exec()

    def _edit_employee(self) -> None:
        emp_id = self._require(self._current_id())
        if emp_id:
            EmployeeDialog(self, self.ctx, emp_id, on_save=self._after_change).exec()

    def _delete_employee(self) -> None:
        emp_id = self._require(self._current_id())
        if not emp_id:
            return
        if not self.ctx.can("delete_employee"):
            W.error(self, "لا تملك صلاحية حذف الموظفين.")
            return
        employee = self.ctx.db.get_employee(emp_id)
        if not W.confirm(self, f"حذف الموظف «{employee.name}» مع إجازاته؟\n"
                               "الحذف ناعم ويمكن الاستعادة من سلة المحذوفات."):
            return
        self.ctx.db.soft_delete_employee(emp_id, self.ctx.user())
        self._after_change()

    def _quick_leave(self) -> None:
        emp_id = self._require(self._current_id())
        if emp_id:
            LeaveDialog(self, self.ctx, emp_id, on_save=self._after_change).exec()

    def _open_register(self) -> None:
        emp_id = self._require(self._current_id())
        if emp_id:
            LeavesRegisterDialog(self, self.ctx, emp_id, on_save=self._after_change).exec()

    def _open_attachments(self) -> None:
        emp_id = self._require(self._current_id())
        if not emp_id:
            return
        leave_id = self._pick_leave(emp_id)
        if leave_id:
            AttachmentsDialog(self, self.ctx, leave_id, emp_id).exec()

    def _pick_leave(self, emp_id: str) -> int | None:
        leaves = self.ctx.db.list_leaves(emp_id)
        if not leaves:
            W.info(self, "لا توجد إجازات مسجلة لهذا الموظف.")
            return None
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        for leave in leaves:
            label = (f"{leave.type} — {D.to_iso(leave.start_date)} "
                     f"({leave.days_actual} يوم)")
            action = QAction(label, self)
            action.triggered.connect(lambda _c=False, lid=leave.id: self._chosen_leave.append(lid))
            menu.addAction(action)
        self._chosen_leave: list[int] = []
        menu.exec(self.table.table.viewport().mapToGlobal(self.table.table.viewport().rect().center()))
        return self._chosen_leave[0] if self._chosen_leave else None

    def _open_statement(self) -> None:
        emp_id = self._require(self._current_id())
        if emp_id:
            StatementDialog(self, self.ctx, emp_id).exec()

    def _open_settlement(self) -> None:
        emp_id = self._require(self._current_id())
        if emp_id:
            SettlementDialog(self, self.ctx, emp_id).exec()

    def _open_dashboard(self) -> None:
        DashboardDialog(self, self.ctx).exec()
        self._after_change()

    def _open_calendar(self) -> None:
        CalendarDialog(self, self.ctx).exec()

    def _open_notifications(self) -> None:
        NotificationsDialog(self, self.ctx).exec()

    def _open_rules(self) -> None:
        RulesEditorDialog(self, self.ctx).exec()
        self._after_change()

    def _open_holidays(self) -> None:
        HolidaysDialog(self, self.ctx).exec()
        self._after_change()

    def _open_users(self) -> None:
        UsersDialog(self, self.ctx).exec()

    def _open_audit(self) -> None:
        AuditDialog(self, self.ctx).exec()

    def _open_db_ops(self) -> None:
        DatabaseOperationsDialog(self, self.ctx, refresh_callback=self._after_change).exec()

    def _open_trash(self) -> None:
        TrashDialog(self, self.ctx).exec()
        self._after_change()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self, self.ctx)
        dialog.theme_changed.connect(self._on_settings_saved)
        dialog.exec()

    def _on_settings_saved(self, _old_theme: str) -> None:
        self.policy = self.ctx.db.policy(refresh=True)
        self.lbl_policy.setText(self.policy.annual_rate_note)
        self._apply_theme()
        self._after_change()

    def _open_about(self) -> None:
        AboutDialog(self, self.ctx).exec()

    def _after_change(self) -> None:
        self._load_filters()
        self._refresh()

    # ==================================================================
    # التصدير والطباعة
    # ==================================================================
    def _export(self, all_rows: bool) -> None:
        if not self.rows:
            W.warn(self, "لا توجد بيانات للتصدير.")
            return
        if all_rows:
            employees = self.ctx.employees()
            rows = reports.global_report(employees, self.policy)
            label = "كل الموظفين"
        else:
            rows = self._report_rows_from_table()
            label = "المعروضين"
        path, _ = QFileDialog.getSaveFileName(self, f"تصدير {label}",
                                              f"employees_{date.today()}.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            X.export_employees(path, rows, title=label)
            W.info(self, f"تم التصدير ({label}):\n{path}")
            self.ctx.db.log(self.ctx.user(), "تصدير", "employees", label, path)
        except Exception as exc:
            W.error(self, f"فشل التصدير: {exc}")

    def _report_rows_from_table(self) -> list[dict]:
        q, workplace, institution = self._filters()
        employees = self.ctx.employees(q, workplace, institution)
        return reports.global_report(employees, self.policy)

    def _global_report(self) -> None:
        employees = self.ctx.employees()
        rows = reports.global_report(employees, self.policy)
        if not rows:
            W.info(self, "لا توجد بيانات للتصدير.")
            return
        content = H.global_report_html(rows, self.policy, "تقرير الإجازات التراكمية",
                                       self.ctx.session.scoped_institution)
        path = H.save_and_open(content, self.ctx.paths.reports_dir, "global_report.html")
        W.info(self, f"تم فتح التقرير في المتصفح:\n{path.name}")

    def _print_employee(self) -> None:
        emp_id = self._require(self._current_id())
        if not emp_id:
            return
        employee = self.ctx.db.get_employee(emp_id)
        balance = B.compute_balance(employee, employee.leaves, self.policy)
        statement = B.yearly_statement(employee, employee.leaves, self.policy)
        content = H.employee_detail_html(employee, self.policy, balance, statement)
        path = H.save_and_open(content, self.ctx.paths.reports_dir, f"employee_{emp_id}.html")
        W.info(self, f"تم فتح التقرير في المتصفح:\n{path.name}")

    def _export_pdf_employee(self) -> None:
        emp_id = self._require(self._current_id())
        if not emp_id:
            return
        employee = self.ctx.db.get_employee(emp_id)
        path, _ = QFileDialog.getSaveFileName(self, "حفظ PDF", f"employee_{emp_id}.pdf", "PDF (*.pdf)")
        if not path:
            return
        try:
            P.export_employee_leaves(path, employee, self.policy)
            W.info(self, f"تم التصدير:\n{path}")
        except Exception as exc:
            W.error(self, f"فشل التصدير: {exc}")

    # ==================================================================
    # القوائم والسياق
    # ==================================================================
    def _context_menu(self, pos) -> None:
        if not self._current_id():
            return
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        actions = [
            ("🖨 طباعة التفاصيل", self._print_employee),
            ("📄 تصدير PDF", self._export_pdf_employee),
            ("✏ تعديل الموظف", self._edit_employee),
            ("📅 سجل الإجازات", self._open_register),
            ("📝 تسجيل إجازة", self._quick_leave),
            ("🧾 كشف حساب الرصيد", self._open_statement),
            ("📤 تصفية نهاية الخدمة", self._open_settlement),
            ("📎 مرفقات الإجازة", self._open_attachments),
            ("🗑 حذف الموظف", self._delete_employee),
        ]
        for text, slot in actions:
            action = QAction(text, self)
            action.triggered.connect(slot)
            menu.addAction(action)
        menu.exec(self.table.table.viewport().mapToGlobal(pos))

    def _column_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        hidden = self._hidden_columns()
        for i, (name, _width) in enumerate(COLUMNS):
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(i not in hidden)
            action.toggled.connect(lambda checked, index=i: self._toggle_column(checked, index))
            menu.addAction(action)
        menu.exec(self.table.table.horizontalHeader().mapToGlobal(pos))

    def _hidden_columns(self) -> set[int]:
        raw = self.ctx.ui_get("hidden_columns", "") or ""
        return {int(part) for part in str(raw).split(",") if part.strip().isdigit()}

    def _toggle_column(self, visible: bool, index: int) -> None:
        self.table.table.setColumnHidden(index, not visible)
        hidden = {i for i in range(len(COLUMNS)) if self.table.table.isColumnHidden(i)}
        self.ctx.ui_set("hidden_columns", ",".join(str(i) for i in sorted(hidden)))

    # ==================================================================
    # المظهر والحالة
    # ==================================================================
    def _toggle_theme(self) -> None:
        name = "light" if theme.current() == "dark" else "dark"
        theme.set_theme(name)
        self.ctx.ui_set("theme", name)
        self._apply_theme()

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme.stylesheet())
        self.lbl_title.setStyleSheet(theme.label_style("accent", 18, bold=True))
        self.lbl_policy.setStyleSheet(theme.label_style("muted"))
        self.lbl_user.setStyleSheet(theme.label_style("muted"))
        self._on_selection()

    def _restore_state(self) -> None:
        name = self.ctx.ui_get("theme", "dark") or "dark"
        theme.set_theme(name)
        geometry = self.ctx.ui_get("window_geometry")
        if geometry:
            try:
                self.restoreGeometry(geometry)
            except (TypeError, ValueError):
                pass
        for i in self._hidden_columns():
            self.table.table.setColumnHidden(i, True)

    def _startup_tasks(self) -> None:
        if self.policy.backup_on_start:
            path = self.ctx.backup.create_if_changed("start")
            if path:
                self.ctx.db.log(self.ctx.user(), "نسخ احتياطي", "database", path.name, "عند بدء التشغيل")
        if self.ctx.ui_get("notifications", True, bool):
            QTimer.singleShot(600, self._show_startup_alerts)

    def _show_startup_alerts(self) -> None:
        alerts = reports.collect_alerts(self.ctx.employees(), self.policy)
        notable = [a for a in alerts if a.severity in ("high", "medium")]
        if notable:
            NotificationsDialog(self, self.ctx).exec()

    # ==================================================================
    # لوحة المفاتيح والإغلاق
    # ==================================================================
    def keyPressEvent(self, event):  # noqa: N802
        if event.matches(QKeySequence.StandardKey.Find):
            self.search.setFocus()
            self.search.selectAll()
            return
        if event.matches(QKeySequence.StandardKey.Refresh):
            self._after_change()
            return
        if event.key() == Qt.Key.Key_F1:
            self._open_about()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            key = event.key()
            mapping = {
                Qt.Key.Key_N: self._add_employee,
                Qt.Key.Key_L: self._quick_leave,
                Qt.Key.Key_D: self._open_dashboard,
                Qt.Key.Key_K: self._open_calendar,
                Qt.Key.Key_E: lambda: self._export(False),
                Qt.Key.Key_R: self._open_register,
                Qt.Key.Key_B: self._open_notifications,
            }
            if key in mapping:
                mapping[key]()
                return
        super().keyPressEvent(event)

    def closeEvent(self, event):  # noqa: N802
        try:
            self.ctx.ui_set("window_geometry", self.saveGeometry())
            if self.policy.backup_on_exit:
                path = self.ctx.backup.create_if_changed("exit")
                if path:
                    self.ctx.db.log(self.ctx.user(), "نسخ احتياطي", "database", path.name,
                                    "عند الإغلاق")
        except Exception:  # pragma: no cover - لا نمنع الإغلاق بسبب النسخ
            pass
        event.accept()
