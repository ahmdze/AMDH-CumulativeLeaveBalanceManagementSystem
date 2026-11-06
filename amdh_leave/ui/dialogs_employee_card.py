"""بطاقة الموظف: عرض وطباعة بطاقة تحتوي على بيانات الموظف ورصيده.

تدعم:
  - عرض معاينة للبطاقة بحجم A5.
  - تصدير إلى PDF للطباعة.
  - معلومات شاملة: الاسم، الرقم الوظيفي، المؤسسة، تاريخ التعيين،
    الرصيد الحالي، والإجازات المستخدمة.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
from PyQt6.QtGui import QPageSize, QPageLayout, QTextDocument

from PyQt6.QtCore import QSizeF, QMarginsF

from .. import config
from ..models import Employee
from ..rules import Policy
from ..services import balance as B
from ..services import dates as D
from . import theme, widgets as W
from .dialogs_base import BaseDialog


class EmployeeCardDialog(BaseDialog):
    """حوار بطاقة الموظف: معاينة + تصدير PDF."""

    def __init__(self, employee: Employee, policy: Policy, parent=None, ctx=None):
        super().__init__(parent, ctx, f"بطاقة الموظف: {employee.name}")
        self.employee = employee
        self.policy = policy
        self.resize(460, 560)
        layout = QVBoxLayout(self)

        # معاينة البطاقة
        self.card_widget = self._build_card()
        card_container = QWidget()
        card_layout = QVBoxLayout(card_container)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.card_widget)
        layout.addWidget(card_container)

        # أزرار الإجراءات
        row = QHBoxLayout()
        row.addWidget(W.button("🖨 طباعة", "Accent", self._print_card))
        row.addWidget(W.button("📄 تصدير PDF", "Ghost", self._export_pdf))
        row.addStretch()
        row.addWidget(self.close_button())
        layout.addLayout(row)

    def _build_card(self) -> QWidget:
        """بناء معاينة البطاقة — تصميم عالي التباين للطباعة بالأبيض والأسود."""
        # ألوان ثابتة عالية التباين: أسود على أبيض مع حدود رمادية داكنة
        BLACK = "#000000"
        WHITE = "#FFFFFF"
        LIGHT_GRAY = "#E0E0E0"
        DARK_GRAY = "#333333"
        BORDER_GRAY = "#666666"

        card = QWidget()
        # حجم A5: 148mm × 210mm ≈ 559×794 pixels عند 96 DPI
        # نستخدم حجم أكبر مع هوامش مناسبة لملء الصفحة
        card.setFixedSize(420, 580)
        card.setStyleSheet(f"""
            QWidget {{
                background: {WHITE};
                border: 2px solid {BLACK};
                border-radius: 4px;
                padding: 12px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        # الهيدر
        header = QLabel(config.APP_NAME)
        header.setObjectName("card_header")
        header.setStyleSheet(f"""
            QLabel#card_header {{
                font-size: 14px;
                font-weight: bold;
                color: {BLACK};
                padding: 8px;
                border: 2px solid {BLACK};
                border-radius: 4px;
                background: {LIGHT_GRAY};
            }}
        """)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        # عنوان البطاقة
        title = QLabel("بطاقة الموظف")
        title.setObjectName("card_title")
        title.setStyleSheet(f"""
            QLabel#card_title {{
                font-size: 16px;
                font-weight: bold;
                color: {BLACK};
                padding: 6px;
            }}
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # فاصل
        separator = QWidget()
        separator.setFixedHeight(3)
        separator.setStyleSheet(f"background: {BLACK}")
        layout.addWidget(separator)

        # بيانات الموظف
        bal = B.compute_balance(self.employee, self.employee.leaves, self.policy)
        active_leaves = [lv for lv in self.employee.leaves if not lv.is_deleted]

        info_layout = QGridLayout()
        info_layout.setSpacing(6)

        fields = [
            ("الاسم", self.employee.name),
            ("الرقم الوظيفي", self.employee.emp_id),
            ("العنوان الوظيفي", self.employee.job_title or "—"),
            ("المؤسسة", self.employee.institution or "—"),
            ("مكان العمل", self.employee.workplace or "—"),
            ("تاريخ التعيين", D.to_iso(self.employee.start_date) if self.employee.start_date else "—"),
            ("الجنس", self.employee.gender),
        ]
        for i, (label_text, value) in enumerate(fields):
            # التسمية على اليمين — محاذاة RTL
            lbl_label = QLabel(label_text)
            lbl_label.setObjectName(f"info_label_{i}")
            lbl_label.setStyleSheet(f"""
                QLabel#info_label_{i} {{
                    font-size: 12px;
                    font-weight: bold;
                    color: {BLACK};
                    padding: 4px;
                    background: {LIGHT_GRAY};
                    border: 1px solid {BORDER_GRAY};
                    border-radius: 2px;
                }}
            """)
            lbl_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignLeft)
            lbl_label.setMinimumHeight(28)
            info_layout.addWidget(lbl_label, i, 0)

            # القيمة على اليسار
            lbl_value = QLabel(str(value))
            lbl_value.setObjectName(f"info_value_{i}")
            lbl_value.setStyleSheet(f"""
                QLabel#info_value_{i} {{
                    font-size: 12px;
                    color: {BLACK};
                    padding: 4px;
                    border: 1px solid {BORDER_GRAY};
                    border-radius: 2px;
                }}
            """)
            lbl_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignLeft)
            lbl_value.setMinimumHeight(28)
            info_layout.addWidget(lbl_value, i, 1)

        layout.addLayout(info_layout)

        # الرصيد
        balance_box = QWidget()
        balance_layout = QVBoxLayout(balance_box)
        balance_layout.setSpacing(6)
        balance_box.setObjectName("balance_box")
        balance_box.setStyleSheet(f"""
            QWidget#balance_box {{
                background: {WHITE};
                border: 2px solid {BLACK};
                border-radius: 4px;
                padding: 10px;
            }}
        """)
        balance_title = QLabel("الرصيد الحالي")
        balance_title.setObjectName("balance_title")
        balance_title.setStyleSheet(f"""
            QLabel#balance_title {{
                font-size: 14px;
                font-weight: bold;
                color: {BLACK};
                padding: 6px;
                border: 2px solid {BLACK};
                border-radius: 4px;
                background: {LIGHT_GRAY};
            }}
        """)
        balance_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        balance_layout.addWidget(balance_title)

        balance_info = [
            ("أيام الخدمة", f"{bal.raw_days} يوم"),
            ("الدوام المحسوبة", f"{bal.net_days} يوم"),
            ("المستحقة", f"{bal.earned} يوم"),
            ("المأخوذة", f"{bal.taken} يوم"),
            ("الرصيد", f"{bal.balance} يوم"),
        ]
        bal_form = QGridLayout()
        bal_form.setSpacing(5)
        for i, (label_text, value) in enumerate(balance_info):
            lbl_label = QLabel(label_text)
            lbl_label.setObjectName(f"bal_label_{i}")
            lbl_label.setStyleSheet(f"""
                QLabel#bal_label_{i} {{
                    font-size: 11px;
                    font-weight: bold;
                    color: {BLACK};
                    padding: 3px;
                    background: {LIGHT_GRAY};
                    border: 1px solid {BORDER_GRAY};
                    border-radius: 2px;
                }}
            """)
            lbl_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignLeft)
            lbl_label.setMinimumHeight(24)
            bal_form.addWidget(lbl_label, i, 0)

            lbl_value = QLabel(str(value))
            lbl_value.setObjectName(f"bal_value_{i}")
            lbl_value.setStyleSheet(f"""
                QLabel#bal_value_{i} {{
                    font-size: 11px;
                    color: {BLACK};
                    padding: 3px;
                    border: 1px solid {BORDER_GRAY};
                    border-radius: 2px;
                }}
            """)
            lbl_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignLeft)
            lbl_value.setMinimumHeight(24)
            bal_form.addWidget(lbl_value, i, 1)
        balance_layout.addLayout(bal_form)
        layout.addWidget(balance_box)

        # الإجازات المستخدمة
        used_label = QLabel(f"الإجازات المسجلة: {len(active_leaves)}")
        used_label.setObjectName("used_label")
        used_label.setStyleSheet(f"""
            QLabel#used_label {{
                font-size: 11px;
                color: {DARK_GRAY};
                padding: 6px;
                border: 1px solid {BORDER_GRAY};
                border-radius: 4px;
            }}
        """)
        used_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(used_label)

        # التذييل
        footer = QLabel(f"تاريخ الإصدار: {D.to_iso(date.today())}")
        footer.setObjectName("card_footer")
        footer.setStyleSheet(f"""
            QLabel#card_footer {{
                font-size: 10px;
                color: {DARK_GRAY};
                padding: 4px;
            }}
        """)
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)

        layout.addStretch()
        return card

    def _build_card_html(self) -> str:
        """بناء البطاقة كـ HTML بوضع LTR هندسي (عكس الخلايا يدوياً) لتجاوز أخطاء الطابعات."""
        bal = B.compute_balance(self.employee, self.employee.leaves, self.policy)
        active_leaves = [lv for lv in self.employee.leaves if not lv.is_deleted]
        today = D.to_iso(date.today())

        info_rows = [
            ("الاسم", self.employee.name),
            ("الرقم الوظيفي", str(self.employee.emp_id)),
            ("العنوان الوظيفي", self.employee.job_title or "—"),
            ("المؤسسة", self.employee.institution or "—"),
            ("مكان العمل", self.employee.workplace or "—"),
            ("تاريخ التعيين", D.to_iso(self.employee.start_date) if self.employee.start_date else "—"),
            ("الجنس", self.employee.gender),
        ]

        balance_rows = [
            ("أيام الخدمة", bal.raw_days),
            ("الدوام المحسوبة", bal.net_days),
            ("المستحقة", bal.earned),
            ("المأخوذة", bal.taken),
            ("الرصيد", bal.balance),
        ]

        # 1. بناء صفوف بيانات الموظف
        # نعكس ترتيب الخلايا برمجياً: نضع القيمة (يساراً) ثم العنوان (يميناً)
        info_html = ""
        for label, value in info_rows:
            info_html += f"""
            <tr>
                <td width="65%" style="padding:4px; border:1px solid #333333; text-align:right;">{value}</td>
                <td width="35%" style="background-color:#E0E0E0; font-weight:bold; padding:4px; border:1px solid #333333; text-align:right;">{label}</td>
            </tr>"""

        # 2. بناء صفوف الرصيد
        balance_html = ""
        for label, val in balance_rows:
            balance_html += f"""
            <tr>
                <td width="65%" style="padding:4px; border:1px solid #333333; text-align:right;">
                    <!-- جدول لترتيب (الرقم يميناً وكلمة يوم يساراً) داخل خلية القيمة -->
                    <table border="0" cellpadding="0" cellspacing="0" align="right">
                        <tr>
                            <td style="padding-right:12px; font-family:'Arial';">يوم</td>
                            <td style="font-family:'Arial';">{val}</td>
                        </tr>
                    </table>
                </td>
                <td width="35%" style="background-color:#E0E0E0; font-weight:bold; padding:4px; border:1px solid #333333; text-align:right;">{label}</td>
            </tr>"""

        return f"""
        <!DOCTYPE html>
        <!-- نستخدم ltr قسرياً لأن محرك الطابعة يتجاهل rtl ويعكس الأعمدة -->
        <html dir="ltr" lang="ar">
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: 'Arial', 'Tahoma', sans-serif;
                    font-size: 11pt;
                    color: #000000;
                    margin: 0;
                    padding: 0;
                    direction: ltr;
                }}
                table {{
                    border-collapse: collapse;
                }}
                .header-title {{
                    background-color: #E0E0E0;
                    font-size: 14pt;
                    font-weight: bold;
                    text-align: center;
                    padding: 6px;
                    border: 2px solid #000000;
                }}
                .main-title {{
                    font-size: 12pt;
                    font-weight: bold;
                    text-align: center;
                    padding: 6px;
                }}
                .section-header {{
                    background-color: #E0E0E0;
                    font-size: 11pt;
                    font-weight: bold;
                    text-align: center;
                    padding: 6px;
                }}
                .summary-box {{
                    text-align: center;
                    font-size: 10pt;
                    border: 1px solid #666666;
                    padding: 5px;
                }}
            </style>
        </head>
        <body>
            <table width="100%" border="0" cellpadding="0" cellspacing="0" style="border: 2px solid #000000; padding: 6px;">
                <tr>
                    <td>
                        <table width="100%" border="0" cellpadding="0" cellspacing="0">
                            <tr><td class="header-title">{config.APP_NAME}</td></tr>
                            <tr><td class="main-title">بطاقة الموظف</td></tr>
                            <tr><td style="border-bottom: 2px solid #000000; height: 3px;"></td></tr>
                        </table>

                        <div style="height: 8px;"></div>

                        <table width="100%" border="0" cellpadding="0" cellspacing="0">
                            {info_html}
                        </table>

                        <div style="height: 8px;"></div>

                        <!-- عنوان القسم كجدول منفصل حتى لا ينهار التخطيط بسبب LTR -->
                        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="border: 2px solid #000000; border-bottom: none;">
                            <tr>
                                <td class="section-header">الرصيد الحالي</td>
                            </tr>
                        </table>
                        <!-- جدول الرصيد الفعلي -->
                        <table width="100%" border="0" cellpadding="0" cellspacing="0" style="border: 2px solid #000000;">
                            {balance_html}
                        </table>

                        <div style="height: 8px;"></div>

                        <!-- تم عكس النصوص لضمان ظهورها الصحيح في وضع LTR -->
                        <table width="100%" border="0" cellpadding="0" cellspacing="0">
                            <tr><td class="summary-box">{len(active_leaves)} &nbsp;:الإجازات المسجلة</td></tr>
                        </table>
                    </td>
                </tr>
            </table>

            <div style="text-align: center; font-size: 9pt; color: #333333; margin-top: 5px;">
                {today} &nbsp;:تاريخ الإصدار
            </div>
        </body>
        </html>
        """

    def _print_card(self) -> None:
        """طباعة البطاقة لملء ورقة A5 بالكامل والتأكد من اتجاه النص."""
        try:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)

            dialog = QPrintDialog(printer, self)
            dialog.setWindowTitle("طباعة البطاقة")
            if dialog.exec() != QPrintDialog.DialogCode.Accepted:
                return

            # 🔴 خطوة مهمة جداً:
            # إعادة تعيين حجم الورقة والهوامش *بعد* اختيار الطابعة
            # لأن الطابعة تعيد ضبط الحجم تلقائياً إلى A4
            printer.setPageSize(QPageSize(QPageSize.PageSizeId.A5))
            printer.setPageOrientation(QPageLayout.Orientation.Portrait)
            printer.setPageMargins(QMarginsF(3, 3, 3, 3), QPageLayout.Unit.Millimeter)

            # بناء HTML
            html = self._build_card_html()
            doc = QTextDocument()
            doc.setDocumentMargin(0)
            # إجبار المستند على استخدام خط محدد لمنع تعريف الطابعة من العبث باتجاه النصوص
            font = QFont("Arial", 12)
            doc.setDefaultFont(font)

            doc.setHtml(html)

            # تحديث أبعاد المستند بناءً على المساحة الفعلية للطباعة
            page_rect = printer.pageRect(QPrinter.Unit.Point)
            doc.setPageSize(QSizeF(page_rect.size()))

            doc.print(printer)
            W.info(self, "تم إرسال البطاقة للطباعة.")
        except Exception as exc:
            W.error(self, f"تعذّر الطباعة: {exc}")

    def _export_pdf(self) -> None:
        """تصدير البطاقة كملف PDF لملء ورقة A5 بالكامل."""
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "تصدير PDF",
            f"بطاقة_{self.employee.emp_id}_{self.employee.name}.pdf",
            "PDF Files (*.pdf)"
        )
        if not path:
            return

        try:
            # استخدام HighResolution لضمان دقة أعلى وتمدد صحيح
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setPageSize(QPageSize(QPageSize.PageSizeId.A5))
            printer.setPageOrientation(QPageLayout.Orientation.Portrait)

            # تعيين هوامش الطابعة
            printer.setPageMargins(QMarginsF(3, 3, 3, 3), QPageLayout.Unit.Millimeter)

            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(path)

            # بناء HTML وتحويله إلى QTextDocument ثم طباعته كـ PDF
            html = self._build_card_html()
            doc = QTextDocument()
            doc.setDocumentMargin(0)
            doc.setHtml(html)

            # إجبار المستند على أخذ الأبعاد الحقيقية لصفحة الطباعة
            page_rect = printer.pageRect(QPrinter.Unit.Point)
            doc.setPageSize(QSizeF(page_rect.size()))

            doc.print(printer)
            W.info(self, f"تم تصدير البطاقة إلى:\n{path}")
        except Exception as exc:
            W.error(self, f"تعذّر التصدير: {exc}")