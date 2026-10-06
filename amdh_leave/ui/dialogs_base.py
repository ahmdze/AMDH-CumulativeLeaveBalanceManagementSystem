"""حوارات الأساس: القاعدة، حول، الإعدادات، سلة المحذوفات، الصيانة."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import date
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices
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
from ..i18n import tr, trf


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
                W.error(self, issue.message, tr("تعذّر الحفظ"))
                return
        warnings = [i.message for i in issues if i.level == "warning"]
        if warnings:
            W.warn(self, "\n".join(f"• {w}" for w in warnings), tr("تنبيهات"))


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
# حول النظام (نُقل إلى dialogs_about.py مع الشعارات وصورة المطوّر)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# الإعدادات
# ---------------------------------------------------------------------------
class SettingsDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, tr("الإعدادات"))
        self.resize(760, 620)
        self._policy = self.ctx.db.policy(refresh=True)
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label(tr("إعدادات النظام"), 16))
        tabs = QTabWidget()
        tabs.addTab(self._tab_general(), tr("⚙ عام"))
        tabs.addTab(self._tab_notifications(), tr("🔔 الإشعارات"))
        tabs.addTab(self._tab_backup(), tr("💾 النسخ الاحتياطي"))
        tabs.addTab(self._tab_sharing(), tr("📤 المشاركة"))
        tabs.addTab(self._tab_security(), tr("🔒 الأمان والتشفير"))
        tabs.addTab(self._tab_data(), tr("🗄 البيانات والصيانة"))
        layout.addWidget(tabs)
        layout.addLayout(self.buttons_row(self.close_button("إلغاء"), self.save_button()))

    # -- تبويب المشاركة -------------------------------------------------
    def _tab_sharing(self) -> QWidget:
        from ..services.sharing import EmailConfig, TelegramConfig
        page = QWidget()
        outer = QVBoxLayout(page)

        email = EmailConfig.from_settings(self.ctx.settings)
        box = QGroupBox(tr("البريد الإلكتروني (SMTP)"))
        form = QFormLayout(box)
        self.e_smtp_host = QLineEdit(email.host)
        self.e_smtp_host.setPlaceholderText("smtp.gmail.com")
        self.sp_smtp_port = QSpinBox()
        self.sp_smtp_port.setRange(1, 65535)
        self.sp_smtp_port.setValue(int(email.port or 587))
        self.cb_smtp_security = QComboBox()
        self.cb_smtp_security.addItem(tr("STARTTLS (587)"), "starttls")
        self.cb_smtp_security.addItem(tr("SSL/TLS (465)"), "ssl")
        self.cb_smtp_security.addItem(tr("بلا حماية"), "none")
        index = self.cb_smtp_security.findData(email.security)
        self.cb_smtp_security.setCurrentIndex(max(0, index))
        self.e_smtp_user = QLineEdit(email.username)
        self.e_smtp_password = QLineEdit(email.password)
        self.e_smtp_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_smtp_sender = QLineEdit(email.sender or email.username)
        self.e_smtp_recipients = QLineEdit(", ".join(email.recipients))
        form.addRow(tr("الخادم"), self.e_smtp_host)
        form.addRow(tr("المنفذ"), self.sp_smtp_port)
        form.addRow(tr("الحماية"), self.cb_smtp_security)
        form.addRow(tr("اسم المستخدم"), self.e_smtp_user)
        form.addRow(tr("كلمة المرور"), self.e_smtp_password)
        form.addRow(tr("بريد المُرسل"), self.e_smtp_sender)
        form.addRow(tr("المستلمون الافتراضيون"), self.e_smtp_recipients)
        outer.addWidget(box)
        outer.addWidget(W.muted_label(tr(
            "يُنصح باستخدام «كلمة مرور تطبيق» مخصّصة من مزوّد البريد، لا كلمة مرور الحساب الأساسية.")))

        telegram = TelegramConfig.from_settings(self.ctx.settings)
        tg_box = QGroupBox(tr("تلغرام (Bot API)"))
        tg_form = QFormLayout(tg_box)
        self.e_tg_token = QLineEdit(telegram.bot_token)
        self.e_tg_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_tg_token.setPlaceholderText("123456:ABC-DEF...")
        self.e_tg_chat = QLineEdit(telegram.chat_id)
        self.e_tg_chat.setPlaceholderText("123456789")
        tg_form.addRow(tr("رمز البوت"), self.e_tg_token)
        tg_form.addRow(tr("معرّف المحادثة"), self.e_tg_chat)
        outer.addWidget(tg_box)
        hint = W.muted_label(tr("لإنشاء بوت: افتح تلغرام ← @BotFather ← /newbot ← انسخ الرمز. "
                                "ولمعرفة معرّف المحادثة استخدم getUpdates."))
        hint.setWordWrap(True)
        outer.addWidget(hint)
        outer.addStretch()
        return page

    # -- تبويب الأمان والتشفير -------------------------------------------
    def _tab_security(self) -> QWidget:
        from ..services import crypto
        page = QWidget()
        outer = QVBoxLayout(page)
        summary = crypto.security_summary(self.ctx.paths.data_dir, self.ctx.paths.db_path)
        self.chk_auth_page = QCheckBox(tr("تفعيل تسجيل الدخول (أدوار وصلاحيات)"))
        self.chk_auth_page.setChecked(self._policy.auth_enabled)
        outer.addWidget(self.chk_auth_page)
        outer.addWidget(W.muted_label(tr(
            "معطَّل افتراضياً. المستخدم الافتراضي admin — غيّر كلمة المرور من «إدارة المستخدمين».")))

        box = QGroupBox(tr("تشفير قاعدة البيانات (SQLCipher)"))
        box_layout = QVBoxLayout(box)
        state = (tr("مُفعَّل") if summary["encryption_enabled"] else tr("غير مُفعَّل"))
        available = tr("مثبتة") if summary["sqlcipher_available"] else tr("غير مثبتة")
        box_layout.addWidget(QLabel(f"{tr('الحالة')}: {state} | {tr('حزمة SQLCipher')}: {available}"))
        if not summary["sqlcipher_available"]:
            hint = W.muted_label(crypto.install_hint())
            hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box_layout.addWidget(hint)
        box_layout.addLayout(W.button_row(
            W.button(tr("🔒 إدارة التشفير"), "Accent", self._open_encryption), stretch=False))
        outer.addWidget(box)
        outer.addStretch()
        return page

    def _open_encryption(self) -> None:
        from .dialogs_security import EncryptionDialog
        dialog = EncryptionDialog(self, self.ctx)
        dialog.exec()
        if dialog.changed:
            self.reject()

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
        form.addRow(tr("معدل الاستحقاق (يوم إجازة لكل ...)"), self.sp_days_per_leave)

        self.chk_enforce_cap = QCheckBox(tr("فرض سقف المعدل السنوي"))
        self.chk_enforce_cap.setChecked(self._policy.enforce_annual_cap)
        self.sp_max_annual = QSpinBox()
        self.sp_max_annual.setRange(0, 365)
        self.sp_max_annual.setValue(self._policy.max_annual)
        self.sp_max_annual.setSuffix(" يوم/سنة")
        cap_row = QHBoxLayout()
        cap_row.addWidget(self.chk_enforce_cap)
        cap_row.addWidget(self.sp_max_annual)
        cap_row.addStretch()
        form.addRow(tr("السقف السنوي"), self._wrap(cap_row))
        note = W.muted_label(tr("معطَّل افتراضياً حفاظاً على الأرقام المعتمدة حالياً (المعدل الطبيعي 36 يوماً)."))
        form.addRow("", note)

        self.cb_basis = QComboBox()
        self.cb_basis.addItem("احتساب متواصل من تاريخ المباشرة (الحالي)", config.BASIS_CONTINUOUS)
        self.cb_basis.addItem("ترصيد سنوي (سنة خدمة) مع ترحيل", config.BASIS_ANNUAL)
        self.cb_basis.setCurrentIndex(0 if self._policy.basis == config.BASIS_CONTINUOUS else 1)
        form.addRow(tr("أساس الاحتساب"), self.cb_basis)

        self.sp_expiry = QSpinBox()
        self.sp_expiry.setRange(0, 30)
        self.sp_expiry.setValue(self._policy.expiry_years)
        self.sp_expiry.setSuffix(" سنة")
        form.addRow(tr("صلاحية الرصيد غير المستخدم (0 = بلا صلاحية)"), self.sp_expiry)

        self.sp_carry_cap = QSpinBox()
        self.sp_carry_cap.setRange(0, 365)
        self.sp_carry_cap.setValue(self._policy.carryover_cap)
        self.sp_carry_cap.setSuffix(" يوم")
        form.addRow(tr("سقف الترحيل السنوي (0 = بلا سقف)"), self.sp_carry_cap)

        self.sp_low = QSpinBox()
        self.sp_low.setRange(-100, 365)
        self.sp_low.setValue(self._policy.low_balance_days)
        self.sp_low.setSuffix(" يوم")
        form.addRow(tr("حد الرصيد المنخفض للتنبيه"), self.sp_low)

        self.chk_warn_negative = QCheckBox(tr("تنبيه عند رصيد سالب"))
        self.chk_warn_negative.setChecked(self._policy.warn_negative_balance)
        warn_row = QHBoxLayout()
        warn_row.addWidget(self.chk_warn_negative)
        warn_row.addWidget(W.muted_label(tr("الرصيد السالب مشروع حسب الضوابط الإدارية — التنبيه اختياري ومعلومي.")))
        warn_row.addStretch()
        form.addRow("", self._wrap(warn_row))

        weekend_row = QHBoxLayout()
        self.weekend_boxes: list[QCheckBox] = []
        for i, name in enumerate(config.WEEKDAY_NAMES):
            box = QCheckBox(name)
            box.setChecked(i in self._policy.weekend)
            self.weekend_boxes.append(box)
            weekend_row.addWidget(box)
        form.addRow(tr("أيام العطلة الأسبوعية"), self._wrap(weekend_row))

        self.cb_first_day = QComboBox()
        for i, name in enumerate(config.WEEKDAY_NAMES):
            self.cb_first_day.addItem(name, i)
        self.cb_first_day.setCurrentIndex(self._policy.first_day_of_week)
        form.addRow(tr("أول أيام الأسبوع في التقويم"), self.cb_first_day)

        self.cb_theme = QComboBox()
        for key, label in theme.theme_choices():
            self.cb_theme.addItem(label, key)
        current_theme = self.ctx.ui_get("theme", "dark") or "dark"
        if current_theme in config.THEME_KEYS:
            current_theme = config.THEME_KEYS[current_theme]
        form.addRow(tr("وضع العرض"), self.cb_theme)
        self.cb_theme.setCurrentIndex(max(0, self.cb_theme.findData(current_theme)))

        outer.addLayout(form)
        outer.addWidget(W.separator())
        outer.addWidget(W.muted_label(tr(
            "تسجيل الدخول والصلاحيات وأمان قاعدة البيانات في تبويب «الأمان والتشفير».")))
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
        self.chk_notifications = QCheckBox(tr("عرض التنبيهات تلقائياً عند بدء التشغيل"))
        self.chk_notifications.setChecked(self.ctx.ui_get("notifications", True, bool))
        layout.addWidget(self.chk_notifications)

        self.sp_soon = QSpinBox()
        self.sp_soon.setRange(0, 90)
        self.sp_soon.setValue(self._policy.warn_leaving_soon_days)
        self.sp_soon.setSuffix(" يوم")
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("التنبيه قبل انتهاء الإجازة بـ")))
        row.addWidget(self.sp_soon)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(W.muted_label(tr("تُصنَّف التنبيهات إلى: مهم / متوسط / معلومة، ويمكن تصديرها إلى Excel أو HTML.")))
        layout.addWidget(W.separator())

        layout.addWidget(W.title_label(tr("إشعارات سطح المكتب (Tray)"), 12))
        self.chk_tray = QCheckBox(tr("تفعيل أيقونة البرنامج في شريط النظام"))
        self.chk_tray.setChecked(self.ctx.ui_get("tray_enabled", True, bool))
        self.chk_tray_popups = QCheckBox(tr("إظهار إشعارات منبثقة عند وجود تنبيهات جديدة"))
        self.chk_tray_popups.setChecked(self.ctx.ui_get("tray_notifications", True, bool))
        self.chk_close_to_tray = QCheckBox(tr("عند الإغلاق: الإخفاء إلى شريط النظام بدل إنهاء البرنامج"))
        self.chk_close_to_tray.setChecked(self.ctx.ui_get("close_to_tray", False, bool))
        for box in (self.chk_tray, self.chk_tray_popups, self.chk_close_to_tray):
            layout.addWidget(box)

        tray_row = QHBoxLayout()
        tray_row.addWidget(QLabel(tr("فترة الفحص الدوري (دقائق، 0 = بلا فحص)")))
        self.sp_tray_minutes = QSpinBox()
        self.sp_tray_minutes.setRange(0, 240)
        self.sp_tray_minutes.setValue(int(self.ctx.ui_get("tray_check_minutes", 30) or 30))
        tray_row.addWidget(self.sp_tray_minutes)
        tray_row.addStretch()
        layout.addLayout(tray_row)
        layout.addStretch()
        return page

    # -- تبويب النسخ الاحتياطي -----------------------------------------
    def _tab_backup(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.chk_backup_start = QCheckBox(tr("نسخة احتياطية عند بدء التشغيل (إن تغيّرت البيانات)"))
        self.chk_backup_start.setChecked(self._policy.backup_on_start)
        self.chk_backup_exit = QCheckBox(tr("نسخة احتياطية عند الإغلاق"))
        self.chk_backup_exit.setChecked(self._policy.backup_on_exit)
        self.chk_backup_import = QCheckBox(tr("نسخة احتياطية قبل أي استيراد"))
        self.chk_backup_import.setChecked(self._policy.backup_before_import)
        for box in (self.chk_backup_start, self.chk_backup_exit, self.chk_backup_import):
            layout.addWidget(box)

        keep_row = QHBoxLayout()
        keep_row.addWidget(QLabel(tr("عدد النسخ المحفوظة (الدوران)")))
        self.sp_keep = QSpinBox()
        self.sp_keep.setRange(1, 999)
        self.sp_keep.setValue(self._policy.backup_keep)
        keep_row.addWidget(self.sp_keep)
        keep_row.addStretch()
        layout.addLayout(keep_row)

        layout.addWidget(W.separator())
        layout.addWidget(W.muted_label(trf("مجلد النسخ: {v0}", v0=self.ctx.paths.backups_dir)))
        self.backup_table = W.TablePanel([tr("الملف"), tr("النوع"), tr("التاريخ"), tr("الحجم"), tr("صالح")])
        layout.addWidget(self.backup_table)
        row = QHBoxLayout()
        row.addWidget(W.button(tr("💾 نسخة الآن"), "Accent", self._backup_now))
        row.addWidget(W.button(tr("♻ استعادة المحددة"), "Gold", self._restore_selected))
        row.addWidget(W.button(tr("🗑 حذف المحددة"), "Warn", self._delete_backup))
        row.addWidget(W.button(tr("📂 فتح المجلد"), "Ghost",
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
        self.backup_table.set_rows(rows, empty_text=tr("لا توجد نسخ احتياطية بعد"),
                                   footer=trf("عدد النسخ: {v0}", v0=len(rows)))

    def _backup_now(self) -> None:
        path = self.ctx.backup.create("manual")
        if path:
            W.info(self, trf("تم إنشاء نسخة احتياطية:\n{v0}", v0=path.name))
        else:
            W.error(self, tr("تعذّر إنشاء النسخة الاحتياطية (راجع ملف السجل)."))
        self._refresh_backups()

    def _selected_backup_path(self) -> str | None:
        row = self.backup_table.current_row()
        if row < 0:
            W.warn(self, tr("حدد نسخة احتياطية أولاً."))
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
        if not W.confirm(self, trf("حذف النسخة {v0}؟", v0=name)):
            return
        try:
            (self.ctx.paths.backups_dir / name).unlink()
        except OSError as exc:
            W.error(self, trf("تعذّر الحذف: {v0}", v0=exc))
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
        row1.addWidget(W.button(tr("🔍 فحص سلامة القاعدة"), "Ghost", self._integrity))
        row1.addWidget(W.button(tr("🧹 ضغط القاعدة (VACUUM)"), "Ghost", self._vacuum))
        row1.addWidget(W.button(tr("📂 مجلد البيانات"), "Ghost", lambda: self._open(self.ctx.paths.data_dir)))
        row1.addWidget(W.button(tr("📂 مجلد السجلات"), "Ghost", lambda: self._open(self.ctx.paths.logs_dir)))
        row1.addWidget(W.button(tr("📄 ملف السجل"), "Ghost", self._open_log))
        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(W.button(tr("🗑 سلة المحذوفات"), "Gold", self._open_trash))
        row2.addWidget(W.button(tr("📜 سجل التدقيق"), "Ghost", self._open_audit))
        row2.addWidget(W.button(tr("👥 المستخدمون"), "Ghost", self._open_users))
        row2.addWidget(W.button(tr("📋 ضوابط الأنواع"), "Ghost", self._open_rules))
        row2.addWidget(W.button(tr("🗓 العطل الرسمية"), "Ghost", self._open_holidays))
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
            W.warn(self, tr("ملف السجل غير متاح."))

    def _integrity(self) -> None:
        ok, message = self.ctx.db.integrity_check()
        (W.info if ok else W.error)(self, f"نتيجة الفحص: {message}", "سلامة القاعدة")

    def _vacuum(self) -> None:
        before = self.ctx.paths.db_path.stat().st_size
        self.ctx.db.vacuum()
        after = self.ctx.paths.db_path.stat().st_size
        W.info(self, trf("تم الضغط.\nقبل: {v0:,.0f} KB\nبعد: {v1:,.0f} KB", v0=before / 1024, v1=after / 1024))

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
            auth_enabled=self.chk_auth_page.isChecked(),
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
        # إشعارات سطح المكتب
        self.ctx.ui_set("tray_enabled", self.chk_tray.isChecked())
        self.ctx.ui_set("tray_notifications", self.chk_tray_popups.isChecked())
        self.ctx.ui_set("close_to_tray", self.chk_close_to_tray.isChecked())
        self.ctx.ui_set("tray_check_minutes", self.sp_tray_minutes.value())
        # إعدادات المشاركة (بريد/تلغرام)
        from ..services.sharing import EmailConfig, TelegramConfig
        recipients = [item.strip() for item in
                      self.e_smtp_recipients.text().replace(";", ",").split(",") if item.strip()]
        EmailConfig(
            host=self.e_smtp_host.text().strip(),
            port=self.sp_smtp_port.value(),
            security=self.cb_smtp_security.currentData(),
            username=self.e_smtp_user.text().strip(),
            password=self.e_smtp_password.text(),
            sender=self.e_smtp_sender.text().strip(),
            recipients=recipients,
        ).save(self.ctx.settings)
        TelegramConfig(bot_token=self.e_tg_token.text().strip(),
                       chat_id=self.e_tg_chat.text().strip()).save(self.ctx.settings)
        self.ctx.db.log(self.ctx.user(), "تعديل", "settings", "", "تحديث إعدادات النظام")
        self._policy = self.ctx.db.policy(refresh=True)
        theme.set_theme(new_theme)
        if new_theme != old_theme:
            self.theme_changed.emit(new_theme)
        W.info(self, tr("تم حفظ الإعدادات."))
        self.accept()


# ---------------------------------------------------------------------------
# سلة المحذوفات
# ---------------------------------------------------------------------------
class TrashDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, tr("سلة المحذوفات"))
        self.resize(860, 560)
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label(tr("العناصر المحذوفة (قابلة للاستعادة)"), 14))
        layout.addWidget(W.muted_label(tr("الحذف في هذا النظام ناعم: لا تُمسّ البيانات إلا بالإفراغ النهائي.")))

        layout.addWidget(W.muted_label(tr("الموظفون المحذوفون")))
        self.emp_table = W.TablePanel([tr("الرقم الوظيفي"), tr("الاسم"), tr("المؤسسة"), tr("حُذف في"), tr("بواسطة")])
        layout.addWidget(self.emp_table)
        emp_row = QHBoxLayout()
        emp_row.addWidget(W.button(tr("♻ استعادة الموظف"), "Accent", self._restore_employee))
        emp_row.addStretch()
        layout.addLayout(emp_row)

        layout.addWidget(W.muted_label(tr("الإجازات المحذوفة")))
        self.leave_table = W.TablePanel(["#", tr("الموظف"), tr("النوع"), tr("من"), tr("الأيام"), tr("حُذفت في"), tr("بواسطة")])
        layout.addWidget(self.leave_table)
        row = QHBoxLayout()
        row.addWidget(W.button(tr("♻ استعادة الإجازة"), "Accent", self._restore_leave))
        row.addWidget(W.button(tr("🗑 حذف نهائي للمحدد"), "Warn", self._purge_leave))
        row.addWidget(W.button(tr("💥 إفراغ السلة نهائياً"), "Warn", self._purge_all))
        row.addStretch()
        row.addWidget(self.close_button())
        layout.addLayout(row)
        self._refresh()

    def _refresh(self) -> None:
        employees = self.ctx.db.list_employees(include_deleted=True)
        emp_rows = [[e.emp_id, e.name, e.institution, e.deleted_at, e.deleted_by] for e in employees]
        self.emp_table.set_rows(emp_rows, empty_text=tr("لا يوجد موظفون محذوفون"))

        all_leaves = self.ctx.db.all_leaves(include_deleted=True)
        names = {e.emp_id: e.name for e in self.ctx.db.list_employees(include_deleted=True, with_leaves=False)}
        deleted = [lv for lv in all_leaves if lv.is_deleted]
        rows = []
        self._deleted_leaves = deleted
        for i, lv in enumerate(deleted, 1):
            start, _end = (lv.start_date, lv.end_date)
            rows.append([i, names.get(lv.emp_id, lv.emp_id), lv.type, D.to_iso(start),
                         lv.days_actual, lv.deleted_at, lv.deleted_by])
        self.leave_table.set_rows(rows, numeric_columns={4}, empty_text=tr("لا توجد إجازات محذوفة"))

    def _restore_employee(self) -> None:
        row = self.emp_table.current_row()
        if row < 0:
            W.warn(self, tr("حدد موظفاً."))
            return
        emp_id = self.emp_table.table.item(row, 0).text()
        self.ctx.db.restore_employee(emp_id, self.ctx.user())
        W.info(self, tr("تمت الاستعادة."))
        self._refresh()

    def _restore_leave(self) -> None:
        rows = self.leave_table.selected_rows()
        if not rows:
            W.warn(self, tr("حدد إجازة."))
            return
        for row in rows:
            leave = self._deleted_leaves[row]
            if leave.id:
                self.ctx.db.restore_leave(leave.id, self.ctx.user())
        W.info(self, tr("تمت الاستعادة."))
        self._refresh()

    def _purge_leave(self) -> None:
        rows = self.leave_table.selected_rows()
        if not rows:
            W.warn(self, tr("حدد إجازة."))
            return
        if not W.confirm(self, tr("حذف نهائي لا يمكن التراجع عنه. متابعة؟")):
            return
        for row in rows:
            leave = self._deleted_leaves[row]
            if leave.id:
                self.ctx.db.purge_leave(leave.id)
        self._refresh()

    def _purge_all(self) -> None:
        if not W.confirm(self, tr("إفراغ السلة نهائياً سيحذف كل المحذوفات بلا رجعة.\nهل أنت متأكد؟")):
            return
        result = self.ctx.db.purge_all_deleted()
        W.info(self, trf("تم الحذف النهائي: {v0} موظف، {v1} إجازة.", v0=result['employees'], v1=result['leaves']))
        self._refresh()
