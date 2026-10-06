"""مشاركة التقارير: إرسال بالبريد الإلكتروني أو إلى تلغرام (مع خيط عمل غير حاجب)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QRadioButton,
    QVBoxLayout, QWidget,
)

from ..exporters import excel as X
from ..exporters import html as H
from ..exporters import pdf as P
from ..services import reports
from ..services import sharing
from . import theme, widgets as W
from .dialogs_base import BaseDialog


class _SendWorker(QThread):
    """ينفّذ الإرسال خارج واجهة المستخدم حتى لا تتجمّد."""

    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.job = job

    def run(self) -> None:  # noqa: D102
        try:
            message = self.job()
        except Exception as exc:  # noqa: BLE001 - تُعرض للمستخدم
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(message or "تم الإرسال بنجاح.")


class ShareDialog(BaseDialog):
    """حوار إعداد وإرسال التقارير."""

    def __init__(self, parent=None, ctx=None, emp_id: str | None = None, on_settings=None):
        super().__init__(parent, ctx, "مشاركة التقارير")
        self.emp_id = emp_id
        self.on_settings = on_settings
        self.worker: _SendWorker | None = None
        self.resize(720, 620)
        self.email_config = sharing.EmailConfig.from_settings(self.ctx.settings)
        self.telegram_config = sharing.TelegramConfig.from_settings(self.ctx.settings)
        self._build()
        self._update_status()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label("مشاركة التقارير", 15))
        layout.addWidget(W.muted_label(
            "يُنشئ النظام ملفات التقرير المطلوبة ثم يرسلها بالبريد أو إلى تلغرام."))

        scope_box = QGroupBox("نطاق التقرير")
        scope_layout = QVBoxLayout(scope_box)
        self.rb_employee = QRadioButton("الموظف المحدد")
        self.rb_all = QRadioButton("كل الموظفين (المعروضين)")
        self.rb_all.setChecked(True if not self.emp_id else False)
        self.rb_employee.setChecked(bool(self.emp_id))
        self.rb_employee.setEnabled(bool(self.emp_id))
        scope_layout.addWidget(self.rb_employee)
        scope_layout.addWidget(self.rb_all)
        layout.addWidget(scope_box)

        format_box = QGroupBox("صيغة الملفات")
        format_layout = QHBoxLayout(format_box)
        self.chk_excel = QCheckBox("Excel (.xlsx)")
        self.chk_pdf = QCheckBox("PDF")
        self.chk_html = QCheckBox("HTML (طباعة)")
        self.chk_excel.setChecked(True)
        self.chk_pdf.setChecked(P.available()[0])
        for box in (self.chk_excel, self.chk_pdf, self.chk_html):
            format_layout.addWidget(box)
        format_layout.addStretch()
        self.chk_pdf.setEnabled(X.HAS_XLSX and P.available()[0])
        if not P.available()[0]:
            self.chk_pdf.setToolTip(P.available()[1])
        layout.addWidget(format_box)

        message_box = QGroupBox("نص الرسالة (اختياري)")
        message_layout = QVBoxLayout(message_box)
        self.e_subject = QLineEdit(f"تقرير الإجازات التراكمية — {date.today()}")
        self.e_body = QLineEdit("مرفق تقرير الإجازات التراكمية.")
        message_layout.addWidget(QLabel("الموضوع"))
        message_layout.addWidget(self.e_subject)
        message_layout.addWidget(QLabel("المحتوى"))
        message_layout.addWidget(self.e_body)
        self.cb_recipients = QComboBox()
        self.cb_recipients.setEditable(True)
        self.cb_recipients.addItems(self.email_config.recipients)
        self.cb_recipients.setCurrentText(", ".join(self.email_config.recipients))
        message_layout.addWidget(QLabel("المستلمون (مفصولون بفاصلة)"))
        message_layout.addWidget(self.cb_recipients)
        layout.addWidget(message_box)

        self.lbl_channel_email = W.muted_label("")
        self.lbl_channel_telegram = W.muted_label("")
        layout.addWidget(self.lbl_channel_email)
        layout.addWidget(self.lbl_channel_telegram)

        buttons = QHBoxLayout()
        self.btn_email = W.button("📧 إرسال بالبريد", "Blue", self._send_email)
        self.btn_telegram = W.button("📨 إرسال إلى تلغرام", "Accent", self._send_telegram)
        buttons.addWidget(self.btn_email)
        buttons.addWidget(self.btn_telegram)
        buttons.addStretch()
        buttons.addWidget(W.button("⚙ إعدادات المشاركة", "Ghost", self._open_settings))
        layout.addLayout(buttons)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
        layout.addStretch()
        layout.addLayout(self.buttons_row(self.close_button()))

    # ------------------------------------------------------------------
    def _update_status(self) -> None:
        ok_style = theme.label_style("pos")
        bad_style = theme.label_style("muted")
        email_ready = self.email_config.is_configured
        telegram_ready = self.telegram_config.is_configured
        self.lbl_channel_email.setText(
            f"{'البريد'}: " + (f"{self.email_config.host}:{self.email_config.port}"
                                   if email_ready else "غير مُهيَّأ — افتح إعدادات المشاركة"))
        self.lbl_channel_email.setStyleSheet(ok_style if email_ready else bad_style)
        self.lbl_channel_telegram.setText(
            f"{'تلغرام'}: " + (f"محادثة {self.telegram_config.chat_id}"
                                   if telegram_ready else "غير مُهيَّأ — افتح إعدادات المشاركة"))
        self.lbl_channel_telegram.setStyleSheet(ok_style if telegram_ready else bad_style)
        self.btn_email.setEnabled(email_ready)
        self.btn_telegram.setEnabled(telegram_ready)

    def _open_settings(self) -> None:
        if self.on_settings:
            self.on_settings()

    # ------------------------------------------------------------------
    def _generate_files(self) -> list[Path]:
        """ينشئ ملفات التقرير المطلوبة ويعيد مساراتها."""
        target_dir = self.ctx.paths.reports_dir / "shared"
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = date.today().strftime("%Y%m%d")
        files: list[Path] = []
        policy = self.ctx.db.policy(refresh=True)

        if self.rb_employee.isChecked() and self.emp_id:
            employee = self.ctx.db.get_employee(self.emp_id)
            if not employee:
                raise sharing.SharingError("الموظف غير موجود.")
            if self.chk_excel.isChecked():
                path = target_dir / f"leaves_{employee.emp_id}_{stamp}.xlsx"
                X.export_leaves(path, employee, policy)
                files.append(path)
            if self.chk_pdf.isChecked():
                path = target_dir / f"leaves_{employee.emp_id}_{stamp}.pdf"
                P.export_employee_leaves(path, employee, policy)
                files.append(path)
            if self.chk_html.isChecked():
                from ..services import balance as B
                balance = B.compute_balance(employee, employee.leaves, policy)
                statement = B.yearly_statement(employee, employee.leaves, policy)
                content = H.employee_detail_html(employee, policy, balance, statement,
                                                 auto_print=False)
                path = H.save(content, target_dir, f"employee_{employee.emp_id}_{stamp}.html")
                files.append(path)
        else:
            employees = self.ctx.employees()
            rows = reports.global_report(employees, policy)
            if not rows:
                raise sharing.SharingError("لا توجد بيانات للتصدير.")
            if self.chk_excel.isChecked():
                path = target_dir / f"employees_{stamp}.xlsx"
                X.export_employees(path, rows)
                files.append(path)
            if self.chk_pdf.isChecked():
                path = target_dir / f"employees_{stamp}.pdf"
                P.export_report(path, rows, policy)
                files.append(path)
            if self.chk_html.isChecked():
                content = H.global_report_html(rows, policy)
                path = H.save(content, target_dir, f"employees_{stamp}.html")
                files.append(path)

        if not files:
            raise sharing.SharingError("اختر صيغة واحدة على الأقل.")
        return files

    def _run(self, job, label: str) -> None:
        if self.worker is not None and self.worker.isRunning():
            W.warn(self, "هناك عملية إرسال جارية.")
            return
        self.btn_email.setEnabled(False)
        self.btn_telegram.setEnabled(False)
        self.lbl_status.setText(f"{label}... الرجاء الانتظار")
        self.lbl_status.setStyleSheet(theme.label_style("gold"))
        self.worker = _SendWorker(job, self)
        self.worker.succeeded.connect(self._on_success)
        self.worker.failed.connect(self._on_failure)
        self.worker.finished.connect(self._update_status)
        self.worker.start()

    def _on_success(self, message: str) -> None:
        self.lbl_status.setText(message)
        self.lbl_status.setStyleSheet(theme.label_style("pos"))
        self.ctx.db.log(self.ctx.user(), "مشاركة", "report", "", message)

    def _on_failure(self, message: str) -> None:
        self.lbl_status.setText(message)
        self.lbl_status.setStyleSheet(theme.label_style("neg"))

    def _recipients(self) -> list[str]:
        raw = self.cb_recipients.currentText().replace(";", ",")
        return [item.strip() for item in raw.split(",") if item.strip()]

    def _send_email(self) -> None:
        config = self.email_config
        config.recipients = self._recipients()
        subject = self.e_subject.text().strip() or "تقرير الإجازات التراكمية"
        body = self.e_body.text().strip()
        problem = sharing.validate_email_config(config)
        if problem:
            W.error(self, problem)
            return

        def job() -> str:
            files = self._generate_files()
            sharing.send_email(config, subject, body, files)
            return f'تم إرسال {len(files)} ملفاً إلى {", ".join(config.recipients)}'

        self._run(job, "جارٍ الإرسال بالبريد")

    def _send_telegram(self) -> None:
        config = self.telegram_config
        problem = sharing.validate_telegram_config(config)
        if problem:
            W.error(self, problem)
            return
        caption = self.e_body.text().strip() or self.e_subject.text().strip()

        def job() -> str:
            files = self._generate_files()
            count = sharing.send_telegram(config, caption, files)
            return f"تم إرسال {count} عنصراً إلى تلغرام"

        self._run(job, "جارٍ الإرسال إلى تلغرام")

    def closeEvent(self, event):  # noqa: N802
        if self.worker is not None and self.worker.isRunning():
            if not W.confirm(self, "هناك عملية إرسال جارية — هل تريد الإغلاق؟"):
                event.ignore()
                return
        event.accept()
