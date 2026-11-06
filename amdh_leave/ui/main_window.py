"""النافذة الرئيسية: الجدول، الفلاتر، التفاصيل، الشريط الجانبي، قفل الخمول، والاختصارات."""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QFont, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..exporters import excel as X
from ..exporters import html as H
from ..exporters import pdf as P
from ..logging_setup import get_logger
from ..services import balance as B
from ..services import dates as D
from ..services import reports
from . import assets, theme
from . import widgets as W
from .calendar_view import CalendarDialog
from .dashboard import DashboardDialog
from .dialogs_about import AboutDialog
from .dialogs_admin import AuditDialog, HolidaysDialog, RulesEditorDialog, UsersDialog
from .dialogs_base import SettingsDialog, TrashDialog
from .dialogs_db import DatabaseOperationsDialog
from .dialogs_employee import EmployeeDialog
from .dialogs_export import export_for_center as export_transfer_file
from .dialogs_import import ImportHistoryDialog, TransferImportDialog
from .dialogs_institutions import InstitutionsDialog
from .dialogs_leave import AttachmentsDialog, LeaveDialog, SettlementDialog, StatementDialog
from .notifications import NotificationsDialog
from .register import LeavesRegisterDialog

COLUMNS = [
    ("الرقم الوظيفي", 120),
    ("الاسم", 200),
    ("العنوان الوظيفي", 150),
    ("مكان العمل", 140),
    ("المؤسسة", 160),
    ("الجنس", 60),
    ("المباشرة", 100),
    ("انتهاء الخدمة", 100),
    ("أيام الخدمة", 90),
    ("خارج الرصيد", 90),
    ("الدوام المحسوبة", 110),
    ("المستحقة", 85),
    ("المأخوذة", 85),
    ("الرصيد", 85),
]
NUMERIC_COLUMNS = {8, 9, 10, 11, 12, 13}
DETAIL_ITEMS = [
    ("name", "الاسم"),
    ("job_title", "العنوان الوظيفي"),
    ("workplace", "مكان العمل"),
    ("institution", "المؤسسة"),
    ("gender", "الجنس"),
    ("start_date", "تاريخ المباشرة"),
    ("end_date", "انتهاء الخدمة"),
    ("raw_days", "أيام الخدمة"),
    ("outside", "خارج الرصيد"),
    ("net_days", "الدوام المحسوبة"),
    ("earned", "المستحقة"),
    ("taken", "المأخوذة"),
    ("balance", "الرصيد"),
    ("promotion_delay", "تأخير العلاوة"),
]


