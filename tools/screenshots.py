"""توليد لقطات شاشة للواجهة بكل ثيم (للتحقق البصري والتوثيق).

الاستخدام:
    python tools/screenshots.py                 # كل الثيمات + النوافذ الرئيسية
    python tools/screenshots.py --theme dark    # ثيم واحد
الناتج:
    screenshots/<theme>_main.png و <theme>_login.png و <theme>_about.png
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QSettings, Qt, QTimer                 # noqa: E402
from PyQt6.QtWidgets import QApplication                       # noqa: E402

from amdh_leave import config                                 # noqa: E402
from amdh_leave.context import AppContext                      # noqa: E402
from amdh_leave.db import Database                             # noqa: E402
from amdh_leave.services.backup import BackupService           # noqa: E402
from amdh_leave.services.security import make_session          # noqa: E402
from amdh_leave.ui import dialogs_about, dialogs_base, dialogs_login, theme  # noqa: E402
from amdh_leave.ui import dialogs_import, dialogs_institutions           # noqa: E402
from amdh_leave.ui.main_window import MainWindow               # noqa: E402

OUT = ROOT / "screenshots"


def build_context(tmp: Path) -> AppContext:
    shutil.copy2(ROOT / "employees_leave.db", tmp / "employees_leave.db")
    paths = config.Paths(tmp).ensure()
    db = Database(paths.db_path, paths.backups_dir)
    db.set_meta({"auth_enabled": "0"})
    # مؤسسات للعرض في اللقطات إن لم تكن مسجّلة
    for name, code, kind in (("مركز الدائرة", "C0", "مركز الدائرة"),
                             ("مستشفى الكرامة", "H1", "مستشفى"),
                             ("مستشفى النور", "H2", "مستشفى"),
                             ("مركز صحي الرافدين", "PH3", "مركز صحي")):
        if db.get_institution(name) is None:
            db.save_institution({"name": name, "code": code, "kind": kind,
                                 "manager": "د. " + name.split()[-1]}, "admin")
    db.set_institution_import("مستشفى الكرامة", when="2026-10-02 09:15:00", user="h1",
                              filename="نقل_مستشفى_الكرامة.amdhz", counts="{}")
    return AppContext(paths=paths, db=db, backup=BackupService(db, paths.backups_dir),
                      session=make_session(None, False),
                      settings=QSettings("MyCompany", "AMDH-Screenshots"))


def grab(widget, path: Path) -> None:
    widget.resize(widget.size().expandedTo(widget.minimumSize()))
    QApplication.processEvents()
    pixmap = widget.grab()
    path.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(path), "PNG")
    print(f"  {path.relative_to(ROOT)} ({pixmap.width()}×{pixmap.height()})")


def main() -> int:
    parser = argparse.ArgumentParser(description="لقطات الواجهة لكل ثيم")
    parser.add_argument("--theme", help="ثيم واحد فقط")
    args = parser.parse_args()

    app = QApplication(sys.argv[:1])
    tmp = Path(tempfile.mkdtemp(prefix="amdh_shots_"))
    ctx = build_context(tmp)

    themes = [args.theme] if args.theme else [key for key, _l, _m in config.THEMES]
    for key in themes:
        # النافذة الرئيسية تستعيد الثيم من الإعدادات، لذا نضبط الإعداد نفسه
        ctx.ui_set("theme", key)
        ctx.ui_set("accent", "")
        theme.set_theme(key)
        theme.set_accent(None)
        theme.apply(app)
        print(f"[{key}]")
        window = MainWindow(ctx)
        window.resize(1400, 860)
        window.show()
        QApplication.processEvents()
        window._refresh()
        window.table.table.setCurrentCell(0, 0)
        window._on_selection()
        QApplication.processEvents()
        grab(window, OUT / f"{key}_main.png")

        login = dialogs_login.LoginDialog(window, ctx)
        login.show()
        QApplication.processEvents()
        grab(login, OUT / f"{key}_login.png")
        login.close()

        about = dialogs_about.AboutDialog(window, ctx)
        about.show()
        QApplication.processEvents()
        grab(about, OUT / f"{key}_about.png")
        about.close()

        settings = dialogs_base.SettingsDialog(window, ctx)
        settings.show()
        QApplication.processEvents()
        grab(settings, OUT / f"{key}_settings.png")
        settings.close()

        institutions = dialogs_institutions.InstitutionsDialog(window, ctx)
        institutions.show()
        QApplication.processEvents()
        grab(institutions, OUT / f"{key}_institutions.png")
        institutions.close()

        transfer = dialogs_import.TransferImportDialog(window, ctx)
        transfer.show()
        QApplication.processEvents()
        grab(transfer, OUT / f"{key}_import.png")
        transfer.close()
        window.close()

    # صورة إضافية: الثيم الداكن بلون مميز مخصّص
    ctx.ui_set("theme", "dark")
    ctx.ui_set("accent", "#8B5CF6")
    theme.set_theme("dark")
    theme.set_accent("#8B5CF6")
    theme.apply(app)
    window = MainWindow(ctx)
    window.resize(1400, 860)
    window.show()
    window._refresh()
    window.table.table.setCurrentCell(0, 0)
    window._on_selection()
    QApplication.processEvents()
    grab(window, OUT / "custom_accent_main.png")
    window.close()
    theme.set_accent(None)

    ctx.db.close()
    QTimer.singleShot(50, app.quit)
    app.exec()
    print(f"\nالمجلد: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
