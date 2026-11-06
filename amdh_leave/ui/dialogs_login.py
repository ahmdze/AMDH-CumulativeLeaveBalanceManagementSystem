"""نافذة تسجيل الدخول: شعار البرنامج وشعار الدائرة، اختيار اللغة، وإدارة المحاولات."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import colors, config
from ..services import security
from . import assets, theme
from . import widgets as W
from .dialogs_base import BaseDialog

MAX_ATTEMPTS = 5

# التأخير التصاعدي (بالمللي ثانية) حسب رقم المحاولة الفاشلة
# المحاولة 1: 1 ثانية، 2: 3 ثوانٍ، 3: 10 ثوانٍ، 4: 30 ثانية، ثم قفل بعد 5
PROGRESSIVE_DELAYS = {1: 1000, 2: 3000, 3: 10000, 4: 30000}


class _HeaderBanner(QWidget):
    """شريط علوي متدرج مع الشعار في المنتصف."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(160)
        self._logo_pixmap = None
        logo = assets.logo(120)
        if logo is not None:
            self._logo_pixmap = logo.scaled(
                100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # التدرج الخلفي
        grad = QLinearGradient(0, 0, 0, self.height())
        accent = theme.color("accent")
        grad.setColorAt(0, QColor(accent))
        grad.setColorAt(1, QColor(colors.darken(accent, 0.2)))
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)

        # رسم خلفية منحنية
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(self.width(), 0)
        path.lineTo(self.width(), self.height() * 0.6)
        path.quadTo(self.width() * 0.5, self.height() * 1.1, 0, self.height() * 0.6)
        path.closeSubpath()
        painter.fillPath(path, grad)

        # الشعار في المنتصف
        if self._logo_pixmap is not None:
            lx = (self.width() - self._logo_pixmap.width()) // 2
            ly = 20
            painter.drawPixmap(lx, ly, self._logo_pixmap)

        painter.end()


