"""نقطة تشغيل التطبيق: تهيئة المسارات، القاعدة، الجلسة، ثم النافذة الرئيسية."""

from __future__ import annotations

import argparse
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
from .ui.dialogs_login import LoginDialog
from .ui.main_window import MainWindow


def _single_instance_path(data_dir: Path) -> Path:
    return Path(data_dir) / ".amdh_instance.lock"


class SingleInstance:
    """قفل ملف على مستوى نظام التشغيل يمنع تشغيل نسختين على نفس البيانات.

    ميزته على البدائل (منفذ Qt أو ملف علامة عادي): يتحرّر **تلقائياً** عند انتهاء
    العملية بأي طريقة (حتى الإنهاء القسري أو انقطاع الكهرباء)، فلا يبقى البرنامج
    محجوباً بعد تعطّل سابق.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.handle = None
        self.acquired = False

    def acquire(self) -> bool:
        import datetime as _dt
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.handle = open(self.path, "a+b")
        except OSError:
            return True                      # لا نمنع التشغيل إن تعذّر القفل
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            return False
        self.acquired = True
        try:
            self.handle.seek(0)
            self.handle.truncate()
            self.handle.write(f"{os.getpid()} {_dt.datetime.now():%Y-%m-%d %H:%M:%S}".encode("utf-8"))
            self.handle.flush()
        except OSError:
            pass
        return True

    def other_instance_info(self) -> str:
        try:
            self.path.parent.joinpath(self.path.name).read_bytes()
            text = self.path.read_text(encoding="utf-8", errors="ignore").strip()
            return text
        except OSError:
            return ""

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            try:
                self.handle.close()
            except OSError:
                pass
            self.handle = None


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


def build_context(paths: config.Paths, app: QApplication, key_hex: str | None = None) -> AppContext:
    db = Database(paths.db_path, paths.backups_dir, key_hex=key_hex)
    backup = BackupService(db, paths.backups_dir)
    settings = QSettings(config.SETTINGS_ORG, config.settings_app_name())
    policy = db.policy(refresh=True)
    session = make_session(None, policy.auth_enabled)
    return AppContext(paths=paths, db=db, backup=backup, session=session, settings=settings)


def _open_encrypted_database(paths: config.Paths, logger) -> str | None:
    """يطلب كلمة مرور القاعدة المشفّرة ويعيد المفتاح (أو None عند الإلغاء)."""
    from .services import crypto
    from .ui.dialogs_security import PasswordDialog

    if not crypto.sqlcipher_available():
        QMessageBox.critical(None, "تشفير قاعدة البيانات",
                             "قاعدة البيانات مشفّرة، لكن حزمة SQLCipher غير مثبتة." +
                             "\n\n" + crypto.install_hint())
        return None
    lock = crypto.read_lock(paths.data_dir) or {}
    if not lock.get("salt"):
        QMessageBox.critical(None, "تشفير قاعدة البيانات",
                             "ملف القفل مفقود — لا يمكن اشتقاق المفتاح. "
                                "استعد نسخة احتياطية غير مشفّرة.")
        return None
    for attempt in range(3):
        dialog = PasswordDialog(None, "فتح قاعدة بيانات مشفّرة",
                                "قاعدة البيانات مشفّرة. أدخل كلمة المرور." + "\n" +
                                f"المحاولات المتبقية: {3 - attempt}")
        if dialog.exec() != dialog.DialogCode.Accepted:
            return None
        password = dialog.password or ""
        if not crypto.check_password(paths.data_dir, password):
            QMessageBox.warning(None, "كلمة المرور", "كلمة المرور غير صحيحة.")
            continue
        iterations = int(lock.get("iterations", crypto.KDF_ITERATIONS))
        logger.info("فُتحت قاعدة بيانات مشفّرة")
        return crypto.derive_key(password, lock["salt"], iterations)
    return None


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
    app.setStyleSheet(theme.stylesheet())

    paths = _prepare_paths(args.data_dir)
    log_file = setup_logging(paths.logs_dir)
    logger = get_logger("app")

    # الشعارات: يُقدَّم مجلد المستخدم على مجلد الحزمة، وأيقونة التطبيق لشريط المهام
    from .ui import assets as ui_assets
    ui_assets.set_user_assets_dir(paths.data_dir / "assets")
    ui_assets.apply_app_icon(app)

    # الواجهة عربية فقط باتجاه من اليمين إلى اليسار
    settings = QSettings(config.SETTINGS_ORG, config.settings_app_name())
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    logger.info("بدء التشغيل — البيانات: %s", paths.data_dir)

    def show_error(text: str) -> None:
        QMessageBox.critical(None, "خطأ غير متوقع",
                             text[-1500:] + (f"\n\n{log_file}" if log_file else ""))

    install_excepthook(show_error)

    guard = SingleInstance(_single_instance_path(paths.data_dir))
    if not guard.acquire():
        running = guard.other_instance_info()
        detail = f"\n\nالنسخة العاملة: {running}" if running else ""
        headless = os.environ.get("QT_QPA_PLATFORM", "").lower() in {"offscreen", "minimal"}
        if headless:
            logger.warning("هناك نسخة أخرى تعمل على نفس البيانات%s", detail)
            return 1
        QMessageBox.information(None, "البرنامج يعمل",
                                "هناك نسخة أخرى من البرنامج تعمل على نفس البيانات." + detail +
                                "\n\n" + "أُغلق النسخة الحالية لتجنّب تعارض الكتابة.")
        return 1

    key_hex: str | None = None
    from .services import crypto as _crypto
    if _crypto.is_encryption_enabled(paths.data_dir) or _crypto.is_encrypted_database(paths.db_path):
        key_hex = _open_encrypted_database(paths, logger)
        if key_hex is None:
            logger.warning("أُلغيت عملية فتح قاعدة بيانات مشفّرة")
            return 3

    ctx = build_context(paths, app, key_hex)
    if not _authenticate(ctx):
        ctx.db.close()
        return 2

    theme.set_theme(ctx.ui_get("theme", "dark") or "dark")
    stored_accent = str(ctx.ui_get("accent", "") or "")
    theme.set_accent(stored_accent or None)
    theme.apply(app)

    window = MainWindow(ctx)
    window.setWindowIcon(ui_assets.app_icon())
    window.show()
    try:
        return app.exec()
    finally:
        guard.release()
        try:
            ctx.db.close()
        except Exception:  # pragma: no cover
            pass
        logger.info("إغلاق التطبيق")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
