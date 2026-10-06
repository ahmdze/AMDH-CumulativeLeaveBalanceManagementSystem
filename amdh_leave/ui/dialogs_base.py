"""حوارات الأساس: القاعدة، حول، الإعدادات، سلة المحذوفات، الصيانة."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import date
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget,
)

from .. import config
from ..models import Issue
from ..services import dates as D
from . import theme, widgets as W


class BaseDialog(QDialog):
    """حوار أساسي: اتجاه من اليمين لليسار، ستايل موحّد، أدوات مشتركة."""

    theme_changed = pyqtSignal(str)

    def __init__(self, parent=None, ctx=None, title: str = ""):
        super().__init__(parent)
        self.ctx = ctx if ctx is not None else getattr(parent, "ctx", None)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        if title:
            self.setWindowTitle(title)
        app = QApplication.instance()
        if app is not None:
            self.setStyleSheet(app.styleSheet())

    # -- أدوات ---------------------------------------------------------
    def buttons_row(self, *items) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch()
        for item in items:
            if item is not None:
                row.addWidget(item)
        return row

    def close_button(self, text: str = "إغلاق") -> QPushButton:
        return W.button(text, "Ghost", self.reject, width=110)

    def save_button(self, text: str = "💾 حفظ", slot=None) -> QPushButton:
        return W.button(text, "Accent", slot or self._save, width=140)

    def _save(self) -> None:  # تُستبدل في الأبناء
        self.accept()

    def show_issues(self, issues: list[Issue]) -> None:
        for issue in issues:
            if issue.is_error:
                W.error(self, issue.message, "تعذّر الحفظ")
                return
        warnings = [i.message for i in issues if i.level == "warning"]
        if warnings:
            W.warn(self, "\n".join(f"• {w}" for w in warnings), "تنبيهات")


class IssuesBox(QTextEdit):
    """عرض نتائج التحقق بألوان حسب الأهمية."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFixedHeight(84)
        self.setVisible(False)

    def set_issues(self, issues: list[Issue]) -> None:
        if not issues:
            self.setVisible(False)
            self.clear()
            return
        colors = {"error": theme.color("neg"), "warning": theme.color("gold"),
                  "info": theme.color("muted")}
        icons = {"error": "⛔", "warning": "⚠️", "info": "ℹ️"}
        html = []
        for issue in issues:
            html.append(f"<div style='color:{colors.get(issue.level, theme.color('text'))}'>"
                        f"{icons.get(issue.level, '•')} {issue.message}</div>")
        self.setHtml("".join(html))
        self.setVisible(True)


