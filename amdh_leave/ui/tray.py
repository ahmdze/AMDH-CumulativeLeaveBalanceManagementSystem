"""إشعارات سطح المكتب (Tray): أيقونة، قائمة سريعة، تنبيهات دورية."""

from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ..logging_setup import get_logger
from ..services import reports
from . import assets, theme

LOG = get_logger("tray")


class TrayController(QObject):
    """يدير أيقونة الصندوق (Tray) وقائمتها وإشعاراتها.

    يعمل بأمان في البيئات التي لا تدعم الصندوق (مثل الفحص الآلي headless).
    """

    def __init__(self, window, ctx):
        super().__init__(window)
        self.window = window
        self.ctx = ctx
        self.tray: QSystemTrayIcon | None = None
        self.menu: QMenu | None = None
        self.act_alerts: QAction | None = None
        self.timer: QTimer | None = None
        self._seen: set[str] = set()
        self.available = QSystemTrayIcon.isSystemTrayAvailable()

    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return bool(self.ctx.ui_get("tray_enabled", True, bool))

    @property
    def popups_enabled(self) -> bool:
        return bool(self.ctx.ui_get("tray_notifications", True, bool))

    def start(self) -> bool:
        """يبدأ عمل الأيقونة. يعيد True إن نجح."""
        if not self.available or not self.enabled:
            LOG.info("أيقونة الصندوق غير مُفعَّلة أو غير مدعومة (available=%s)", self.available)
            return False
        if self.tray is not None:
            return True
        self.tray = QSystemTrayIcon(assets.app_icon(), self.window)
        self.tray.setToolTip(f"{self.ctx.ui_get('app_name', '') or ''}".strip() or
                             "نظام إدارة الرصيد التراكمي للإجازات")
        self._build_menu()
        self.tray.activated.connect(self._on_activated)
        self.tray.show()

        minutes = int(self.ctx.ui_get("tray_check_minutes", 30) or 30)
        if minutes > 0:
            self.timer = QTimer(self)
            self.timer.setInterval(max(1, minutes) * 60_000)
            self.timer.timeout.connect(lambda: self.refresh_alerts(notify=True))
            self.timer.start()
        LOG.info("بدأت أيقونة الصندوق (فحص كل %s دقيقة)", minutes)
        return True

    def _build_menu(self) -> None:
        menu = QMenu()
        menu.setLayoutDirection(self.window.layoutDirection())

        act_toggle = QAction("إظهار/إخفاء النافذة", self)
        act_toggle.triggered.connect(self.toggle_window)
        menu.addAction(act_toggle)
        menu.addSeparator()

        self.act_alerts = QAction("التنبيهات", self)
        self.act_alerts.triggered.connect(self.window._open_notifications)
        menu.addAction(self.act_alerts)

        act_dashboard = QAction("لوحة المؤشرات", self)
        act_dashboard.triggered.connect(self.window._open_dashboard)
        menu.addAction(act_dashboard)

        act_calendar = QAction("تقويم الإجازات", self)
        act_calendar.triggered.connect(self.window._open_calendar)
        menu.addAction(act_calendar)

        def allowed(permission: str) -> bool:
            checker = getattr(self.ctx, "can", None)
            return True if not callable(checker) else bool(checker(permission))

        if allowed("edit_leave"):
            act_leave = QAction("تسجيل إجازة", self)
            act_leave.triggered.connect(self.window._quick_leave)
            menu.addAction(act_leave)
        menu.addSeparator()

        if allowed("backup_restore"):
            act_backup = QAction("نسخة احتياطية الآن", self)
            act_backup.triggered.connect(self.backup_now)
            menu.addAction(act_backup)

        theme_menu = menu.addMenu("الثيم")
        theme_menu.setLayoutDirection(self.window.layoutDirection())
        for key, label in theme.theme_choices():
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(key == theme.current())
            action.triggered.connect(lambda _c=False, name=key: self.window.set_theme(name))
            theme_menu.addAction(action)

        menu.addSeparator()
        act_about = QAction("حول النظام", self)
        act_about.triggered.connect(self.window._open_about)
        menu.addAction(act_about)

        act_exit = QAction("خروج", self)
        act_exit.triggered.connect(self.quit_application)
        menu.addAction(act_exit)

        self.menu = menu
        self.tray.setContextMenu(menu)

    # ------------------------------------------------------------------
    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_window()

    def toggle_window(self) -> None:
        if self.window.isVisible() and not self.window.isMinimized():
            self.window.hide()
        else:
            self.window.showNormal()
            self.window.activateWindow()
            self.window.raise_()

    def quit_application(self) -> None:
        self.window._force_quit = True          # يتجاوز الإخفاء إلى الصندوق
        QApplication.instance().quit()

    def backup_now(self) -> None:
        path = self.ctx.backup.create("manual")
        if path:
            self.notify("نسخة احتياطية", f"تم إنشاء نسخة احتياطية: {path.name}")
        else:
            self.notify("نسخة احتياطية", "تعذّر إنشاء النسخة الاحتياطية (راجع ملف السجل).",
                        warning=True)

    # ------------------------------------------------------------------
    @staticmethod
    def _signature(alerts) -> set[str]:
        return {f"{a.kind}|{a.emp_id}|{a.leave_id}|{a.message}" for a in alerts}

    def refresh_alerts(self, notify: bool = True) -> int:
        """يفحص التنبيهات، يحدّث عدّاد القائمة، ويعرض إشعاراً بالجديد."""
        policy = self.ctx.db.policy(refresh=True)
        alerts = reports.collect_alerts(self.ctx.employees(), policy)
        important = [a for a in alerts if a.severity in ("high", "medium")]
        if self.act_alerts is not None:
            count = len(important)
            self.act_alerts.setText(f"التنبيهات ({count})" if count
                                    else "التنبيهات")
        current = self._signature(important)
        new_items = [a for a in important if f"{a.kind}|{a.emp_id}|{a.leave_id}|{a.message}"
                     not in self._seen]
        self._seen |= current
        if notify and new_items and self.popups_enabled:
            first = new_items[0]
            extra = len(new_items) - 1
            body = first.message if not extra else f"{first.message} (+{extra})"
            self.notify(f"تنبيهات جديدة ({len(new_items)})", body,
                        warning=first.severity == "high")
        return len(important)

    def notify(self, title: str, message: str, warning: bool = False) -> None:
        if self.tray is None or not self.popups_enabled:
            return
        icon = (QSystemTrayIcon.MessageIcon.Warning if warning
                else QSystemTrayIcon.MessageIcon.Information)
        try:
            self.tray.showMessage(title, message, icon, 8000)
        except Exception:  # pragma: no cover - بعض البيئات لا تدعم الإشعار
            LOG.debug("تعذّر عرض إشعار الصندوق")

    def shutdown(self) -> None:
        if self.timer is not None:
            self.timer.stop()
            self.timer = None
        if self.tray is not None:
            self.tray.hide()
            self.tray = None
