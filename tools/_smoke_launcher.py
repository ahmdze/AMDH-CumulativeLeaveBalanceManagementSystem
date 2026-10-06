"""فحص مسار التشغيل الكامل (leave_system_deep.py → amdh_leave.app.main)."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(r"G:\Download\AMDH-Calculator")
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="amdh_launch_"))
shutil.copy2(ROOT / "employees_leave.db", TMP / "employees_leave.db")

from PyQt6.QtCore import QTimer                                  # noqa: E402
from PyQt6.QtWidgets import QApplication                         # noqa: E402

from amdh_leave import app as app_module                         # noqa: E402
from amdh_leave.ui import main_window as mw                      # noqa: E402

original_show = mw.MainWindow.show
state = {"shown": False}


def show_and_quit(self):
    original_show(self)
    state["shown"] = True
    state["rows"] = self.table.table.rowCount()
    state["balance"] = self.rows[0][13] if self.rows else None
    QTimer.singleShot(400, QApplication.instance().quit)


mw.MainWindow.show = show_and_quit

code = app_module.main(["--data-dir", str(TMP)])
print("main() returned:", code)
print("window shown:", state.get("shown"), "| rows:", state.get("rows"),
      "| balance:", state.get("balance"))
log = TMP / "logs" / "app.log"
print("log exists:", log.exists())
if log.exists():
    text = log.read_text(encoding="utf-8", errors="ignore")
    print("log lines:", len(text.splitlines()))
    for line in text.splitlines():
        if "ERROR" in line or "Traceback" in line:
            print("LOG-ERROR:", line)
print("TMP:", TMP)
ok = code == 0 and state.get("shown") and state.get("rows") == 1
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