# ---------------------------------------------------------------------------
# حول النظام
# ---------------------------------------------------------------------------
class AboutDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, "حول النظام")
        self.setFixedSize(470, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(8)

        icon = QLabel("📊")
        icon.setFont(QFont("Segoe UI", 44))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(theme.label_style("blue"))
        layout.addWidget(icon)

        for text, size, key in ((config.APP_NAME, 18, "blue"),
                                (f"الإصدار {config.APP_VERSION}", 11, "muted")):
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFont(QFont("Segoe UI", size, QFont.Weight.Bold))
            label.setStyleSheet(theme.label_style(key, size))
            layout.addWidget(label)

        layout.addWidget(W.separator())
        for text, size, key in (("برمجة وتطوير", 12, "accent"),
                                (config.APP_DEVELOPER, 11, "text"),
                                ("للإستفسار والدعم", 12, "accent"),
                                (f"📞 {config.APP_PHONE}", 11, "text"),
                                (f"✉️ {config.APP_EMAIL}", 11, "text")):
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFont(QFont("Segoe UI", size, QFont.Weight.Bold if size == 12 else QFont.Weight.Normal))
            label.setStyleSheet(theme.label_style(key, size))
            layout.addWidget(label)

        layout.addWidget(W.separator())
        note = W.muted_label("الرصيد السالب مسموح حسب الضوابط الإدارية المعتمدة.\n"
                             "قاعدة البيانات تعمل محلياً (SQLite) مع نسخ احتياطي تلقائي.")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(note)
        layout.addStretch()
        layout.addLayout(self.buttons_row(self.close_button()))


# ---------------------------------------------------------------------------
# الإعدادات
# ---------------------------------------------------------------------------
class SettingsDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, "الإعدادات")
        self.resize(760, 620)
        self._policy = self.ctx.db.policy(refresh=True)
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label("إعدادات النظام", 16))
        tabs = QTabWidget()
        tabs.addTab(self._tab_general(), "⚙ عام")
        tabs.addTab(self._tab_notifications(), "🔔 الإشعارات")
        tabs.addTab(self._tab_backup(), "💾 النسخ الاحتياطي")
        tabs.addTab(self._tab_data(), "🗄 البيانات والصيانة")
        layout.addWidget(tabs)
        layout.addLayout(self.buttons_row(self.close_button("إلغاء"), self.save_button()))

    # -- تبويب عام -----------------------------------------------------
    def _tab_general(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        form = QFormLayout()
        form.setSpacing(10)

        self.sp_days_per_leave = QSpinBox()
        self.sp_days_per_leave.setRange(1, 365)
        self.sp_days_per_leave.setValue(self._policy.days_per_leave)
        self.sp_days_per_leave.setSuffix(" يوم دوام")
        form.addRow("معدل الاستحقاق (يوم إجازة لكل ...)", self.sp_days_per_leave)

        self.chk_enforce_cap = QCheckBox("فرض سقف المعدل السنوي")
        self.chk_enforce_cap.setChecked(self._policy.enforce_annual_cap)
        self.sp_max_annual = QSpinBox()
        self.sp_max_annual.setRange(0, 365)
        self.sp_max_annual.setValue(self._policy.max_annual)
        self.sp_max_annual.setSuffix(" يوم/سنة")
        cap_row = QHBoxLayout()
        cap_row.addWidget(self.chk_enforce_cap)
        cap_row.addWidget(self.sp_max_annual)
        cap_row.addStretch()
        form.addRow("السقف السنوي", self._wrap(cap_row))
        note = W.muted_label("معطَّل افتراضياً حفاظاً على الأرقام المعتمدة حالياً (المعدل الطبيعي 36 يوماً).")
        form.addRow("", note)

        self.cb_basis = QComboBox()
        self.cb_basis.addItem("احتساب متواصل من تاريخ المباشرة (الحالي)", config.BASIS_CONTINUOUS)
        self.cb_basis.addItem("ترصيد سنوي (سنة خدمة) مع ترحيل", config.BASIS_ANNUAL)
        self.cb_basis.setCurrentIndex(0 if self._policy.basis == config.BASIS_CONTINUOUS else 1)
        form.addRow("أساس الاحتساب", self.cb_basis)

        self.sp_expiry = QSpinBox()
        self.sp_expiry.setRange(0, 30)
        self.sp_expiry.setValue(self._policy.expiry_years)
        self.sp_expiry.setSuffix(" سنة")
        form.addRow("صلاحية الرصيد غير المستخدم (0 = بلا صلاحية)", self.sp_expiry)

        self.sp_carry_cap = QSpinBox()
        self.sp_carry_cap.setRange(0, 365)
        self.sp_carry_cap.setValue(self._policy.carryover_cap)
        self.sp_carry_cap.setSuffix(" يوم")
        form.addRow("سقف الترحيل السنوي (0 = بلا سقف)", self.sp_carry_cap)

        self.sp_low = QSpinBox()
        self.sp_low.setRange(-100, 365)
        self.sp_low.setValue(self._policy.low_balance_days)
        self.sp_low.setSuffix(" يوم")
        form.addRow("حد الرصيد المنخفض للتنبيه", self.sp_low)

        self.chk_warn_negative = QCheckBox("تنبيه عند رصيد سالب")
        self.chk_warn_negative.setChecked(self._policy.warn_negative_balance)
        warn_row = QHBoxLayout()
        warn_row.addWidget(self.chk_warn_negative)
        warn_row.addWidget(W.muted_label("الرصيد السالب مشروع حسب الضوابط الإدارية — التنبيه اختياري ومعلومي."))
        warn_row.addStretch()
        form.addRow("", self._wrap(warn_row))

        weekend_row = QHBoxLayout()
        self.weekend_boxes: list[QCheckBox] = []
        for i, name in enumerate(config.WEEKDAY_NAMES):
            box = QCheckBox(name)
            box.setChecked(i in self._policy.weekend)
            self.weekend_boxes.append(box)
            weekend_row.addWidget(box)
        form.addRow("أيام العطلة الأسبوعية", self._wrap(weekend_row))

        self.cb_first_day = QComboBox()
        for i, name in enumerate(config.WEEKDAY_NAMES):
            self.cb_first_day.addItem(name, i)
        self.cb_first_day.setCurrentIndex(self._policy.first_day_of_week)
        form.addRow("أول أيام الأسبوع في التقويم", self.cb_first_day)

        self.cb_theme = QComboBox()
        for key in ("dark", "light"):
            self.cb_theme.addItem(config.THEME_LABELS[key], key)
        current_theme = self.ctx.ui_get("theme", "dark") or "dark"
        if current_theme in config.THEME_KEYS:
            current_theme = config.THEME_KEYS[current_theme]
        form.addRow("وضع العرض", self.cb_theme)
        self.cb_theme.setCurrentIndex(max(0, self.cb_theme.findData(current_theme)))

        outer.addLayout(form)
        outer.addWidget(W.separator())

        auth_box = QGroupBox("تسجيل الدخول والصلاحيات")
        auth_layout = QVBoxLayout(auth_box)
        self.chk_auth = QCheckBox("تفعيل تسجيل الدخول (أدوار وصلاحيات)")
        self.chk_auth.setChecked(self._policy.auth_enabled)
        auth_layout.addWidget(self.chk_auth)
        auth_layout.addWidget(W.muted_label(
            "معطَّل افتراضياً. المستخدم الافتراضي: admin وكلمة المرور: admin — "
            "غيّرها فوراً من «إدارة المستخدمين» قبل التفعيل لتجنّب فقدان الوصول."))
        outer.addWidget(auth_box)
        outer.addStretch()
        return page

    @staticmethod
    def _wrap(layout) -> QWidget:
        holder = QWidget()
        holder.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        return holder

    # -- تبويب الإشعارات ----------------------------------------------
    def _tab_notifications(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.chk_notifications = QCheckBox("عرض التنبيهات تلقائياً عند بدء التشغيل")
        self.chk_notifications.setChecked(self.ctx.ui_get("notifications", True, bool))
        layout.addWidget(self.chk_notifications)

        self.sp_soon = QSpinBox()
        self.sp_soon.setRange(0, 90)
        self.sp_soon.setValue(self._policy.warn_leaving_soon_days)
        self.sp_soon.setSuffix(" يوم")
        row = QHBoxLayout()
        row.addWidget(QLabel("التنبيه قبل انتهاء الإجازة بـ"))
        row.addWidget(self.sp_soon)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(W.muted_label("تُصنَّف التنبيهات إلى: مهم / متوسط / معلومة، ويمكن تصديرها إلى Excel أو HTML."))
        layout.addStretch()
        return page

    # -- تبويب النسخ الاحتياطي -----------------------------------------
    def _tab_backup(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.chk_backup_start = QCheckBox("نسخة احتياطية عند بدء التشغيل (إن تغيّرت البيانات)")
        self.chk_backup_start.setChecked(self._policy.backup_on_start)
        self.chk_backup_exit = QCheckBox("نسخة احتياطية عند الإغلاق")
        self.chk_backup_exit.setChecked(self._policy.backup_on_exit)
        self.chk_backup_import = QCheckBox("نسخة احتياطية قبل أي استيراد")
        self.chk_backup_import.setChecked(self._policy.backup_before_import)
        for box in (self.chk_backup_start, self.chk_backup_exit, self.chk_backup_import):
            layout.addWidget(box)

        keep_row = QHBoxLayout()
        keep_row.addWidget(QLabel("عدد النسخ المحفوظة (الدوران)"))
        self.sp_keep = QSpinBox()
        self.sp_keep.setRange(1, 999)
        self.sp_keep.setValue(self._policy.backup_keep)
        keep_row.addWidget(self.sp_keep)
        keep_row.addStretch()
        layout.addLayout(keep_row)

        layout.addWidget(W.separator())
        layout.addWidget(W.muted_label(f"مجلد النسخ: {self.ctx.paths.backups_dir}"))
        self.backup_table = W.TablePanel(["الملف", "النوع", "التاريخ", "الحجم", "صالح"])
        layout.addWidget(self.backup_table)
        row = QHBoxLayout()
        row.addWidget(W.button("💾 نسخة الآن", "Accent", self._backup_now))
        row.addWidget(W.button("♻ استعادة المحددة", "Gold", self._restore_selected))
        row.addWidget(W.button("🗑 حذف المحددة", "Warn", self._delete_backup))
        row.addWidget(W.button("📂 فتح المجلد", "Ghost",
                               lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.paths.backups_dir)))))
        row.addStretch()
        layout.addLayout(row)
        self._refresh_backups()
        return page

    def _refresh_backups(self) -> None:
        rows = []
        for item in self.ctx.backup.list_backups():
            rows.append([item["name"], item["kind"], item["mtime"],
                         f"{item['size'] / 1024:,.0f} KB", "نعم" if item["valid"] else "لا"])
        self.backup_table.set_rows(rows, empty_text="لا توجد نسخ احتياطية بعد",
                                   footer=f"عدد النسخ: {len(rows)}")

    def _backup_now(self) -> None:
        path = self.ctx.backup.create("manual")
        if path:
            W.info(self, f"تم إنشاء نسخة احتياطية:\n{path.name}")
        else:
            W.error(self, "تعذّر إنشاء النسخة الاحتياطية (راجع ملف السجل).")
        self._refresh_backups()

    def _selected_backup_path(self) -> str | None:
        row = self.backup_table.current_row()
        if row < 0:
            W.warn(self, "حدد نسخة احتياطية أولاً.")
            return None
        return self.backup_table.table.item(row, 0).text()

    def _restore_selected(self) -> None:
        name = self._selected_backup_path()
        if not name:
            return
        if not W.confirm(self, f"استعادة قاعدة البيانات من:\n{name}\n\n"
                               "سيتم أخذ نسخة أمان من الوضع الحالي قبل الاستعادة.\nهل تريد المتابعة؟"):
            return
        ok, message = self.ctx.backup.restore(self.ctx.paths.backups_dir / name)
        (W.info if ok else W.error)(self, message)
        if ok:
            self.ctx.db.invalidate_policy()
            self._policy = self.ctx.db.policy(refresh=True)
            self._refresh_backups()

    def _delete_backup(self) -> None:
        name = self._selected_backup_path()
        if not name:
            return
        if not W.confirm(self, f"حذف النسخة {name}؟"):
            return
        try:
            (self.ctx.paths.backups_dir / name).unlink()
        except OSError as exc:
            W.error(self, f"تعذّر الحذف: {exc}")
        self._refresh_backups()

    # -- تبويب البيانات ------------------------------------------------
    def _tab_data(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        stats = self.ctx.db.stats()
        grid = QGridLayout()
        items = [
            ("مسار قاعدة البيانات", stats["path"]),
            ("حجم الملف", f"{stats['size_bytes'] / 1024:,.0f} KB"),
            ("إصدار المخطط", str(stats["schema_version"])),
            ("الموظفون", f"{stats['employees']} (محذوف: {stats['employees_deleted']})"),
            ("الإجازات", f"{stats['leaves']} (محذوف: {stats['leaves_deleted']})"),
            ("المؤسسات / أماكن العمل", f"{stats['institutions']} / {stats['workplaces']}"),
            ("المرفقات", str(stats["attachments"])),
            ("سجلات التدقيق", str(stats["audit"])),
        ]
        for i, (key, value) in enumerate(items):
            grid.addWidget(W.muted_label(key), i, 0)
            label = QLabel(str(value))
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(label, i, 1)
        layout.addLayout(grid)
        layout.addWidget(W.separator())

        row1 = QHBoxLayout()
        row1.addWidget(W.button("🔍 فحص سلامة القاعدة", "Ghost", self._integrity))
        row1.addWidget(W.button("🧹 ضغط القاعدة (VACUUM)", "Ghost", self._vacuum))
        row1.addWidget(W.button("📂 مجلد البيانات", "Ghost", lambda: self._open(self.ctx.paths.data_dir)))
        row1.addWidget(W.button("📂 مجلد السجلات", "Ghost", lambda: self._open(self.ctx.paths.logs_dir)))
        row1.addWidget(W.button("📄 ملف السجل", "Ghost", self._open_log))
        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(W.button("🗑 سلة المحذوفات", "Gold", self._open_trash))
        row2.addWidget(W.button("📜 سجل التدقيق", "Ghost", self._open_audit))
        row2.addWidget(W.button("👥 المستخدمون", "Ghost", self._open_users))
        row2.addWidget(W.button("📋 ضوابط الأنواع", "Ghost", self._open_rules))
        row2.addWidget(W.button("🗓 العطل الرسمية", "Ghost", self._open_holidays))
        row2.addStretch()
        layout.addLayout(row2)
        layout.addStretch()
        return page

    def _open(self, path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_log(self) -> None:
        from ..logging_setup import log_path
        path = log_path()
        if path and path.exists():
            self._open(path)
        else:
            W.warn(self, "ملف السجل غير متاح.")

    def _integrity(self) -> None:
        ok, message = self.ctx.db.integrity_check()
        (W.info if ok else W.error)(self, f"نتيجة الفحص: {message}", "سلامة القاعدة")

    def _vacuum(self) -> None:
        before = self.ctx.paths.db_path.stat().st_size
        self.ctx.db.vacuum()
        after = self.ctx.paths.db_path.stat().st_size
        W.info(self, f"تم الضغط.\nقبل: {before / 1024:,.0f} KB\nبعد: {after / 1024:,.0f} KB")

    def _open_trash(self) -> None:
        TrashDialog(self, self.ctx).exec()

    def _open_audit(self) -> None:
        from .dialogs_admin import AuditDialog
        AuditDialog(self, self.ctx).exec()

    def _open_users(self) -> None:
        from .dialogs_admin import UsersDialog
        UsersDialog(self, self.ctx).exec()

    def _open_rules(self) -> None:
        from .dialogs_admin import RulesEditorDialog
        RulesEditorDialog(self, self.ctx).exec()

    def _open_holidays(self) -> None:
        from .dialogs_admin import HolidaysDialog
        HolidaysDialog(self, self.ctx).exec()

    # -- الحفظ ---------------------------------------------------------
    def _save(self) -> None:
        weekend = tuple(i for i, box in enumerate(self.weekend_boxes) if box.isChecked())
        policy = replace(
            self._policy,
            days_per_leave=self.sp_days_per_leave.value(),
            max_annual=self.sp_max_annual.value(),
            enforce_annual_cap=self.chk_enforce_cap.isChecked(),
            basis=self.cb_basis.currentData(),
            expiry_years=self.sp_expiry.value(),
            carryover_cap=self.sp_carry_cap.value(),
            low_balance_days=self.sp_low.value(),
            warn_negative_balance=self.chk_warn_negative.isChecked(),
            warn_leaving_soon_days=self.sp_soon.value(),
            weekend=weekend or config.DEFAULT_WEEKEND,
            first_day_of_week=self.cb_first_day.currentIndex(),
            auth_enabled=self.chk_auth.isChecked(),
            backup_on_start=self.chk_backup_start.isChecked(),
            backup_on_exit=self.chk_backup_exit.isChecked(),
            backup_before_import=self.chk_backup_import.isChecked(),
            backup_keep=self.sp_keep.value(),
        )
        self.ctx.db.save_policy(policy)
        new_theme = self.cb_theme.currentData() or "dark"
        old_theme = self.ctx.ui_get("theme", "dark")
        self.ctx.ui_set("theme", new_theme)
        self.ctx.ui_set("notifications", self.chk_notifications.isChecked())
        self.ctx.ui_set("auto_backup", self.chk_backup_exit.isChecked())
        self.ctx.db.log(self.ctx.user(), "تعديل", "settings", "", "تحديث إعدادات النظام")
        self._policy = self.ctx.db.policy(refresh=True)
        theme.set_theme(new_theme)
        if new_theme != old_theme:
            self.theme_changed.emit(new_theme)
        W.info(self, "تم حفظ الإعدادات.")
        self.accept()


# ---------------------------------------------------------------------------
# سلة المحذوفات
# ---------------------------------------------------------------------------
class TrashDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, "سلة المحذوفات")
        self.resize(860, 560)
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label("العناصر المحذوفة (قابلة للاستعادة)", 14))
        layout.addWidget(W.muted_label("الحذف في هذا النظام ناعم: لا تُمسّ البيانات إلا بالإفراغ النهائي."))

        layout.addWidget(W.muted_label("الموظفون المحذوفون"))
        self.emp_table = W.TablePanel(["الرقم الوظيفي", "الاسم", "المؤسسة", "حُذف في", "بواسطة"])
        layout.addWidget(self.emp_table)
        emp_row = QHBoxLayout()
        emp_row.addWidget(W.button("♻ استعادة الموظف", "Accent", self._restore_employee))
        emp_row.addStretch()
        layout.addLayout(emp_row)

        layout.addWidget(W.muted_label("الإجازات المحذوفة"))
        self.leave_table = W.TablePanel(["#", "الموظف", "النوع", "من", "الأيام", "حُذفت في", "بواسطة"])
        layout.addWidget(self.leave_table)
        row = QHBoxLayout()
        row.addWidget(W.button("♻ استعادة الإجازة", "Accent", self._restore_leave))
        row.addWidget(W.button("🗑 حذف نهائي للمحدد", "Warn", self._purge_leave))
        row.addWidget(W.button("💥 إفراغ السلة نهائياً", "Warn", self._purge_all))
        row.addStretch()
        row.addWidget(self.close_button())
        layout.addLayout(row)
        self._refresh()

    def _refresh(self) -> None:
        employees = self.ctx.db.list_employees(include_deleted=True)
        emp_rows = [[e.emp_id, e.name, e.institution, e.deleted_at, e.deleted_by] for e in employees]
        self.emp_table.set_rows(emp_rows, empty_text="لا يوجد موظفون محذوفون")

        all_leaves = self.ctx.db.all_leaves(include_deleted=True)
        names = {e.emp_id: e.name for e in self.ctx.db.list_employees(include_deleted=True, with_leaves=False)}
        deleted = [lv for lv in all_leaves if lv.is_deleted]
        rows = []
        self._deleted_leaves = deleted
        for i, lv in enumerate(deleted, 1):
            start, _end = (lv.start_date, lv.end_date)
            rows.append([i, names.get(lv.emp_id, lv.emp_id), lv.type, D.to_iso(start),
                         lv.days_actual, lv.deleted_at, lv.deleted_by])
        self.leave_table.set_rows(rows, numeric_columns={4}, empty_text="لا توجد إجازات محذوفة")

    def _restore_employee(self) -> None:
        row = self.emp_table.current_row()
        if row < 0:
            W.warn(self, "حدد موظفاً.")
            return
        emp_id = self.emp_table.table.item(row, 0).text()
        self.ctx.db.restore_employee(emp_id, self.ctx.user())
        W.info(self, "تمت الاستعادة.")
        self._refresh()

    def _restore_leave(self) -> None:
        rows = self.leave_table.selected_rows()
        if not rows:
            W.warn(self, "حدد إجازة.")
            return
        for row in rows:
            leave = self._deleted_leaves[row]
            if leave.id:
                self.ctx.db.restore_leave(leave.id, self.ctx.user())
        W.info(self, "تمت الاستعادة.")
        self._refresh()

    def _purge_leave(self) -> None:
        rows = self.leave_table.selected_rows()
        if not rows:
            W.warn(self, "حدد إجازة.")
            return
        if not W.confirm(self, "حذف نهائي لا يمكن التراجع عنه. متابعة؟"):
            return
        for row in rows:
            leave = self._deleted_leaves[row]
            if leave.id:
                self.ctx.db.purge_leave(leave.id)
        self._refresh()

    def _purge_all(self) -> None:
        if not W.confirm(self, "إفراغ السلة نهائياً سيحذف كل المحذوفات بلا رجعة.\nهل أنت متأكد؟"):
            return
        result = self.ctx.db.purge_all_deleted()
        W.info(self, f"تم الحذف النهائي: {result['employees']} موظف، {result['leaves']} إجازة.")
        self._refresh()
