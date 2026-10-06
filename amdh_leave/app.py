"""نقطة تشغيل التطبيق: تهيئة المسارات، القاعدة، الجلسة، ثم النافذة الرئيسية."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from . import config
from .context import AppContext
from .db import Database
from .logging_setup import get_logger, install_excepthook, setup_logging
from .services.backup import BackupService
from .services.security import make_session
from .ui import theme
from .ui.dialogs_admin import LoginDialog
from .ui.main_window import MainWindow


def _single_instance_key(db_path: Path) -> str:
    digest = hashlib.sha1(str(db_path.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"amdh-leave-{digest}"


class SingleInstance:
    """يمنع تشغيل نسختين على نفس قاعدة البيانات (سبب شائع لتلف البيانات)."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.server = None
        self.active = False

    def acquire(self) -> bool:
        try:
            from PyQt6.QtNetwork import QLocalServer, QLocalSocket
        except ImportError:  # pragma: no cover
            return True
        socket = QLocalSocket()
        socket.connectToServer(self.key)
        if socket.waitForConnected(300):
            socket.disconnectFromServer()
            self.active = True
            return False
        self.server = QLocalServer()
        try:
            self.server.removeServer(self.key)
        except Exception:
            pass
        return self.server.listen(self.key)


def _prepare_paths(data_dir: str | None) -> config.Paths:
    paths = config.Paths(Path(data_dir).expanduser().resolve() if data_dir else None)
    paths.ensure()
    # ترحيل قاعدة بيانات قديمة موجودة بجانب البرنامج إلى مجلد البيانات الجديد
    if not paths.db_path.exists():
        for candidate in paths.legacy_db_candidates():
            if candidate.exists():
                try:
                    shutil.copy2(candidate, paths.db_path)
                    get_logger("app").info("نُسخت قاعدة البيانات من %s", candidate)
                except OSError:
                    pass
                break
    return paths


def build_context(paths: config.Paths, app: QApplication) -> AppContext:
    db = Database(paths.db_path, paths.backups_dir)
    backup = BackupService(db, paths.backups_dir)
    settings = QSettings(config.SETTINGS_ORG, config.SETTINGS_APP)
    policy = db.policy(refresh=True)
    session = make_session(None, policy.auth_enabled)
    return AppContext(paths=paths, db=db, backup=backup, session=session, settings=settings)


def _authenticate(ctx: AppContext, parent=None) -> bool:
    """يعيد True إذا سُمح بالدخول."""
    if not ctx.policy.auth_enabled:
        ctx.session = make_session(None, False)
        return True
    dialog = LoginDialog(parent, ctx)
    if dialog.exec() != dialog.DialogCode.Accepted or dialog.user is None:
        return False
    ctx.session = make_session(dialog.user, True)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=config.APP_NAME)
    parser.add_argument("--data-dir", help="مجلد البيانات (افتراضياً مجلد البرنامج)")
    parser.add_argument("--version", action="store_true", help="عرض الإصدار")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.version:
        print(f"{config.APP_NAME} {config.APP_VERSION}")
        return 0

    app = QApplication(sys.argv[:1])
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName(config.APP_ORGANIZATION)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setStyleSheet(theme.stylesheet())

    paths = _prepare_paths(args.data_dir)
    log_file = setup_logging(paths.logs_dir)
    logger = get_logger("app")
    logger.info("بدء التشغيل — البيانات: %s", paths.data_dir)

    def show_error(text: str) -> None:
        QMessageBox.critical(None, "خطأ غير متوقع",
                             text[-1500:] + (f"\n\nملف السجل: {log_file}" if log_file else ""))

    install_excepthook(show_error)

    guard = SingleInstance(_single_instance_key(paths.db_path))
    if not guard.acquire():
        QMessageBox.information(None, "البرنامج يعمل",
                                "هناك نسخة أخرى من البرنامج تعمل على نفس قاعدة البيانات.\n"
                                "أُغلق النسخة الحالية لتجنّب تعارض الكتابة.")
        return 1

    ctx = build_context(paths, app)
    if not _authenticate(ctx):
        ctx.db.close()
        return 2

    theme.set_theme(ctx.ui_get("theme", "dark") or "dark")
    app.setStyleSheet(theme.stylesheet())

    window = MainWindow(ctx)
    window.show()
    try:
        return app.exec()
    finally:
        try:
            ctx.db.close()
        except Exception:  # pragma: no cover
            pass
        logger.info("إغلاق التطبيق")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
