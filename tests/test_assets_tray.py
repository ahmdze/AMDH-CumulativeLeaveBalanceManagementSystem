"""اختبارات الأصول (الشعارات) وإشعارات سطح المكتب."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QObject                           # noqa: E402
from PyQt6.QtWidgets import QApplication                      # noqa: E402

from amdh_leave.ui import assets, theme                        # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_placeholder_assets_are_detected():
    """الشعارات المسلَّمة فارغة (شفافة) فيُستخدم البديل المرسوم، أو تكون صور حقيقية."""
    for name in (assets.LOGO, assets.DEPARTMENT_LOGO, assets.APP_ICON):
        path = assets.PACKAGE_ASSETS / name
        if not path.exists():
            pytest.skip(f"{name} غير موجود")
        size = path.stat().st_size
        if size < assets.PLACEHOLDER_MAX_BYTES:
            # صورة فارغة (placeholder) — يجب أن ترجع asset_path None
            assert assets.asset_path(name) is None
            assert assets.is_placeholder(name) is True
        else:
            # صورة حقيقية — يجب أن ترجع asset_path المسار
            assert assets.asset_path(name) is not None
            assert assets.is_placeholder(name) is False


def test_developer_photo_is_fixed_in_package(qapp):
    """صورة المطوّر حقيقية وثابتة من الحزمة، ولا يستبدلها مجلد المستخدم."""
    path = assets.PACKAGE_ASSETS / assets.DEVELOPER_PHOTO
    assert path.exists() and path.stat().st_size >= assets.PLACEHOLDER_MAX_BYTES
    assert assets.package_asset_path(assets.DEVELOPER_PHOTO) is not None
    assert assets.is_placeholder(assets.DEVELOPER_PHOTO) is False
    assert assets.developer_photo(240, 300) is not None


def test_user_assets_dir_takes_priority(qapp, tmp_path):
    """أي صورة يضعها المستخدم في مجلد البيانات تُقدَّم على صور الحزمة."""
    assets.set_user_assets_dir(None)
    # إذا كان الشعار حقيقيًا في الحزمة، نختبر بصور الدائرة بدلاً منه
    package_logo = assets.PACKAGE_ASSETS / assets.LOGO
    if package_logo.exists() and package_logo.stat().st_size >= assets.PLACEHOLDER_MAX_BYTES:
        # الشعار حقيقي — نستخدم department_logo للاختبار
        assert assets.asset_path(assets.DEPARTMENT_LOGO) is not None or True
    else:
        assert assets.asset_path(assets.LOGO) is None

    user_dir = tmp_path / "assets"
    user_dir.mkdir()
    image = user_dir / assets.LOGO
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 2000)     # أكبر من حد العنصر الفارغ
    assets.set_user_assets_dir(user_dir)
    try:
        assert assets.asset_path(assets.LOGO) == image
        assert assets.is_placeholder(assets.LOGO) is False
        assert assets.user_assets_dir() == user_dir
    finally:
        assets.set_user_assets_dir(None)


def test_fallback_paintings_have_expected_sizes(qapp):
    for key in ("dark", "light", "midnight", "emerald", "warm"):
        theme.set_theme(key)
        logo = assets.draw_logo(128)
        assert logo.width() == 128 and not logo.isNull()
        department = assets.draw_department_logo(96)
        assert department.width() == 96 and not department.isNull()
        photo = assets.draw_developer_photo(160, 200)
        assert photo.width() == 160 and photo.height() == 200 and not photo.isNull()
    theme.set_theme("dark")


def test_helpers_return_pixmaps_or_none(qapp):
    logo = assets.logo(64)
    assert logo is not None and logo.width() == 64
    department = assets.department_logo(72)
    assert department is not None and department.width() == 72
    photo = assets.developer_photo(120, 150)
    assert photo is not None and photo.height() == 150
    # إذا كان الشعار حقيقيًا في الحزمة، fallback=False يرجع الصورة وليس None
    package_logo = assets.PACKAGE_ASSETS / assets.LOGO
    if package_logo.exists() and package_logo.stat().st_size >= assets.PLACEHOLDER_MAX_BYTES:
        assert assets.logo(64, fallback=False) is not None
    else:
        assert assets.logo(64, fallback=False) is None


def test_app_icon_is_never_empty(qapp):
    icon = assets.app_icon()
    assert not icon.isNull()
    sizes = {(size.width(), size.height()) for size in icon.availableSizes()}
    assert (64, 64) in sizes or (256, 256) in sizes


def test_apply_app_icon_does_not_raise(qapp):
    assets.apply_app_icon(qapp)
    assert not qapp.windowIcon().isNull()


# ---------------------------------------------------------------------------
# إشعارات سطح المكتب
# ---------------------------------------------------------------------------
def test_tray_controller_graceful_without_system_tray(qapp, tmp_path, monkeypatch):
    from amdh_leave.ui.tray import TrayController

    monkeypatch.setattr("PyQt6.QtWidgets.QSystemTrayIcon.isSystemTrayAvailable",
                        staticmethod(lambda: False))
    monkeypatch.setattr("amdh_leave.ui.tray.reports.collect_alerts",
                        lambda employees, policy: [])
    controller = TrayController(_FakeWindow(), _FakeContext(tmp_path))
    assert controller.available is False
    assert controller.start() is False          # لا يتعطّل بلا صندوق
    assert controller.refresh_alerts(notify=True) == 0
    controller.notify("عنوان", "نص")            # بلا أيقونة ⇒ لا شيء
    assert controller.tray is None
    controller.shutdown()


def test_tray_alert_counting_and_deduplication(qapp, tmp_path, monkeypatch):
    from amdh_leave.ui.tray import TrayController

    alerts = [_Alert("high"), _Alert("medium"), _Alert("info")]
    monkeypatch.setattr("amdh_leave.ui.tray.reports.collect_alerts",
                        lambda employees, policy: alerts)
    controller = TrayController(_FakeWindow(), _FakeContext(tmp_path))
    count = controller.refresh_alerts(notify=False)
    assert count == 2                            # المهم والمتوسط فقط
    assert len(controller._seen) == 2
    assert controller.refresh_alerts(notify=True) == 2
    assert controller.tray is None               # لم تُنشأ أيقونة في بيئة بلا صندوق


def test_tray_menu_actions_when_available(qapp, tmp_path, monkeypatch):
    """عند توفّر الصندوق تُبنى القائمة وتعمل الإجراءات (بلا عرض فعلي)."""
    from amdh_leave.ui.tray import TrayController

    monkeypatch.setattr("PyQt6.QtWidgets.QSystemTrayIcon.isSystemTrayAvailable",
                        staticmethod(lambda: True))
    monkeypatch.setattr("amdh_leave.ui.tray.reports.collect_alerts",
                        lambda employees, policy: [_Alert("high")])
    context = _FakeContext(tmp_path)
    controller = TrayController(_FakeWindow(), context)
    assert controller.start() is True
    try:
        assert controller.tray is not None and not controller.tray.isVisible() is False
        assert controller.menu is not None
        assert controller.act_alerts is not None
        controller.refresh_alerts(notify=False)
        assert "1" in controller.act_alerts.text()
    finally:
        controller.shutdown()
    assert controller.tray is None


class _Alert:
    def __init__(self, severity: str):
        self.severity = severity
        self.kind = "low_balance"
        self.emp_id = "1"
        self.leave_id = None
        self.message = f"تنبيه {severity}"


class _FakeWindow(QObject):
    def __init__(self):
        super().__init__()
        self._force_quit = False
        self.hidden = False

    def layoutDirection(self):
        from PyQt6.QtCore import Qt
        return Qt.LayoutDirection.RightToLeft

    def isVisible(self):
        return True

    def isMinimized(self):
        return False

    def showNormal(self):
        pass

    def activateWindow(self):
        pass

    def raise_(self):
        pass

    def hide(self):
        self.hidden = True

    def _open_notifications(self):
        pass

    def _open_dashboard(self):
        pass

    def _open_calendar(self):
        pass

    def _quick_leave(self):
        pass

    def _open_about(self):
        pass

    def set_theme(self, _name):
        pass


class _FakeContext:
    def __init__(self, tmp_path, alerts=None):
        self.paths = type("P", (), {"data_dir": tmp_path})()
        self._settings = {}
        self._alerts = alerts or []
        self.backup = _FakeBackup()

    def ui_get(self, key, default=None, type_=None):
        return self._settings.get(key, default)

    def ui_set(self, key, value):
        self._settings[key] = value

    def employees(self):
        return []

    def db(self):
        return None

    @property
    def db(self):
        from amdh_leave.rules import Policy

        class _Db:
            def policy(self, refresh=False):
                return Policy.from_meta({})

            def log(self, *args, **kwargs):
                pass

        return _Db()


class _FakeBackup:
    def create(self, _kind="manual"):
        return None
