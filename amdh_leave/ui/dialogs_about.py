"""نافذة «حول» الجديدة: معلومات البرنامج، المطوّر (مع صورته)، وبيئة النظام."""

from __future__ import annotations

import platform
import sqlite3
import sys

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget,
)

from .. import config, i18n
from ..i18n import tr, trf
from ..logging_setup import log_path
from . import assets, theme, widgets as W
from .dialogs_base import BaseDialog

FEATURES = [
    "احتساب الرصيد التراكمي: يوم إجازة لكل 10 أيام دوام (قابل للتعديل)",
    "ضوابط لكل نوع إجازة: يخصم من الرصيد؟ يُستبعد من الخدمة؟ سقف؟ يتطلب أمراً؟",
    "كشف حساب سنوي بالترحيل والصلاحية + تصفية نهاية الخدمة",
    "الرصيد السالب مسموح حسب الضوابط الإدارية ولا يُمنع",
    "حذف ناعم وسلة محذوفات + سجل تدقيق كامل",
    "نسخ احتياطي بدوران واستعادة وفحص سلامة وضغط القاعدة",
    "تقارير Excel (RTL) وPDF بالعربية وصفحات طباعة HTML",
    "لوحة مؤشرات، تقويم إجازات، مركز تنبيهات، مرفقات، ومستخدمون بأدوار",
    "تعدد اللغات (عربية/كردية/إنجليزية) و5 ثيمات",
    "مشاركة التقارير عبر البريد الإلكتروني وتلغرام",
    "تشفير قاعدة البيانات عبر SQLCipher (اختياري)",
    "إشعارات سطح المكتب (Tray) مع فحص دوري",
]


class AboutDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, tr("حول النظام"))
        self.setMinimumSize(700, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self._header())

        tabs = QTabWidget()
        tabs.addTab(self._tab_program(), tr("البرنامج"))
        tabs.addTab(self._tab_developer(), tr("المطوّر"))
        tabs.addTab(self._tab_system(), tr("النظام"))
        layout.addWidget(tabs, 1)
        layout.addLayout(self.buttons_row(self.close_button()))

    # ------------------------------------------------------------------
    def _header(self) -> QWidget:
        holder = QFrame()
        holder.setObjectName("Card")
        row = QHBoxLayout(holder)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(14)

        logo = QLabel()
        logo.setFixedSize(88, 88)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = assets.logo(88)
        if pixmap is not None:
            logo.setPixmap(pixmap)
        row.addWidget(logo)

        texts = QVBoxLayout()
        name = QLabel(config.APP_NAME)
        name.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        name.setStyleSheet(theme.label_style("accent", 16, bold=True))
        version = W.muted_label(f"{tr('الإصدار')} {config.APP_VERSION} — {config.APP_RELEASE}")
        developer = W.muted_label(config.APP_DEVELOPER)
        texts.addWidget(name)
        texts.addWidget(version)
        texts.addWidget(developer)
        texts.addStretch()
        row.addLayout(texts, 1)

        department = QLabel()
        department.setFixedSize(72, 72)
        department.setAlignment(Qt.AlignmentFlag.AlignCenter)
        department_pixmap = assets.department_logo(72)
        if department_pixmap is not None:
            department.setPixmap(department_pixmap)
        row.addWidget(department)
        return holder

    # ------------------------------------------------------------------
    def _tab_program(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        description = QLabel(tr(
            "نظام مكتبي لإدارة الإجازات التراكمية لموظفي الدوائر والمؤسسات، يعمل محلياً "
            "بقاعدة بيانات SQLite بلا حاجة إلى إنترنت، مع تقارير جاهزة للطباعة والتصدير."))
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addWidget(W.separator())

        title = QLabel(tr("أبرز الميزات"))
        title.setStyleSheet(theme.label_style("accent", 12, bold=True))
        layout.addWidget(title)

        features = QTextEdit()
        features.setReadOnly(True)
        features.setHtml("<ul>" + "".join(f"<li>{f}</li>" for f in FEATURES) + "</ul>")
        layout.addWidget(features, 1)

        note = W.muted_label(tr(
            "ملاحظة ضوابطية: الرصيد السالب مشروع حسب الضوابط الإدارية المعتمدة، "
            "ولا يمنعه النظام ولا يعتبره خطأً."))
        note.setWordWrap(True)
        layout.addWidget(note)
        return page

    def _tab_developer(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setSpacing(16)

        photo = QLabel()
        photo.setFixedSize(240, 300)
        photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        photo.setStyleSheet(f"border: 1px solid {theme.color('border')}; border-radius: 8px;")
        pixmap = assets.developer_photo(240, 300)
        if pixmap is not None:
            photo.setPixmap(pixmap)
        layout.addWidget(photo, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        name = QLabel(config.APP_DEVELOPER)
        name.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        name.setStyleSheet(theme.label_style("accent", 14, bold=True))
        info.addWidget(name)
        info.addWidget(W.muted_label(tr("تصميم وبرمجة وتطوير النظام")))
        info.addWidget(W.separator())

        rows = [
            (tr("الهاتف"), config.APP_PHONE),
            (tr("البريد الإلكتروني"), config.APP_EMAIL),
            (tr("المشروع"), config.APP_NAME),
            (tr("الإصدار"), f"{config.APP_VERSION} ({config.APP_RELEASE})"),
        ]
        for label, value in rows:
            row = QHBoxLayout()
            key = W.muted_label(f"{label}:")
            key.setFixedWidth(120)
            row.addWidget(key)
            row.addWidget(QLabel(value))
            row.addStretch()
            info.addLayout(row)

        info.addWidget(W.separator())
        hint = W.muted_label(tr(
            "يمكنك استبدال صورة المطوّر وشعار البرنامج وشعار الدائرة بصورك: "
            "ضع الملفات في مجلد assets داخل مجلد البيانات (راجع assets/README.md)."))
        hint.setWordWrap(True)
        info.addWidget(hint)
        info.addStretch()

        buttons = QHBoxLayout()
        buttons.addWidget(W.button(tr("📂 فتح مجلد الصور"), "Ghost", self._open_assets))
        buttons.addWidget(W.button(f"✉️ {tr('مراسلة')}", "Ghost", self._send_email))
        buttons.addStretch()
        info.addLayout(buttons)

        layout.addLayout(info, 1)
        return page

    def _tab_system(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        stats = self.ctx.db.stats() if self.ctx else {}
        size_kb = stats.get("size_bytes", 0) / 1024
        rows = [
            (tr("إصدار البرنامج"), f"{config.APP_VERSION} ({config.APP_RELEASE})"),
            (tr("بايثون"), sys.version.split()[0]),
            (tr("PyQt6"), self._qt_version()),
            (tr("SQLite"), sqlite3.sqlite_version),
            (tr("نظام التشغيل"), f"{platform.system()} {platform.release()}"),
            (tr("وضع العرض"), theme.current()),
            (tr("اللغة"), i18n.language_label()),
            (tr("مجلد البيانات"), str(self.ctx.paths.data_dir) if self.ctx else "—"),
            (tr("قاعدة البيانات"), f"{stats.get('path', '—')} ({size_kb:,.0f} KB)"),
            (tr("إصدار المخطط"), str(stats.get("schema_version", "—"))),
            (tr("الموظفون"), str(stats.get("employees", "—"))),
            (tr("الإجازات"), str(stats.get("leaves", "—"))),
            (tr("ملف السجل"), str(log_path() or "—")),
        ]
        grid = QGridLayout()
        for index, (label, value) in enumerate(rows):
            key = W.muted_label(f"{label}:")
            grid.addWidget(key, index, 0, Qt.AlignmentFlag.AlignTop)
            text = QLabel(str(value))
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(text, index, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.addWidget(W.button(tr("📋 نسخ معلومات النظام"), "Blue", self._copy_info))
        buttons.addWidget(W.button(tr("📂 فتح مجلد البيانات"), "Ghost", self._open_data))
        buttons.addWidget(W.button(tr("📄 فتح ملف السجل"), "Ghost", self._open_log))
        buttons.addStretch()
        layout.addLayout(buttons)
        return page

    # ------------------------------------------------------------------
    @staticmethod
    def _qt_version() -> str:
        from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
        return f"Qt {QT_VERSION_STR} / PyQt {PYQT_VERSION_STR}"

    def _system_summary(self) -> str:
        stats = self.ctx.db.stats() if self.ctx else {}
        lines = [
            f"{config.APP_NAME} — {tr('الإصدار')} {config.APP_VERSION} ({config.APP_RELEASE})",
            f"{tr('المطوّر')}: {config.APP_DEVELOPER} | {config.APP_PHONE} | {config.APP_EMAIL}",
            f"{tr('بايثون')}: {sys.version.split()[0]} | {self._qt_version()} | "
            f"SQLite {sqlite3.sqlite_version}",
            f"{tr('نظام التشغيل')}: {platform.system()} {platform.release()}",
            f"{tr('مجلد البيانات')}: {self.ctx.paths.data_dir if self.ctx else '—'}",
            f"{tr('الموظفون')}: {stats.get('employees', '—')} | "
            f"{tr('الإجازات')}: {stats.get('leaves', '—')}",
        ]
        return "\n".join(lines)

    def _copy_info(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._system_summary())
            W.info(self, tr("تم نسخ معلومات النظام إلى الحافظة."), tr("حول النظام"))

    def _assets_dir(self):
        base = self.ctx.paths.data_dir / "assets" if self.ctx else assets.PACKAGE_ASSETS
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _open_assets(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._assets_dir())))

    def _open_data(self) -> None:
        if self.ctx:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.paths.data_dir)))

    def _open_log(self) -> None:
        path = log_path()
        if path and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            W.warn(self, tr("ملف السجل غير متاح."))

    def _send_email(self) -> None:
        QDesktopServices.openUrl(QUrl(f"mailto:{config.APP_EMAIL}?subject={config.APP_NAME}"))
