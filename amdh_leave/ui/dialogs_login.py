"""نافذة تسجيل الدخول: شعار البرنامج وشعار الدائرة، اختيار اللغة، وإدارة المحاولات."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from .. import config
from .. import i18n
from ..i18n import tr, trf
from ..services import security
from . import assets, theme, widgets as W
from .dialogs_base import BaseDialog

MAX_ATTEMPTS = 5


class LoginDialog(BaseDialog):
    """نافذة دخول مُعاد تصميمها مع الشعارات واختيار اللغة."""

    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, tr("تسجيل الدخول"))
        self.user = None
        self.attempts = 0
        self._locked = False
        self.setFixedSize(620, 520)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build()
        self._update_hint()
        QTimer.singleShot(120, self.e_user.setFocus)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 18)
        layout.setSpacing(12)
        layout.addWidget(self._logos())

        self.lbl_title = QLabel(config.APP_NAME)
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        self.lbl_title.setStyleSheet(theme.label_style("accent", 17, bold=True))
        layout.addWidget(self.lbl_title)

        self.lbl_version = W.muted_label(f"{tr('الإصدار')} {config.APP_VERSION}")
        self.lbl_version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_version)
        layout.addWidget(W.separator())

        card = W.card()
        grid = QGridLayout(card)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self.lbl_language = QLabel(tr("لغة الواجهة"))
        self.cb_language = QComboBox()
        for code, label in i18n.available_languages():
            self.cb_language.addItem(label, code)
        index = self.cb_language.findData(i18n.language())
        self.cb_language.setCurrentIndex(max(0, index))
        self.cb_language.currentIndexChanged.connect(self._switch_language)

        self.lbl_user = QLabel(tr("اسم المستخدم"))
        self.e_user = QLineEdit()
        self.e_user.setPlaceholderText(tr("أدخل اسم المستخدم"))

        self.lbl_pass = QLabel(tr("كلمة المرور"))
        self.e_pass = QLineEdit()
        self.e_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_pass.setPlaceholderText(tr("أدخل كلمة المرور"))
        self.e_pass.returnPressed.connect(self._login)
        self.e_user.returnPressed.connect(lambda: self.e_pass.setFocus())

        self.btn_eye = QPushButton("👁")
        self.btn_eye.setObjectName("Ghost")
        self.btn_eye.setFixedWidth(42)
        self.btn_eye.setCheckable(True)
        self.btn_eye.setToolTip(tr("إظهار كلمة المرور"))
        self.btn_eye.toggled.connect(self._toggle_password)

        pass_row = QWidget()
        pass_layout = QHBoxLayout(pass_row)
        pass_layout.setContentsMargins(0, 0, 0, 0)
        pass_layout.setSpacing(6)
        pass_layout.addWidget(self.e_pass, 1)
        pass_layout.addWidget(self.btn_eye)

        self.chk_remember = QCheckBox(tr("تذكر اسم المستخدم"))
        last_user = str(self.ctx.ui_get("last_user", "") or "")
        self.chk_remember.setChecked(bool(last_user))
        if last_user:
            self.e_user.setText(last_user)

        grid.addWidget(self.lbl_language, 0, 0)
        grid.addWidget(self.cb_language, 0, 1)
        grid.addWidget(self.lbl_user, 1, 0)
        grid.addWidget(self.e_user, 1, 1)
        grid.addWidget(self.lbl_pass, 2, 0)
        grid.addWidget(pass_row, 2, 1)
        grid.addWidget(self.chk_remember, 3, 1)
        grid.setColumnStretch(1, 1)
        layout.addWidget(card)

        self.lbl_error = QLabel("")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setStyleSheet(theme.label_style("neg"))
        self.lbl_error.setMinimumHeight(34)
        layout.addWidget(self.lbl_error)

        self.lbl_footer = W.muted_label("")
        self.lbl_footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_footer)

        layout.addStretch()
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_exit = W.button(tr("خروج"), "Ghost", self.reject, width=120)
        self.btn_login = W.button(tr("دخول"), "Accent", self._login, width=150)
        buttons.addWidget(self.btn_exit)
        buttons.addWidget(self.btn_login)
        buttons.addStretch()
        layout.addLayout(buttons)

    def _logos(self) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(18)

        self.img_department = QLabel()
        self.img_department.setFixedSize(84, 84)
        self.img_department.setAlignment(Qt.AlignmentFlag.AlignCenter)
        department = assets.department_logo(84)
        if department is not None:
            self.img_department.setPixmap(department)
        row.addWidget(self.img_department)

        row.addStretch()

        self.img_logo = QLabel()
        self.img_logo.setFixedSize(96, 96)
        self.img_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo = assets.logo(96)
        if logo is not None:
            self.img_logo.setPixmap(logo)
        row.addWidget(self.img_logo)
        return holder

    # ------------------------------------------------------------------
    def _toggle_password(self, shown: bool) -> None:
        self.e_pass.setEchoMode(QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password)
        self.btn_eye.setToolTip(tr("إخفاء كلمة المرور") if shown else tr("إظهار كلمة المرور"))

    def _switch_language(self) -> None:
        code = self.cb_language.currentData()
        if not code or code == i18n.language():
            return
        i18n.set_language(code)
        self.ctx.ui_set("language", code)
        self.retranslate()
        self._update_hint()

    def retranslate(self) -> None:
        """إعادة تعريب/ترجمة نصوص النافذة فوراً (لتغيير اللغة قبل الدخول)."""
        self.setWindowTitle(tr("تسجيل الدخول"))
        self.lbl_version.setText(f"{tr('الإصدار')} {config.APP_VERSION}")
        self.lbl_language.setText(tr("لغة الواجهة"))
        self.lbl_user.setText(tr("اسم المستخدم"))
        self.lbl_pass.setText(tr("كلمة المرور"))
        self.e_user.setPlaceholderText(tr("أدخل اسم المستخدم"))
        self.e_pass.setPlaceholderText(tr("أدخل كلمة المرور"))
        self.chk_remember.setText(tr("تذكر اسم المستخدم"))
        self.btn_exit.setText(tr("خروج"))
        self.btn_login.setText(tr("دخول"))
        self.lbl_error.setText("")

    def _update_hint(self) -> None:
        stats = self.ctx.db.stats()
        self.lbl_footer.setText(
            f"{tr('قاعدة البيانات')}: {self.ctx.paths.db_path.name} | "
            f"{tr('الموظفون')}: {stats['employees']} | {tr('الإجازات')}: {stats['leaves']}")

    # ------------------------------------------------------------------
    def _login(self) -> None:
        if self._locked:
            return
        username = self.e_user.text().strip()
        password = self.e_pass.text()
        if not username:
            self._fail(tr("أدخل اسم المستخدم."))
            self.e_user.setFocus()
            return
        user = self.ctx.db.get_user(username)
        if not user or not user.active:
            self._fail(tr("المستخدم غير موجود أو غير مُفعَّل."))
            return
        if not security.verify_password(password, user.password_hash, user.salt, user.iterations):
            self._fail(tr("كلمة المرور غير صحيحة."))
            return
        self.ctx.db.touch_login(username)
        self.ctx.ui_set("last_user", username if self.chk_remember.isChecked() else "")
        self.user = user
        self.ctx.db.log(username, tr("دخول"), "session", username, "")
        self.accept()

    def _fail(self, message: str) -> None:
        self.attempts += 1
        self.e_pass.clear()
        self.e_pass.setFocus()
        remaining = MAX_ATTEMPTS - self.attempts
        if remaining <= 0:
            self._lock()
            return
        self.lbl_error.setText(f"{message}\n{trf('المحاولات المتبقية: {count}', count=remaining)}")

    def _lock(self) -> None:
        """إيقاف المحاولات دقيقة واحدة بعد استنفاد المحاولات (حماية بسيطة)."""
        self._locked = True
        self.btn_login.setEnabled(False)
        self.e_user.setEnabled(False)
        self.e_pass.setEnabled(False)
        seconds = 60
        self.lbl_error.setText(trf("تم إيقاف المحاولات مؤقتاً. أعد المحاولة بعد {n} ثانية", n=seconds))

        def tick():
            nonlocal seconds
            seconds -= 1
            if seconds <= 0:
                timer.stop()
                self._locked = False
                self.btn_login.setEnabled(True)
                self.e_user.setEnabled(True)
                self.e_pass.setEnabled(True)
                self.attempts = 0
                self.lbl_error.setText("")
                self.e_pass.setFocus()
            else:
                self.lbl_error.setText(
                    trf("تم إيقاف المحاولات مؤقتاً. أعد المحاولة بعد {n} ثانية", n=seconds))

        timer = QTimer(self)
        timer.timeout.connect(tick)
        timer.start(1000)


def default_password_warning(db) -> str:
    """تحذير إن كانت كلمة مرور المدير لا تزال الافتراضية (admin)."""
    admin = db.get_user("admin")
    if admin and admin.password_hash and security.verify_password(
            "admin", admin.password_hash, admin.salt, admin.iterations):
        return tr("كلمة مرور المدير الافتراضية (admin) لم تُغيَّر بعد — يُنصح بتغييرها فوراً.")
    return ""