class LoginDialog(BaseDialog):
    """نافذة دخول مُعاد تصميمها مع الشعارات واختيار اللغة."""

    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, "تسجيل الدخول")
        self.user = None
        self.attempts = 0
        self._locked = False
        self.setFixedSize(520, 600)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build()
        self._update_hint()
        QTimer.singleShot(120, self.e_user.setFocus)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # الشريط العلوي المتدرج
        self.banner = _HeaderBanner(self)
        layout.addWidget(self.banner)

        # العنوان والإصدار
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(30, 16, 30, 8)
        info_layout.setSpacing(4)

        self.lbl_title = QLabel(config.APP_NAME)
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.lbl_title.setStyleSheet(theme.label_style("accent", 16, bold=True))
        info_layout.addWidget(self.lbl_title)

        self.lbl_version = W.muted_label(f"الإصدار {config.APP_VERSION}")
        self.lbl_version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_layout.addWidget(self.lbl_version)

        layout.addWidget(info_widget)

        # منطقة الحقول - بدون بطاقة
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(40, 16, 40, 16)
        form_layout.setSpacing(12)

        # حقل اسم المستخدم
        self.lbl_user = QLabel("اسم المستخدم")
        self.lbl_user.setStyleSheet(theme.label_style("text", 12, bold=True))
        form_layout.addWidget(self.lbl_user)

        self.e_user = QLineEdit()
        self.e_user.setPlaceholderText("أدخل اسم المستخدم")
        self.e_user.setFixedHeight(48)
        self.e_user.setStyleSheet(
            """
            QLineEdit {{
                background: {};
                border: 2px solid {};
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 13px;
                color: {};
            }}
            QLineEdit:focus {{
                border-color: {};
            }}
        """.format(theme.color("card"), theme.color("muted_bg"), theme.color("text"), theme.color("accent"))
        )
        form_layout.addWidget(self.e_user)

        # حقل كلمة المرور
        self.lbl_pass = QLabel("كلمة المرور")
        self.lbl_pass.setStyleSheet(theme.label_style("text", 12, bold=True))
        form_layout.addWidget(self.lbl_pass)

        pass_row = QWidget()
        pass_layout = QHBoxLayout(pass_row)
        pass_layout.setContentsMargins(0, 0, 0, 0)
        pass_layout.setSpacing(6)

        self.e_pass = QLineEdit()
        self.e_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_pass.setPlaceholderText("أدخل كلمة المرور")
        self.e_pass.setFixedHeight(48)
        self.e_pass.setStyleSheet(self.e_user.styleSheet())
        self.e_pass.returnPressed.connect(self._login)
        self.e_user.returnPressed.connect(lambda: self.e_pass.setFocus())
        pass_layout.addWidget(self.e_pass, 1)

        self.btn_eye = QPushButton("👁")
        self.btn_eye.setObjectName("Ghost")
        self.btn_eye.setFixedWidth(48)
        self.btn_eye.setFixedHeight(48)
        self.btn_eye.setCheckable(True)
        self.btn_eye.setToolTip("إظهار كلمة المرور")
        self.btn_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_eye.setStyleSheet(
            """
            QPushButton {{
                background: {};
                border: 2px solid {};
                border-radius: 8px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background: {};
            }}
        """.format(theme.color("card"), theme.color("muted_bg"), theme.color("hover_bg"))
        )
        self.btn_eye.toggled.connect(self._toggle_password)
        pass_layout.addWidget(self.btn_eye)

        form_layout.addWidget(pass_row)

        # تذكر اسم المستخدم
        self.chk_remember = QCheckBox("تذكر اسم المستخدم")
        self.chk_remember.setStyleSheet(theme.label_style("muted"))
        self.chk_remember.setCursor(Qt.CursorShape.PointingHandCursor)
        last_user = str(self.ctx.ui_get("last_user", "") or "")
        self.chk_remember.setChecked(bool(last_user))
        if last_user:
            self.e_user.setText(last_user)
        form_layout.addWidget(self.chk_remember)

        layout.addWidget(form_widget)

        # رسالة الخطأ
        self.lbl_error = QLabel("")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setStyleSheet(theme.label_style("neg", 12))
        self.lbl_error.setMinimumHeight(30)
        layout.addWidget(self.lbl_error)

        # الأزرار
        buttons = QWidget()
        btn_layout = QHBoxLayout(buttons)
        btn_layout.setContentsMargins(40, 16, 40, 20)
        btn_layout.setSpacing(12)

        self.btn_login = QPushButton("دخول  🔓")
        self.btn_login.setFixedHeight(48)
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.setStyleSheet(
            """
            QPushButton {{
                background: {};
                border: none;
                border-radius: 8px;
                color: {};
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {};
            }}
            QPushButton:pressed {{
                background: {};
            }}
        """.format(
                theme.color("accent"),
                theme.color("on_accent"),
                colors.darken(theme.color("accent"), 0.1),
                colors.darken(theme.color("accent"), 0.2),
            )
        )
        self.btn_login.clicked.connect(self._login)
        btn_layout.addWidget(self.btn_login, 1)

        self.btn_exit = QPushButton("خروج")
        self.btn_exit.setFixedHeight(48)
        self.btn_exit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_exit.setStyleSheet(
            """
            QPushButton {{
                background: transparent;
                border: 2px solid {};
                border-radius: 8px;
                color: {};
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {};
            }}
        """.format(theme.color("muted_bg"), theme.color("muted"), theme.color("hover_bg"))
        )
        self.btn_exit.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_exit)

        layout.addWidget(buttons)

        # الفوتر
        self.lbl_footer = W.muted_label("")
        self.lbl_footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_footer.setFixedHeight(20)
        layout.addWidget(self.lbl_footer)
        layout.addStretch()

    def _update_logo_display(self):
        """تحديث عرض الشعارات في الشريط العلوي."""
        self.banner.update()

    # ------------------------------------------------------------------
    def _toggle_password(self, shown: bool) -> None:
        self.e_pass.setEchoMode(QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password)

    def _update_hint(self) -> None:
        stats = self.ctx.db.stats()
        self.lbl_footer.setText(
            f"قاعدة البيانات: {self.ctx.paths.db_path.name} | "
            f"الموظفون: {stats['employees']} | الإجازات: {stats['leaves']}"
        )

    # ------------------------------------------------------------------
    def _login(self) -> None:
        if self._locked:
            return
        username = self.e_user.text().strip()
        password = self.e_pass.text()
        if not username:
            self._fail("أدخل اسم المستخدم.")
            self.e_user.setFocus()
            return
        user = self.ctx.db.get_user(username)
        if not user or not user.active:
            self._fail("المستخدم غير موجود أو غير مُفعَّل.")
            return
        if not security.verify_password(password, user.password_hash, user.salt, user.iterations):
            self._fail("كلمة المرور غير صحيحة.")
            return
        self.ctx.db.touch_login(username)
        self.ctx.ui_set("last_user", username if self.chk_remember.isChecked() else "")
        self.user = user
        self.ctx.db.log(username, "دخول", "session", username, "")
        self.accept()

    def _fail(self, message: str) -> None:
        self.attempts += 1
        self.e_pass.clear()
        remaining = MAX_ATTEMPTS - self.attempts
        if remaining <= 0:
            self._lock()
            return

        # تأخير تصاعدي قبل السماح بالمحاولة التالية
        delay_ms = PROGRESSIVE_DELAYS.get(self.attempts, 0)
        if delay_ms > 0:
            delay_sec = delay_ms // 1000
            self._show_delay(message, delay_sec, delay_ms)
            return

        self.e_pass.setFocus()
        self.lbl_error.setText(f"{message}\nالمحاولات المتبقية: {remaining}")

    def _show_delay(self, message: str, delay_sec: int, delay_ms: int) -> None:
        """عرض رسالة الانتظار مع عداد تنازلي، ثم السماح بالمحاولة التالية."""
        self.btn_login.setEnabled(False)
        self.e_user.setEnabled(False)
        self.e_pass.setEnabled(False)
        seconds = delay_sec

        def tick():
            nonlocal seconds
            seconds -= 1
            if seconds <= 0:
                timer.stop()
                self.btn_login.setEnabled(True)
                self.e_user.setEnabled(True)
                self.e_pass.setEnabled(True)
                self.e_pass.setFocus()
                remaining = MAX_ATTEMPTS - self.attempts
                self.lbl_error.setText(f"{message}\nالمحاولات المتبقية: {remaining}")
            else:
                self.lbl_error.setText(f"{message}\nانتظر {seconds} ثانية قبل المحاولة التالية...")

        timer = QTimer(self)
        timer.timeout.connect(tick)
        timer.start(1000)
        self.lbl_error.setText(f"{message}\nانتظر {delay_sec} ثانية قبل المحاولة التالية...")

    def _lock(self) -> None:
        """إيقاف المحاولات دقيقة واحدة بعد استنفاد المحاولات (حماية بسيطة)."""
        self._locked = True
        self.btn_login.setEnabled(False)
        self.e_user.setEnabled(False)
        self.e_pass.setEnabled(False)
        seconds = 60
        self.lbl_error.setText(f"تم إيقاف المحاولات مؤقتاً. أعد المحاولة بعد {seconds} ثانية")

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
                self.lbl_error.setText(f"تم إيقاف المحاولات مؤقتاً. أعد المحاولة بعد {seconds} ثانية")

        timer = QTimer(self)
        timer.timeout.connect(tick)
        timer.start(1000)


def default_password_warning(db) -> str:
    """تحذير إن كانت كلمة مرور المدير لا تزال الافتراضية (admin)."""
    admin = db.get_user("admin")
    if (
        admin
        and admin.password_hash
        and security.verify_password("admin", admin.password_hash, admin.salt, admin.iterations)
    ):
        return "كلمة مرور المدير الافتراضية (admin) لم تُغيَّر بعد — يُنصح بتغييرها فوراً."
    return ""
