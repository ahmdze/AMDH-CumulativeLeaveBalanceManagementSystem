"""حوارات الأمان: كلمة المرور وإدارة تشفير قاعدة البيانات (SQLCipher)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QVBoxLayout, QWidget,
)

from ..i18n import tr, trf
from ..services import crypto
from ..services import security as sec
from . import theme, widgets as W
from .dialogs_base import BaseDialog


class PasswordDialog(BaseDialog):
    """طلب كلمة مرور (مع تأكيد اختياري). لا يحتاج سياق التطبيق."""

    def __init__(self, parent=None, title: str = "", message: str = "",
                 confirm: bool = False, minimum: int = 4):
        super().__init__(parent, None, title or tr("كلمة المرور"))
        self.password: str | None = None
        self.confirm_mode = confirm
        self.minimum = minimum
        self.setFixedSize(480, 300 if not confirm else 340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.addWidget(W.title_label(title or tr("كلمة المرور"), 14))
        if message:
            note = W.muted_label(message)
            note.setWordWrap(True)
            layout.addWidget(note)

        card = W.card()
        form = QFormLayout(card)
        self.e_pass = QLineEdit()
        self.e_pass.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(tr("كلمة المرور"), self.e_pass)
        self.e_pass2 = QLineEdit()
        self.e_pass2.setEchoMode(QLineEdit.EchoMode.Password)
        if confirm:
            form.addRow(tr("تأكيد كلمة المرور"), self.e_pass2)
        self.chk_show = W.button(tr("👁 إظهار"), "Ghost", self._toggle_show, width=110)
        form.addRow("", self.chk_show)
        layout.addWidget(card)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(theme.label_style("neg"))
        self.lbl_error.setWordWrap(True)
        layout.addWidget(self.lbl_error)
        layout.addStretch()
        layout.addLayout(self.buttons_row(W.button(tr("إلغاء"), "Ghost", self.reject, width=110),
                                          W.button(tr("تأكيد"), "Accent", self._accept, width=130)))
        self.e_pass.returnPressed.connect(self._accept)
        self.e_pass2.returnPressed.connect(self._accept)

    def _toggle_show(self) -> None:
        shown = self.e_pass.echoMode() == QLineEdit.EchoMode.Password
        mode = QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
        self.e_pass.setEchoMode(mode)
        self.e_pass2.setEchoMode(mode)
        self.chk_show.setText(tr("🙈 إخفاء") if shown else tr("👁 إظهار"))

    def _accept(self) -> None:
        password = self.e_pass.text()
        if len(password) < self.minimum:
            self.lbl_error.setText(trf("كلمة المرور قصيرة (الحد الأدنى {n} أحرف).", n=self.minimum))
            return
        if self.confirm_mode and password != self.e_pass2.text():
            self.lbl_error.setText(tr("كلمتا المرور غير متطابقتين."))
            return
        self.password = password
        self.accept()


class EncryptionDialog(BaseDialog):
    """إدارة تشفير قاعدة البيانات: تفعيل، إلغاء، تغيير كلمة المرور."""

    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, tr("تشفير قاعدة البيانات"))
        self.changed = False
        self.resize(680, 580)
        self._build()
        self._refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label(tr("تشفير قاعدة البيانات (SQLCipher)"), 15))

        self.status_box = QGroupBox(tr("الحالة الحالية"))
        self.status_layout = QGridLayout(self.status_box)
        layout.addWidget(self.status_box)

        warning = W.muted_label(tr(
            "تنبيه مهم: كلمة المرور لا يمكن استرجاعها. إذا فقدتها لن يمكن فتح قاعدة البيانات، "
            "لذلك احفظها في مكان آمن واحتفظ بنسخة احتياطية غير مشفّرة في مكان محمي."))
        warning.setWordWrap(True)
        layout.addWidget(warning)

        self.hint = W.muted_label("")
        self.hint.setWordWrap(True)
        self.hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.hint)

        buttons = QHBoxLayout()
        self.btn_enable = W.button(tr("🔒 تفعيل التشفير"), "Accent", self._enable)
        self.btn_disable = W.button(tr("🔓 إلغاء التشفير"), "Warn", self._disable)
        self.btn_change = W.button(tr("🔑 تغيير كلمة المرور"), "Gold", self._change)
        self.btn_copy = W.button(tr("📋 نسخ أمر التثبيت"), "Ghost", self._copy_hint)
        for btn in (self.btn_enable, self.btn_disable, self.btn_change, self.btn_copy):
            buttons.addWidget(btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.lbl_message = QLabel("")
        self.lbl_message.setWordWrap(True)
        layout.addWidget(self.lbl_message)
        layout.addStretch()
        layout.addLayout(self.buttons_row(self.close_button()))

    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        summary = crypto.security_summary(self.ctx.paths.data_dir, self.ctx.paths.db_path)
        self.summary = summary
        while self.status_layout.count():
            item = self.status_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        lock = summary.get("lock_data") or {}
        rows = [
            (tr("حزمة SQLCipher مثبتة"),
             tr("نعم") if summary["sqlcipher_available"] else tr("لا — راجع أمر التثبيت أدناه")),
            (tr("التشفير مُفعَّل"), tr("نعم") if summary["encryption_enabled"] else tr("لا")),
            (tr("قاعدة البيانات مشفّرة فعلياً"),
             tr("نعم") if summary["database_encrypted"] else tr("لا")),
            (tr("ملف القفل"), tr("موجود") if summary["lock_file"] else tr("غير موجود")),
            (tr("تاريخ التفعيل"), str(lock.get("created_at", "—"))),
            (tr("عدد تكرارات الاشتقاق"), str(lock.get("iterations", crypto.KDF_ITERATIONS))),
        ]
        for index, (label, value) in enumerate(rows):
            self.status_layout.addWidget(W.muted_label(f"{label}:"), index, 0)
            widget = QLabel(str(value))
            widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.status_layout.addWidget(widget, index, 1)
        self.status_layout.setColumnStretch(1, 1)

        available = summary["sqlcipher_available"]
        enabled = summary["encryption_enabled"]
        self.btn_enable.setEnabled(available and not enabled)
        self.btn_disable.setEnabled(available and enabled)
        self.btn_change.setEnabled(available and enabled)
        self.btn_copy.setVisible(not available)
        self.hint.setText("" if available else crypto.install_hint())
        if not available:
            self.lbl_message.setText(tr(
                "التشفير غير متاح حالياً لأن حزمة SQLCipher غير مثبتة — "
                "بقية مزايا البرنامج تعمل بشكل طبيعي."))
            self.lbl_message.setStyleSheet(theme.label_style("gold"))

    def _copy_hint(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText("pip install sqlcipher3-binary")
            W.info(self, tr("تم نسخ أمر التثبيت إلى الحافظة."))

    # ------------------------------------------------------------------
    def _enable(self) -> None:
        if not self.summary["sqlcipher_available"]:
            W.error(self, crypto.install_hint())
            return
        if not W.confirm(self, tr(
                "سيتم إنشاء نسخة احتياطية غير مشفّرة، ثم تشفير قاعدة البيانات.\n"
                "تذكّر كلمة المرور جيداً — لا يمكن استرجاعها.\n\nهل تريد المتابعة؟")):
            return
        dialog = PasswordDialog(self, tr("كلمة مرور التشفير"),
                                tr("ستُطلب هذه الكلمة في كل مرة يُفتح فيها البرنامج."),
                                confirm=True, minimum=6)
        if dialog.exec() != dialog.DialogCode.Accepted or not dialog.password:
            return
        password = dialog.password
        self.ctx.backup.create("pre_encrypt")
        self.ctx.db.close()          # مهم: لا اتصال مفتوح أثناء استبدال الملف
        try:
            crypto.encrypt_database(self.ctx.paths.db_path, password)
        except crypto.CryptoError as exc:
            W.error(self, str(exc))
            self.ctx.db.open()
            return
        self.changed = True
        W.info(self, tr("تم تفعيل التشفير بنجاح.") + "\n\n" +
               tr("سيُغلق البرنامج الآن. شغّله مرة أخرى وأدخل كلمة المرور."))
        QApplication.instance().quit()

    def _disable(self) -> None:
        dialog = PasswordDialog(self, tr("كلمة المرور الحالية"),
                                tr("أدخل كلمة المرور الحالية لإلغاء التشفير."))
        if dialog.exec() != dialog.DialogCode.Accepted or not dialog.password:
            return
        password = dialog.password
        if not crypto.check_password(self.ctx.paths.data_dir, password):
            W.error(self, tr("كلمة المرور غير صحيحة."))
            return
        self.ctx.backup.create("pre_decrypt")
        self.ctx.db.close()
        try:
            crypto.disable_encryption(self.ctx.paths.data_dir, self.ctx.paths.db_path, password)
        except crypto.CryptoError as exc:
            W.error(self, str(exc))
            self.ctx.db.open()
            return
        self.changed = True
        W.info(self, tr("تم إلغاء التشفير.") + "\n\n" +
               tr("سيُغلق البرنامج الآن. شغّله مرة أخرى للعمل بلا كلمة مرور."))
        QApplication.instance().quit()

    def _change(self) -> None:
        old = PasswordDialog(self, tr("كلمة المرور الحالية"))
        if old.exec() != old.DialogCode.Accepted or not old.password:
            return
        if not crypto.check_password(self.ctx.paths.data_dir, old.password):
            W.error(self, tr("كلمة المرور الحالية غير صحيحة."))
            return
        new = PasswordDialog(self, tr("كلمة المرور الجديدة"), confirm=True, minimum=6)
        if new.exec() != new.DialogCode.Accepted or not new.password:
            return
        self.ctx.backup.create("pre_rekey")
        self.ctx.db.close()
        try:
            crypto.change_password(self.ctx.paths.db_path, old.password, new.password)
        except crypto.CryptoError as exc:
            W.error(self, str(exc))
            self.ctx.db.open()
            return
        self.changed = True
        W.info(self, tr("تم تغيير كلمة المرور.") + "\n\n" +
               tr("سيُغلق البرنامج الآن. استخدم كلمة المرور الجديدة عند التشغيل."))
        QApplication.instance().quit()

    # ------------------------------------------------------------------
    def closeEvent(self, event):  # noqa: N802
        if self.changed:
            W.info(self, tr("يلزم إعادة تشغيل البرنامج لتطبيق تغيير التشفير."))
        event.accept()


def prompt_database_password(data_dir, db_path, parent=None) -> str | None:
    """يطلب كلمة مرور القاعدة المشفّرة عند بدء التشغيل (3 محاولات)."""
    message = tr("قاعدة البيانات مشفّرة. أدخل كلمة المرور لفتحها.")
    for attempt in range(3):
        remaining = 3 - attempt
        dialog = PasswordDialog(parent, tr("فتح قاعدة بيانات مشفّرة"),
                                f"{message}\n" + trf("المحاولات المتبقية: {count}", count=remaining))
        if dialog.exec() != dialog.DialogCode.Accepted:
            return None
        if dialog.password:
            return dialog.password
        if not sec.password_strength(dialog.password or "x")[0]:
            continue
    return None
