"""بطاقة بيانات دخول المؤسسة مع معاينة/طباعة ورقية."""

from __future__ import annotations

import html
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPageSize, QTextDocument
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout,
)

from .. import config
from ..services import dates as D
from . import theme, widgets as W
from .dialogs_base import BaseDialog

try:
    from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog
    HAS_PRINT = True
except ImportError:                                   # pragma: no cover
    HAS_PRINT = False


def credentials_html(institution: str, code: str, username: str, password: str,
                     role_label: str) -> str:
    """صفحة A4 عربية جاهزة للطباعة (بيانات الدخول والتعليمات)."""
    esc = html.escape
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar"><head><meta charset="utf-8">
<style>
@page {{ size: A4; margin: 18mm 16mm; }}
body {{ font-family: 'Segoe UI', Tahoma, Arial; color: #111; font-size: 12pt; }}
h1 {{ color: #0f766e; font-size: 20pt; margin: 0 0 4px; }}
.sub {{ color: #475569; margin-bottom: 14px; }}
table {{ width: 100%; border-collapse: collapse; margin: 10px 0 16px; }}
th, td {{ border: 1px solid #94a3b8; padding: 8px 10px; text-align: right; }}
th {{ background: #e2e8f0; width: 28%; }}
.pass {{ font-family: Consolas, monospace; font-size: 16pt; direction: ltr;
         text-align: center; letter-spacing: 1px; }}
.box {{ border: 1px solid #94a3b8; padding: 10px 14px; margin: 12px 0; }}
.warn {{ background: #fff7ed; border-color: #fb923c; }}
.sign {{ display: flex; justify-content: space-between; margin-top: 46px; }}
.sign div {{ width: 42%; border-top: 1px solid #111; padding-top: 6px; text-align: center; }}
.footer {{ margin-top: 24px; color: #64748b; font-size: 9pt; }}
</style></head><body>
<h1>بطاقة بيانات دخول المؤسسة</h1>
<div class="sub">{esc(config.APP_NAME)} — الإصدار {esc(config.APP_VERSION)}</div>
<table>
<tr><th>المؤسسة</th><td>{esc(institution)}</td></tr>
<tr><th>الرمز</th><td>{esc(code or '—')}</td></tr>
<tr><th>اسم المستخدم</th><td class="pass">{esc(username)}</td></tr>
<tr><th>كلمة المرور</th><td class="pass">{esc(password)}</td></tr>
<tr><th>نوع الحساب</th><td>{esc(role_label)}</td></tr>
<tr><th>تاريخ التسليم</th><td>{datetime.now():%Y-%m-%d}</td></tr>
</table>
<div class="box">
<strong>تعليمات الاستخدام:</strong>
<ol>
<li>شغّل برنامج «{esc(config.APP_NAME)}» على جهاز المؤسسة.</li>
<li>أدخل اسم المستخدم وكلمة المرور أعلاه.</li>
<li>الحساب مقيَّد بموظفي مؤسستك فقط، ويمكنك إدخال الإجازات وتصدير بيانات المؤسسة للمركز.</li>
<li>لا تشارك كلمة المرور، واحفظ هذه البطاقة في مكان آمن.</li>
<li>عند نهاية الشهر: «تصدير للمركز» ← أرسل الملف إلى مركز الدائرة.</li>
</ol>
</div>
<div class="box warn">
<strong>تنبيه:</strong> كلمة المرور لا تُعرض مرة أخرى بعد إغلاق هذه النافذة.
إذا فُقدت، يلزم أن يعيد مدير المركز تعيينها.
</div>
<div class="sign"><div>تسليم (مدير المركز)</div><div>استلام (موظف المؤسسة)</div></div>
<div class="footer">{esc(config.APP_NAME)} — {esc(config.APP_DEVELOPER)} · {esc(config.APP_PHONE)}</div>
</body></html>"""


class CredentialsDialog(BaseDialog):
    """عرض بيانات الدخول مرة واحدة مع معاينة وطباعة وحفظ PDF."""

    def __init__(self, parent, ctx, *, institution: str, code: str = "", username: str = "",
                 password: str = "", role_label: str = "مدخل بيانات") -> None:
        super().__init__(parent, ctx, "بيانات دخول المؤسسة")
        self.institution = institution
        self.code = code
        self.username = username
        self.password = password
        self.role_label = role_label
        self.setMinimumSize(640, 560)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.addWidget(W.title_label("🔑 بيانات دخول المؤسسة", 15))
        layout.addWidget(W.muted_label(
            "اعرضها مرة واحدة، واطبعها ورقياً وسلّمها لموظف المؤسسة. "
            "لن تُعرض كلمة المرور مرة أخرى بعد الإغلاق."))

        card = W.card()
        form = QFormLayout(card)
        self.e_inst = QLineEdit(self.institution)
        self.e_inst.setReadOnly(True)
        self.e_code = QLineEdit(self.code)
        self.e_code.setReadOnly(True)
        self.e_user = QLineEdit(self.username)
        self.e_user.setReadOnly(True)
        self.e_user.setStyleSheet("font-family: Consolas, monospace;")
        self.e_pass = QLineEdit(self.password)
        self.e_pass.setReadOnly(True)
        self.e_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_pass.setStyleSheet("font-family: Consolas, monospace;")
        self.btn_show = W.button("👁 إظهار", "Ghost", self._toggle, width=100)
        form.addRow("المؤسسة", self.e_inst)
        form.addRow("الرمز", self.e_code)
        form.addRow("اسم المستخدم", self.e_user)
        pass_row = QHBoxLayout()
        pass_row.addWidget(self.e_pass, 1)
        pass_row.addWidget(self.btn_show)
        form.addRow("كلمة المرور", pass_row)
        layout.addWidget(card)

        instructions = W.muted_label(
            "تعليمات: شغّل البرنامج، أدخل اسم المستخدم وكلمة المرور، ثم يمكنك إدخال "
            "موظفي مؤسستك وإجازاتهم. الحساب مقيَّد بمؤسستك فقط. "
            "عند نهاية الشهر استخدم «تصدير للمركز».")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        layout.addStretch()

        buttons = QHBoxLayout()
        self.btn_print = W.button("🖨 طباعة/معاينة", "Accent", self._print, width=170)
        self.btn_print.setEnabled(HAS_PRINT)
        buttons.addWidget(self.btn_print)
        buttons.addWidget(W.button("📄 حفظ PDF", "Gold", self._pdf, width=130))
        buttons.addWidget(W.button("📋 نسخ البيانات", "Ghost", self._copy, width=150))
        buttons.addStretch()
        buttons.addWidget(W.button("إغلاق", "Ghost", self.accept, width=90))
        layout.addLayout(buttons)
        if not HAS_PRINT:
            layout.addWidget(W.muted_label("الطباعة غير متاحة في هذه البيئة."))

    def _toggle(self) -> None:
        shown = self.e_pass.echoMode() == QLineEdit.EchoMode.Password
        self.e_pass.setEchoMode(QLineEdit.EchoMode.Normal if shown
                                else QLineEdit.EchoMode.Password)
        self.btn_show.setText("🙈 إخفاء" if shown else "👁 إظهار")

    def _document(self) -> QTextDocument:
        document = QTextDocument()
        document.setHtml(credentials_html(self.institution, self.code, self.username,
                                          self.password, self.role_label))
        return document

    def _print(self) -> None:
        if not HAS_PRINT:
            W.error(self, "طباعة Qt غير متاحة.")
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        document = self._document()
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("معاينة بطاقة بيانات الدخول")
        preview.paintRequested.connect(document.print)
        preview.exec()

    def _pdf(self) -> None:
        if not HAS_PRINT:
            W.error(self, "توليد PDF غير متاح في هذه البيئة.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "حفظ بطاقة بيانات الدخول",
            str(self.ctx.paths.reports_dir / f"بيانات_دخول_{self.username}.pdf"), "PDF (*.pdf)")
        if not path:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        self._document().print(printer)
        W.info(self, f"تم حفظ الملف:\n{path}")

    def _copy(self) -> None:
        QApplication.clipboard().setText(
            f"المؤسسة: {self.institution}\nاسم المستخدم: {self.username}\n"
            f"كلمة المرور: {self.password}\n")
        W.info(self, "تم نسخ بيانات الدخول إلى الحافظة.")
