"""اختبارات نافذة تسجيل الدخول (المسارات التي كانت تُسقط البرنامج سابقاً)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication                      # noqa: E402

from amdh_leave.services import security                       # noqa: E402
from amdh_leave.ui import theme                                 # noqa: E402
from amdh_leave.ui.dialogs_login import MAX_ATTEMPTS, LoginDialog  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_login_with_correct_password_authenticates(qapp, ctx):
    dialog = LoginDialog(None, ctx)
    dialog.e_user.setText("admin")
    dialog.e_pass.setText("admin")
    dialog._login()
    assert dialog.user is not None
    assert dialog.user.username == "admin"
    assert ctx.db.get_user("admin").last_login
    dialog.close()


def test_login_with_wrong_password_shows_remaining_attempts(qapp, ctx):
    """كان هذا المسار يُسقط البرنامج (NameError: trf) قبل إصلاح الاستيراد."""
    dialog = LoginDialog(None, ctx)
    dialog.e_user.setText("admin")
    dialog.e_pass.setText("كلمة خاطئة")
    dialog._login()
    assert dialog.user is None
    assert dialog.lbl_error.text()                     # لا يظهر خطأ فارغ
    assert str(MAX_ATTEMPTS - 1) in dialog.lbl_error.text()   # المحاولات المتبقية
    assert dialog.e_pass.text() == ""                  # يُفرَّغ الحقل
    dialog.close()


def test_login_unknown_user_message(qapp, ctx):
    dialog = LoginDialog(None, ctx)
    dialog.e_user.setText("لا-يوجد")
    dialog.e_pass.setText("x")
    dialog._login()
    assert dialog.user is None
    assert dialog.lbl_error.text()
    dialog.close()


def test_login_requires_username(qapp, ctx):
    dialog = LoginDialog(None, ctx)
    dialog.e_user.setText("")
    dialog.e_pass.setText("x")
    dialog._login()
    assert dialog.user is None
    assert dialog.lbl_error.text()
    dialog.close()


def test_login_locks_after_max_attempts(qapp, ctx):
    """بعد استنفاد المحاولات يُعطَّل الدخول مؤقتاً (يحتاج مؤقّتاً حقيقياً)."""
    dialog = LoginDialog(None, ctx)
    dialog.e_user.setText("admin")
    for _ in range(MAX_ATTEMPTS):
        dialog.e_pass.setText("خاطئة")
        dialog._login()
    assert dialog._locked is True
    assert dialog.btn_login.isEnabled() is False
    assert dialog.e_pass.isEnabled() is False
    assert dialog.lbl_error.text()
    dialog._locked = False            # لتفادي مؤقّت معلّق عند إغلاق الحوار
    dialog.close()


def test_login_remembers_username_via_settings(qapp, ctx):
    dialog = LoginDialog(None, ctx)
    dialog.e_user.setText("admin")
    dialog.e_pass.setText("admin")
    dialog.chk_remember.setChecked(True)
    dialog._login()
    assert ctx.ui_get("last_user", "") == "admin"

    dialog.chk_remember.setChecked(False)
    dialog.e_pass.setText("admin")
    dialog._login()
    assert ctx.ui_get("last_user", "") == ""
    dialog.close()


def test_login_password_toggle_and_translate(qapp, ctx):
    dialog = LoginDialog(None, ctx)
    dialog._toggle_password(True)
    assert dialog.e_pass.echoMode().name == "Normal"
    dialog._toggle_password(False)
    assert dialog.e_pass.echoMode().name == "Password"
    dialog.retranslate()               # لا يُسقط البرنامج ولا يترك خطأ ظاهراً
    assert dialog.lbl_error.text() == ""
    dialog.close()


def test_default_password_warning(qapp, ctx):
    from amdh_leave.ui.dialogs_login import default_password_warning
    assert default_password_warning(ctx.db)          # كلمة المرور الافتراضية admin
    user = ctx.db.get_user("admin")
    user.password_hash, user.salt, user.iterations = security.hash_password("قوية-جداً-2026")
    ctx.db.save_user(user)
    assert default_password_warning(ctx.db) == ""


def test_theme_and_language_menu_actions(qapp, ctx):
    """قوائم الثيم واللغة تُبنى بلا فتح حوارات (وكانت مساراً غير مغطّى)."""
    from amdh_leave import config
    from amdh_leave.services import balance as B
    from amdh_leave.ui.main_window import MainWindow

    window = MainWindow(ctx)
    try:
        theme_keys = [action.data() for action in window.theme_actions()]
        assert theme_keys == [key for key, _label, _mode in config.THEMES]
        language_codes = [action.data() for action in window.language_actions()]
        assert language_codes == ["ar", "ku", "en"]

        for key in theme_keys:
            window.set_theme(key)
            assert theme.current() == key
        window.set_theme("dark")
        window._apply_language("ar")            # نفس اللغة ⇒ بلا حوار
        assert ctx.ui_get("language", "ar") == "ar"
        assert window.table.table is not None
    finally:
        window.close()