class _IdleActivityFilter(QObject):
    """مراقب أحداث على مستوى التطبيق لإعادة ضبط مؤقت الخمول عند أي حركة ماوس أو ضغطة مفتاح."""

    def __init__(self, on_activity, parent=None):
        super().__init__(parent)
        self._on_activity = on_activity

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() in (
            QEvent.Type.KeyPress,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
            QEvent.Type.Wheel,
        ):
            self._on_activity()
        return super().eventFilter(obj, event)


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.policy = ctx.db.policy(refresh=True)
        self.rows: list[dict] = []
        self._session_locking = False
        self.setWindowTitle(f"{config.APP_NAME} — الإصدار {config.APP_VERSION}")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(1360, 820)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._refresh)
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._lock_session_on_idle)
        self._idle_filter = _IdleActivityFilter(self._reset_idle_timer, self)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._idle_filter)
        self._build()
        self._restore_state()
        self._load_filters()
        self._refresh()
        self._configure_idle_timer()
        self._startup_tasks()

    # ==================================================================
    # مؤقت الخمول وقفل الجلسة التلقائي
    # ==================================================================
    def _configure_idle_timer(self) -> None:
        minutes = int(getattr(self.policy, "session_timeout_minutes", 0) or 0)
        if minutes > 0 and self.policy.auth_enabled:
            self._idle_timer.setInterval(minutes * 60 * 1000)
            self._idle_timer.start()
        else:
            self._idle_timer.stop()

    def _reset_idle_timer(self) -> None:
        if self._idle_timer.isActive() and not self._session_locking:
            self._idle_timer.start()

    def _lock_session_on_idle(self) -> None:
        if self._session_locking or not self.policy.auth_enabled:
            return
        self._session_locking = True
        try:
            from ..services.security import make_session
            from .dialogs_login import LoginDialog

            self.hide()
            dlg = LoginDialog(None, self.ctx)
            dlg.setWindowTitle("قُفلت الجلسة بسبب الخمول — أعد تسجيل الدخول")
            if dlg.exec() == dlg.DialogCode.Accepted and dlg.user is not None:
                self.ctx.session = make_session(dlg.user, True)
                self.lbl_user.setText(self._user_text())
                self.show()
                self._after_change()
                self._configure_idle_timer()
            else:
                self._force_quit = True
                self.close()
        finally:
            self._session_locking = False

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
        header.setObjectName("Header")
        header.setFixedHeight(60)
        layout = QHBoxLayout(header)
        layout.setSpacing(10)

        self.lbl_logo = QLabel()
        self.lbl_logo.setFixedSize(42, 42)
        self.lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo = assets.logo(42)
        if logo is not None:
            self.lbl_logo.setPixmap(logo)
        self.lbl_logo.setToolTip(config.APP_NAME)
        layout.addWidget(self.lbl_logo)

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
        layout.addWidget(
            W.button(
                "🎨 الثيم", "Ghost", self._choose_theme, width=110, tooltip="اختيار ثيم الواجهة (5 ثيمات)"
            )
        )
        return header

    def _user_text(self) -> str:
        session = self.ctx.session
        scope = session.scoped_institution or "كل المؤسسات"
        role = config.ROLE_LABELS.get(session.role, session.role)
        return f"المستخدم: {session.display_name} ({role}) — {scope}"

    # -- الشريط الجانبي --------------------------------------------------
    def _sidebar(self) -> QScrollArea:
        area = QScrollArea()
        area.setMinimumWidth(200)
        area.setMaximumWidth(280)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setStyleSheet("QScrollArea { background: transparent; }")
        holder = QWidget()
        holder.setObjectName("Sidebar")
        area.setWidget(holder)
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(3)

        section_added: list[bool] = [False]

        def add_section(title: str, is_first: bool = False):
            section_buttons: list[tuple[str, str, callable, str | None, str]] = []

            def make_label():
                lbl = QLabel(title)
                text_color = theme.color("text")
                lbl.setStyleSheet(f"""
                    font-size: 15px;
                    font-weight: bold;
                    font-family: "Arial";
                    color: {text_color};
                    margin-top: 8px;
                    margin-bottom: 4px;
                """)
                return lbl

            section_label = make_label()

            def collect_button(
                text: str, style: str, slot, permission: str | None = None, tooltip: str = ""
            ) -> None:
                if permission and not self.ctx.can(permission):
                    return
                section_buttons.append((text, style, slot, permission, tooltip))

            return collect_button, section_label, section_buttons, is_first

        # 1. قسم إدارة الموظفين
        collect, label, buttons, is_first = add_section("إدارة الموظفين", is_first=True)
        collect(
            "إضافة موظف جديد  ➕",
            "Accent",
            self._add_employee,
            "edit_employee",
            tooltip="إضافة موظف جديد إلى قاعدة البيانات",
        )
        collect(
            "تعديل الموظف  ✏",
            "Ghost",
            self._edit_employee,
            "edit_employee",
            tooltip="تعديل بيانات الموظف المحدد",
        )
        collect("بطاقة الموظف  🪪", "Ghost", self._open_employee_card, tooltip="عرض بطاقة الموظف الشخصية")
        collect("كشف حساب الموظف  🧾", "Ghost", self._open_statement, tooltip="عرض كشف حساب الإجازات للموظف")
        collect(
            "تصفية نهاية الخدمة  📤",
            "Ghost",
            self._open_settlement,
            tooltip="تصفية حساب الموظف عند نهاية الخدمة",
        )
        collect(
            "حذف الموظف  🗑",
            "Warn",
            self._delete_employee,
            "delete_employee",
            tooltip="حذف الموظف من قاعدة البيانات",
        )
        if buttons:
            if not is_first and section_added[0]:
                layout.addWidget(W.separator())
            layout.addWidget(label)
            for text, style, slot, _permission, tooltip in buttons:
                if style == "Ghost":
                    btn = W.nav_button(text, slot, tooltip=tooltip)
                else:
                    btn = W.button(text, style, slot, tooltip=tooltip)
                    btn.setMinimumHeight(34)
                layout.addWidget(btn)
            section_added[0] = True

        # 2. قسم الإجازات والدوام
        collect, label, buttons, is_first = add_section("الإجازات والدوام")
        collect(
            "تسجيل إجازة  📝", "Blue", self._quick_leave, "edit_leave", tooltip="تسجيل إجازة جديدة للموظف"
        )
        collect("سجل الإجازات  📅", "Ghost", self._open_register, tooltip="عرض سجل جميع الإجازات")
        collect("تقويم الإجازات  🗓", "Ghost", self._open_calendar, tooltip="عرض الإجازات على التقويم الشهري")
        collect(
            "مرفقات الإجازة  📎",
            "Ghost",
            self._open_attachments,
            "manage_attachments",
            tooltip="إدارة مرفقات الإجازات",
        )
        if buttons:
            if section_added[0]:
                layout.addWidget(W.separator())
            layout.addWidget(label)
            for text, style, slot, _permission, tooltip in buttons:
                if style == "Ghost":
                    btn = W.nav_button(text, slot, tooltip=tooltip)
                else:
                    btn = W.button(text, style, slot, tooltip=tooltip)
                    btn.setMinimumHeight(34)
                layout.addWidget(btn)
            section_added[0] = True

        # 3. قسم التقارير والبيانات
        collect, label, buttons, is_first = add_section("التقارير والبيانات")
        collect("لوحة المؤشرات  📊", "Gold", self._open_dashboard, tooltip="عرض لوحة المؤشرات والإحصائيات")
        collect("تقرير إجمالي  📄", "Ghost", self._global_report, tooltip="توليد تقرير إجمالي لجميع الموظفين")
        collect(
            "تقرير مخصص  📑", "Ghost", self._open_custom_report, tooltip="توليد تقرير مخصص حسب معايير محددة"
        )
        collect(
            "استيراد موظفين Excel  📥",
            "Ghost",
            self._import_employee_data,
            "edit_employee",
            tooltip="استيراد بيانات الموظفين من ملف Excel",
        )
        collect(
            "تصدير الموظفين Excel  📤",
            "Ghost",
            self._export_employee_data,
            tooltip="تصدير بيانات الموظفين إلى ملف Excel",
        )
        if buttons:
            if section_added[0]:
                layout.addWidget(W.separator())
            layout.addWidget(label)
            for text, style, slot, _permission, tooltip in buttons:
                if style == "Ghost":
                    btn = W.nav_button(text, slot, tooltip=tooltip)
                else:
                    btn = W.button(text, style, slot, tooltip=tooltip)
                    btn.setMinimumHeight(34)
                layout.addWidget(btn)
            section_added[0] = True

        # 4. قسم المؤسسات والتنقلات
        collect, label, buttons, is_first = add_section("المؤسسات والتنقلات")
        collect(
            "المؤسسات  🏥",
            "Ghost",
            self._open_institutions,
            "manage_institutions",
            tooltip="إدارة قائمة المؤسسات",
        )
        collect(
            "استيراد من مؤسسة  📥",
            "Blue",
            self._import_transfer,
            "import_transfer",
            tooltip="استيراد بيانات من مؤسسة أخرى",
        )
        collect(
            "تصدير للمركز  📤",
            "Blue",
            self._export_transfer,
            "export_transfer",
            tooltip="تصدير بيانات للمركز الرئيسي أو إرسالها عبر الشبكة",
        )
        collect(
            "سجل الاستيراد  📋",
            "Ghost",
            self._open_import_history,
            "manage_institutions",
            tooltip="عرض سجل عمليات الاستيراد",
        )
        if buttons:
            if section_added[0]:
                layout.addWidget(W.separator())
            layout.addWidget(label)
            for text, style, slot, _permission, tooltip in buttons:
                if style == "Ghost":
                    btn = W.nav_button(text, slot, tooltip=tooltip)
                else:
                    btn = W.button(text, style, slot, tooltip=tooltip)
                    btn.setMinimumHeight(34)
                layout.addWidget(btn)
            section_added[0] = True

        # 5. قسم إدارة النظام
        collect, label, buttons, is_first = add_section("إدارة النظام")
        collect(
            "ضوابط الإجازات  📋",
            "Ghost",
            self._open_rules,
            "edit_rules",
            tooltip="تعديل ضوابط وسياسات الإجازات",
        )
        collect(
            "العطل الرسمية  🗓",
            "Ghost",
            self._open_holidays,
            "view_holidays",
            tooltip="عرض وإدارة العطل الرسمية",
        )
        collect("المستخدمون  👥", "Ghost", self._open_users, "manage_users", tooltip="إدارة مستخدمين النظام")
        collect("سجل التدقيق  📜", "Ghost", self._open_audit, "view_audit", tooltip="عرض سجل تدقيق العمليات")
        collect("التنبيهات  🔔", "Ghost", self._open_notifications, tooltip="عرض التنبيهات والإشعارات")
        if buttons:
            if section_added[0]:
                layout.addWidget(W.separator())
            layout.addWidget(label)
            for text, style, slot, _permission, tooltip in buttons:
                if style == "Ghost":
                    btn = W.nav_button(text, slot, tooltip=tooltip)
                else:
                    btn = W.button(text, style, slot, tooltip=tooltip)
                    btn.setMinimumHeight(34)
                layout.addWidget(btn)
            section_added[0] = True

        # 6. قسم الأمان والصيانة
        collect, label, buttons, is_first = add_section("الأمان والصيانة")
        collect(
            "تشفير قاعدة البيانات  🔒",
            "Ghost",
            self._open_encryption,
            "manage_encryption",
            tooltip="تشفير وفك تشفير قاعدة البيانات",
        )
        collect(
            "خزنة كلمات المرور  🔐",
            "Ghost",
            self._open_vault,
            "manage_encryption",
            tooltip="إدارة خزنة كلمات المرور",
        )
        collect(
            "عمليات قاعدة البيانات  🗄️",
            "Ghost",
            self._open_db_ops,
            "db_operations",
            tooltip="عمليات الصيانة على قاعدة البيانات",
        )
        collect(
            "سلة المحذوفات  🗑", "Warn", self._open_trash, "purge", tooltip="عرض واستعادة العناصر المحذوفة"
        )
        if buttons:
            if section_added[0]:
                layout.addWidget(W.separator())
            layout.addWidget(label)
            for text, style, slot, _permission, tooltip in buttons:
                if style == "Ghost":
                    btn = W.nav_button(text, slot, tooltip=tooltip)
                else:
                    btn = W.button(text, style, slot, tooltip=tooltip)
                    btn.setMinimumHeight(34)
                layout.addWidget(btn)
            section_added[0] = True

        # 7. الإعدادات
        collect, label, buttons, is_first = add_section("عام")
        collect("الإعدادات  ⚙", "Ghost", self._open_settings, tooltip="إعدادات النظام والتفضيلات")
        collect("حول  ℹ", "Gold", self._open_about, tooltip="معلومات عن التطبيق والإصدار")
        if buttons:
            if section_added[0]:
                layout.addWidget(W.separator())
            layout.addWidget(label)
            for text, style, slot, _permission, tooltip in buttons:
                if style == "Ghost":
                    btn = W.nav_button(text, slot, tooltip=tooltip)
                else:
                    btn = W.button(text, style, slot, tooltip=tooltip)
                    btn.setMinimumHeight(34)
                layout.addWidget(btn)
            section_added[0] = True

        layout.addWidget(W.separator())
        btn_exit = W.button("خروج  🚪", "Warn", self.close, tooltip="خروج من التطبيق")
        btn_exit.setMinimumHeight(34)
        layout.addWidget(btn_exit)

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
        filters.addWidget(W.button("🔍 بحث متقدم", "Blue", self._open_advanced_search))
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

        details = W.card(hoverable=True)
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
        for combo, values in (
            (self.cb_workplace, self.ctx.workplaces()),
            (self.cb_institution, self.ctx.institutions()),
        ):
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
        return (
            self.search.text().strip(),
            "" if workplace == "الكل" else workplace,
            "" if institution == "الكل" else institution,
        )

    def _refresh(self) -> None:
        self.policy = self.ctx.db.policy(refresh=True)
        q, workplace, institution = self._filters()
        employees = self.ctx.employees(q, workplace, institution)
        rows, colors = [], {}
        totals = {"raw": 0, "outside": 0, "net": 0, "earned": 0, "taken": 0, "balance": 0, "negative": 0}
        for r, emp in enumerate(employees):
            balance = B.compute_balance(emp, emp.leaves, self.policy)
            inst_label = emp.institution
            if emp.secondment_to:
                inst_label = f"{emp.institution} (منسّب: {emp.secondment_to})"
            rows.append(
                [
                    emp.emp_id,
                    emp.name,
                    emp.job_title,
                    emp.workplace,
                    inst_label,
                    emp.gender,
                    D.to_iso(emp.start_date),
                    D.to_iso(emp.end_date),
                    balance.raw_days,
                    balance.outside,
                    balance.net_days,
                    balance.earned,
                    balance.taken,
                    balance.balance,
                ]
            )
            colors[(r, 13)] = theme.balance_color(balance.balance, self.policy.low_balance_days)
            totals["raw"] += balance.raw_days
            totals["outside"] += balance.outside
            totals["net"] += balance.net_days
            totals["earned"] += balance.earned
            totals["taken"] += balance.taken
            totals["balance"] += balance.balance
            totals["negative"] += 1 if balance.balance < 0 else 0
        self.rows = rows
        footer = (
            f"عدد الموظفين المعروضين: {len(rows)} | إجمالي المستحقة: {totals['earned']} يوم | "
            f"المأخوذة: {totals['taken']} يوم | إجمالي الرصيد: {totals['balance']} يوم | "
            f"أرصدة سالبة: {totals['negative']} (مسموح حسب الضوابط)"
        )
        self.table.set_rows(
            rows,
            numeric_columns=NUMERIC_COLUMNS,
            colors=colors,
            empty_text="لا يوجد موظفون مطابقون للبحث أو الفلاتر",
            footer=footer,
        )
        if hasattr(self, "lbl_status"):
            self.lbl_status.setText(f"الموظفون: {len(rows)} — آخر تحديث: {date.today().strftime('%Y-%m-%d')}")
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
        promo = B.promotion_impact(employee, employee.leaves, self.policy)
        for key, widget in self.detail_widgets.items():
            if key == "promotion_delay":
                widget.set_value(
                    promo.total_excluded_days,
                    "gold" if promo.has_delay else "pos",
                    " يوم",
                )
            elif key in ("raw_days", "outside", "net_days", "earned", "taken", "balance"):
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
        if not W.confirm(
            self, f"حذف الموظف «{employee.name}» مع إجازاته؟\nالحذف ناعم ويمكن الاستعادة من سلة المحذوفات."
        ):
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

    def _export_employee_data(self) -> None:
        """تصدير بيانات الموظفين كاملة (الحقول القابلة للإدخال) إلى Excel."""
        q, workplace, institution = self._filters()
        employees = self.ctx.employees(q, workplace, institution)
        if not employees:
            W.warn(self, "لا توجد بيانات للتصدير.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "تصدير الموظفين", f"الموظفون_{D.date.today()}.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            X.export_employee_master(path, employees)
        except Exception as exc:  # noqa: BLE001
            W.error(self, f"فشل التصدير: {exc}")
            return
        W.info(self, f"تم التصدير:\n{path}")
        if W.confirm(self, "هل تريد فتح الملف الآن؟"):
            W.open_path(self, path)

    def _import_employee_data(self) -> None:
        if not self.ctx.can("edit_employee"):
            W.error(self, "لا تملك صلاحية استيراد الموظفين.")
            return
        from .dialogs_db import ImportWizardDialog

        ImportWizardDialog(self, self.ctx, refresh_callback=self._after_change).exec()

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
            label = f"{leave.type} — {D.to_iso(leave.start_date)} ({leave.days_actual} يوم)"
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

    def _open_encryption(self) -> None:
        """إدارة تشفير قاعدة البيانات."""
        from .dialogs_security import EncryptionDialog

        dialog = EncryptionDialog(self, self.ctx)
        dialog.exec()

    def _open_vault(self) -> None:
        from .dialogs_vault import VaultDialog

        VaultDialog(self, self.ctx).exec()

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

    # -- المؤسسات وملفات النقل -----------------------------------------
    def _open_institutions(self) -> None:
        InstitutionsDialog(self, self.ctx).exec()
        self._after_change()

    def _import_transfer(self) -> None:
        dialog = TransferImportDialog(self, self.ctx)
        dialog.exec()
        self._after_change()

    def _export_transfer(self) -> None:
        export_transfer_file(self, self.ctx)

    def _open_import_history(self) -> None:
        ImportHistoryDialog(self, self.ctx).exec()

    def _transfer_employee(self) -> None:
        """نقل الموظف المحدد إلى مؤسسة أخرى مع تسجيل الانتقال في سجله."""
        emp_id = self._current_id()
        if not emp_id:
            return
        if not self.ctx.can("transfer_employee"):
            W.error(self, "لا تملك صلاحية نقل الموظفين بين المؤسسات.")
            return
        employee = self.ctx.db.get_employee(emp_id)
        if employee is None:
            return
        names = [
            item.name
            for item in self.ctx.db.list_institutions(active_only=True)
            if item.name != employee.institution
        ]
        if not names:
            W.warn(self, "لا توجد مؤسسة أخرى مسجّلة. أضف المؤسسات من نافذة «المؤسسات».")
            return
        from PyQt6.QtWidgets import QInputDialog

        choice, ok = QInputDialog.getItem(
            self, "نقل موظف", f"نقل «{employee.name}» من «{employee.institution}» إلى:", names, 0, False
        )
        if not ok or not choice:
            return
        from ..services import dates as DD

        moved_on = DD.date.today()
        if not W.confirm(
            self,
            f"نقل الموظف {employee.name} ({emp_id}) إلى «{choice}»؟\n\n"
            "سيبقى رصيده وإجازاته كما هي، ويُسجَّل الانتقال في سجل الموظف.",
            "تأكيد النقل",
        ):
            return
        self.ctx.db.add_move(
            emp_id,
            employee.institution,
            choice,
            moved_on=moved_on,
            source_file="—",
            note="نقل يدوي من الشاشة الرئيسية",
            user=self.ctx.user(),
        )
        self.ctx.db.set_employee_institution(emp_id, choice, moved_on=moved_on, user=self.ctx.user())
        W.info(self, f"تم نقل الموظف إلى «{choice}» بتاريخ {moved_on}.")
        self._after_change()

    def _open_trash(self) -> None:
        TrashDialog(self, self.ctx).exec()
        self._after_change()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self, self.ctx)
        dialog.theme_changed.connect(self._on_settings_saved)
        dialog.exec()
        self.policy = self.ctx.db.policy(refresh=True)
        self._configure_idle_timer()

    def _on_settings_saved(self, _old_theme: str) -> None:
        self.policy = self.ctx.db.policy(refresh=True)
        self.lbl_policy.setText(self.policy.annual_rate_note)
        self._apply_theme()
        self._configure_idle_timer()
        self._after_change()

    def _open_advanced_search(self) -> None:
        from .dialogs_advanced_search import AdvancedSearchDialog

        AdvancedSearchDialog(self, self.ctx).exec()

    def _open_about(self) -> None:
        AboutDialog(self, self.ctx).exec()

    def _open_employee_card(self) -> None:
        """فتح بطاقة الموظف المحدد."""
        row = self.table.current_row()
        if row < 0:
            W.warn(self, "حدد موظفاً أولاً.")
            return
        emp_id = self.table.table.item(row, 0).text()
        employee = self.ctx.db.get_employee(emp_id)
        if employee is None:
            W.error(self, "الموظف غير موجود.")
            return
        from .dialogs_employee_card import EmployeeCardDialog

        EmployeeCardDialog(employee, self.policy, self, self.ctx).exec()

    def _open_custom_report(self) -> None:
        """فتح نافذة التقرير المخصص."""
        from .dialogs_custom_report import CustomReportDialog

        CustomReportDialog(self, self.ctx).exec()

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
        path, _ = QFileDialog.getSaveFileName(
            self, f"تصدير {label}", f"employees_{date.today()}.xlsx", "Excel (*.xlsx)"
        )
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
        content = H.global_report_html(
            rows, self.policy, "تقرير الإجازات التراكمية", self.ctx.session.scoped_institution
        )
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
            ("🖨 طباعة التفاصيل", self._print_employee, ""),
            ("📄 تصدير PDF", self._export_pdf_employee, ""),
            ("✏ تعديل الموظف / التنسيب", self._edit_employee, "edit_employee"),
            ("📅 سجل الإجازات", self._open_register, ""),
            ("📝 تسجيل إجازة", self._quick_leave, "edit_leave"),
            ("🧾 كشف حساب الرصيد", self._open_statement, ""),
            ("📤 تصفية نهاية الخدمة", self._open_settlement, ""),
            ("📎 مرفقات الإجازة", self._open_attachments, "manage_attachments"),
            ("🔀 نقل الموظف إلى مؤسسة", self._transfer_employee, "transfer_employee"),
            ("🗑 حذف الموظف", self._delete_employee, "delete_employee"),
        ]
        for text, slot, permission in actions:
            if permission and not self.ctx.can(permission):
                continue
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
    def theme_actions(self) -> list[QAction]:
        """إجراءات قائمة الثيمات مع معاينة لونية لكل ثيم."""
        current = theme.current()
        actions = []
        for key, label in theme.theme_choices():
            action = QAction(theme.swatch_icon(key), label, self)
            action.setCheckable(True)
            action.setChecked(key == current)
            action.setData(key)
            action.triggered.connect(lambda _c=False, name=key: self.set_theme(name))
            actions.append(action)
        return actions

    def accent_actions(self) -> list[QAction]:
        """إجراءات اللون المميز: تخصيص لون أو العودة إلى لون الثيم."""
        actions = []
        pick = QAction(theme.accent_preview_icon(), "تخصيص اللون المميز...", self)
        pick.setData("pick")
        pick.triggered.connect(self._pick_accent)
        actions.append(pick)
        reset = QAction("إعادة لون الثيم الافتراضي", self)
        reset.setData("reset")
        reset.setEnabled(bool(theme.accent_override()))
        reset.triggered.connect(lambda: self.set_accent(None))
        actions.append(reset)
        return actions

    def _pick_accent(self) -> None:
        from PyQt6.QtWidgets import QColorDialog

        chosen = QColorDialog.getColor(QColor(theme.color("accent")), self, "اختر اللون المميز")
        if chosen.isValid():
            self.set_accent(chosen.name())

    def set_accent(self, accent: str | None) -> None:
        """يضبط اللون المميز المخصّص (يُشتق منه كل حالات التفاعل)."""
        theme.set_accent(accent)
        self.ctx.ui_set("accent", accent or "")
        self._apply_theme()

    def _choose_theme(self) -> None:
        """قائمة الثيمات الخمسة + تخصيص اللون المميز."""
        menu = QMenu(self)
        menu.setLayoutDirection(self.layoutDirection())
        for action in self.theme_actions():
            menu.addAction(action)
        menu.addSeparator()
        for action in self.accent_actions():
            menu.addAction(action)
        menu.exec(self.cursor().pos())

    def set_theme(self, name: str) -> None:
        theme.set_theme(name)
        self.ctx.ui_set("theme", theme.current())
        self._apply_theme()

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme.stylesheet())
        self.lbl_title.setStyleSheet(theme.label_style("accent", 18, bold=True))
        self.lbl_policy.setStyleSheet(theme.label_style("muted"))
        self.lbl_user.setStyleSheet(theme.label_style("muted"))
        self._on_selection()
        for widget in self.findChildren(W.KPICard):
            widget.value.setStyleSheet(theme.label_style(theme.color("accent"), 18, bold=True))

    def _restore_state(self) -> None:
        name = self.ctx.ui_get("theme", "dark") or "dark"
        theme.set_theme(name)
        stored_accent = str(self.ctx.ui_get("accent", "") or "")
        theme.set_accent(stored_accent or None)
        theme.apply(QApplication.instance())
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
        # أيقونة الصندوق (Tray)
        try:
            from .tray import TrayController

            self.tray = TrayController(self, self.ctx)
            if self.tray.start():
                QTimer.singleShot(900, lambda: self.tray.refresh_alerts(notify=True))
        except Exception as exc:  # pragma: no cover
            get_logger("tray").warning("تعذّر تشغيل أيقونة الصندوق: %s", exc)
            self.tray = None
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
        tray = getattr(self, "tray", None)
        if (
            tray is not None
            and tray.tray is not None
            and not getattr(self, "_force_quit", False)
            and bool(self.ctx.ui_get("close_to_tray", False, bool))
        ):
            self.ctx.ui_set("window_geometry", self.saveGeometry())
            self.hide()
            tray.notify("البرنامج ما زال يعمل", "أُخفي البرنامج إلى شريط النظام. اضغط على الأيقونة لإظهاره.")
            event.ignore()
            return
        try:
            self._idle_timer.stop()
            app = QApplication.instance()
            if app is not None and hasattr(self, "_idle_filter"):
                app.removeEventFilter(self._idle_filter)
            self.ctx.ui_set("window_geometry", self.saveGeometry())
            if self.policy.backup_on_exit:
                path = self.ctx.backup.create_if_changed("exit")
                if path:
                    self.ctx.db.log(self.ctx.user(), "نسخ احتياطي", "database", path.name, "عند الإغلاق")
        except Exception:  # pragma: no cover
            pass
        tray = getattr(self, "tray", None)
        if tray is not None:
            tray.shutdown()
        event.accept()
