# -*- mode: python ; coding: utf-8 -*-
"""ملف بناء PyInstaller لنظام إدارة الإجازات التراكمية.

البناء:
    pyinstaller AMDH-Leave.spec --noconfirm
الناتج:
    dist/AMDH-Leave/AMDH-Leave.exe
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

block_cipher = None
ROOT = Path(SPECPATH)

hidden = [
    "openpyxl", "openpyxl.styles", "openpyxl.utils",
    "reportlab", "reportlab.pdfbase", "reportlab.pdfbase.ttfonts",
    "reportlab.platypus", "reportlab.lib",
    "arabic_reshaper", "bidi", "bidi.algorithm",
    "PyQt6.QtNetwork",
    "PyQt6.QtPrintSupport",
    "sqlcipher3", "sqlcipher3.dbapi2",
]

# الصور (الشعارات) تُضمَّن داخل الحزمة
datas = [
    (str(ROOT / "amdh_leave" / "assets"), "amdh_leave/assets"),
]

a = Analysis(
    ["leave_system_deep.py"],
    pathex=[str(ROOT)],
    binaries=collect_dynamic_libs("sqlcipher3"),
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PIL", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AMDH-Leave",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # بلا نافذة سوداء (السجلات تُكتب في logs/app.log)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AMDH-Leave",
)
