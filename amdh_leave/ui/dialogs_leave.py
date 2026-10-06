"""حوارات الإجازات: تسجيل/تعديل، المرفقات، كشف الحساب، تصفية نهاية الخدمة."""

from __future__ import annotations

import shutil
import uuid
from datetime import date
from pathlib import Path

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget,
)

from .. import config
from ..exporters import excel as X
from ..exporters import html as H
from ..exporters import pdf as P
from ..models import Leave
from ..services import balance as B
from ..services import dates as D
from ..services import reports, validation
from . import theme, widgets as W
from .dialogs_base import BaseDialog, IssuesBox


class LeaveDialog(BaseDialog):
    """تسجيل أو تعديل إجازة مع معاينة حيّة للأثر على الرصيد."""

    def __init__(self, parent=None, ctx=None, emp_id: str = "", leave_id: int | None = None,
                 on_save=None):
        super().__init__(parent, ctx, "تعديل إجازة" if leave_id else "تسجيل إجازة")
        self.emp_id = emp_id
        self.leave_id = leave_id
        self.on_save = on_save
        self.employee = self.ctx.db.get_employee(emp_id)
        self.policy = self.ctx.db.policy(refresh=True)
        self.resize(620, 700)
        if not self.employee:
            W.error(self, "الموظف غير موجود.")
            self.reject()
            return
        self._build()
        self._load_leave()
        self._recalc()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label(
            f"{'تعديل إجازة' if self.leave_id else 'تسجيل إجازة'} — {self.employee.name}", 15))
        layout.addWidget(W.muted_label(
            f"الرقم الوظيفي: {self.employee.emp_id} | {self.employee.job_title} | "
            f"{self.employee.institution}"))

        frame = W.card()
        form = QFormLayout(frame)
        form.setSpacing(10)

        self.cb_type = QComboBox()
        self.cb_type.addItems(self.policy.types_for_gender(self.employee.gender))
        self.cb_type.currentTextChanged.connect(self._on_type_changed)

        amount_row = QHBoxLayout()
        self.sp_amount = QSpinBox()
        self.sp_amount.setRange(1, 100000)
        self.sp_amount.setValue(1)
        self.sp_amount.valueChanged.connect(self._recalc)
        self.cb_unit = QComboBox()
        self.cb_unit.addItems(list(config.UNITS))
        self.cb_unit.currentTextChanged.connect(self._recalc)
        amount_row.addWidget(self.sp_amount, 2)
        amount_row.addWidget(self.cb_unit, 1)

        self.d_start = W.date_edit(date.today())
        self.d_start.dateChanged.connect(self._recalc)

        self.lbl_period = QLabel("—")
        self.lbl_period.setStyleSheet(theme.label_style("accent", 11, bold=True))

        self.chk_manual = QCheckBox("تعديل الأيام المؤثرة يدوياً")
        self.sp_days = QSpinBox()
        self.sp_days.setRange(-100000, 100000)
        self.sp_days.setEnabled(False)
        self.sp_days.valueChanged.connect(self._recalc)
        self.chk_manual.toggled.connect(self._on_manual_toggled)
        manual_row = QHBoxLayout()
        manual_row.addWidget(self.chk_manual)
        manual_row.addWidget(self.sp_days)
        manual_row.addStretch()

        self.chk_outside = QCheckBox("استبعاد أيام هذه الإجازة من أيام الخدمة")
        self.chk_outside.toggled.connect(self._recalc)
        self.lbl_rule_hint = W.muted_label("")

        self.e_order = QLineEdit()
        self.d_order = W.OptionalDate("تاريخ الأمر", date.today())
        self.e_reason = QLineEdit()
        self.cb_status = QComboBox()
        for key in config.LEAVE_STATUSES:
            self.cb_status.addItem(config.LEAVE_STATUS_LABELS[key], key)
        if not self.ctx.can("approve"):
            self.cb_status.setCurrentIndex(1)
            self.cb_status.setEnabled(False)

        form.addRow("نوع الإجازة", self.cb_type)
        form.addRow("العدد والوحدة", self._holder(amount_row))
        form.addRow("تبدأ في", self.d_start)
        form.addRow("المدة المحتسبة", self.lbl_period)
        form.addRow("", self._holder(manual_row))
        form.addRow("", self.chk_outside)
        form.addRow("", self.lbl_rule_hint)
        form.addRow("رقم الأمر", self.e_order)
        form.addRow("", self.d_order)
        form.addRow("الحالة", self.cb_status)
        form.addRow("السبب / الملاحظة", self.e_reason)
        layout.addWidget(frame)

        # معاينة الرصيد
        preview = W.card()
        preview_layout = QHBoxLayout(preview)
        self.lbl_before = W.LabeledValue("الرصيد الحالي")
        self.lbl_days = W.LabeledValue("الأيام المؤثرة")
        self.lbl_after = W.LabeledValue("الرصيد بعد التسجيل")
        for widget in (self.lbl_before, self.lbl_days, self.lbl_after):
            preview_layout.addWidget(widget)
        layout.addWidget(preview)
        self.lbl_note = W.muted_label("")
        self.lbl_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_note)

        self.issues = IssuesBox()
        layout.addWidget(self.issues)
        layout.addStretch()
        layout.addLayout(self.buttons_row(W.button("إلغاء", "Ghost", self.reject, width=110),
                                          W.button("💾 حفظ الإجازة", "Accent", self._save, width=160)))

    @staticmethod
    def _holder(layout) -> QWidget:
        holder = QWidget()
        holder.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        return holder

    # ------------------------------------------------------------------
    def _load_leave(self) -> None:
        if not self.leave_id:
            self._on_type_changed(self.cb_type.currentText())
            return
        leave = self.ctx.db.get_leave(self.leave_id)
        if not leave:
            W.error(self, "الإجازة غير موجودة.")
            self.reject()
            return
        index = self.cb_type.findText(leave.type)
        if index < 0:
            self.cb_type.addItem(leave.type)
            index = self.cb_type.count() - 1
        self.cb_type.setCurrentIndex(index)
        self._on_type_changed(leave.type, manual=True)
        self.sp_amount.setValue(max(1, abs(leave.amount) or 1))
        unit_index = self.cb_unit.findText(leave.unit)
        self.cb_unit.setCurrentIndex(unit_index if unit_index >= 0 else 0)
        W.set_date(self.d_start, leave.start_date)
        self.chk_outside.setChecked(bool(leave.outside_balance))
        self.e_order.setText(leave.order)
        if leave.order_date:
            self.d_order.set_value(leave.order_date)
        else:
            self.d_order.check.setChecked(False)
        self.e_reason.setText(leave.reason)
        status_index = self.cb_status.findData(leave.status)
        if status_index >= 0 and self.cb_status.isEnabled():
            self.cb_status.setCurrentIndex(status_index)
        # حماية البيانات القديمة: إن اختلف المخزون عن المحتسب، نُبقي المخزون ونفعّل التعديل اليدوي
        computed = self._compute_days()
        if computed != leave.days_actual:
            self.chk_manual.setChecked(True)
            self.sp_days.setValue(leave.days_actual)
            self.lbl_rule_hint.setText(
                f"⚠️ الأيام المخزنة سابقاً ({leave.days_actual}) تختلف عن المحتسبة حالياً "
                f"({computed}) — تم الإبقاء على المخزنة ويمكن تعديلها يدوياً.")
        else:
            self.sp_days.setValue(leave.days_actual)

    def _on_manual_toggled(self, checked: bool) -> None:
        self.sp_days.setEnabled(checked)
        if not checked:
            self.sp_days.setValue(self._compute_days())
        self._recalc()

    def _on_type_changed(self, leave_type: str, manual: bool = False) -> None:
        rule = self.policy.rule(leave_type)
        self.sp_amount.setRange(-100000 if rule.is_adjustment else 1, 100000)
        if rule.is_adjustment and self.sp_amount.value() < 1:
            pass
        self.chk_outside.setChecked(rule.service_exclusion)
        hints = []
        if rule.is_adjustment:
            hints.append("تسوية: يمكن إدخال قيمة سالبة لتصحيح الرصيد، مع ذكر السبب إلزاماً.")
        if rule.service_exclusion:
            hints.append("أيام هذا النوع تُستبعد من أيام الخدمة ولا تُخصم من الرصيد.")
        if rule.requires_order:
            hints.append("هذا النوع يتطلب رقم الأمر.")
        hints.append(f"طريقة العد: {rule.count_mode_label} | {rule.quota_label}")
        self.lbl_rule_hint.setText(" • ".join(hints))
        self.e_order.setPlaceholderText("مطلوب" if rule.requires_order else "اختياري")
        if not manual:
            self._recalc()

    # ------------------------------------------------------------------
    def _compute_end(self):
        start = W.date_of(self.d_start)
        amount = self.sp_amount.value()
        if not start or amount <= 0:
            return start, start
        return start, D.end_date_for(start, amount, self.cb_unit.currentText())

    def _compute_days(self) -> int:
        start, end = self._compute_end()
        rule = self.policy.rule(self.cb_type.currentText())
        if self.policy.rule(self.cb_type.currentText()).is_adjustment and self.sp_amount.value() < 0:
            return self.sp_amount.value()
        return D.days_count(start, end, rule.count_mode, self.policy.weekend, self.policy.holidays)

    def _candidate(self) -> Leave:
        start, end = self._compute_end()
        leave_type = self.cb_type.currentText()
        rule = self.policy.rule(leave_type)
        days = self.sp_days.value() if self.chk_manual.isChecked() else self._compute_days()
        if rule.is_adjustment and not self.chk_manual.isChecked() and self.sp_amount.value() < 0:
            days = self.sp_amount.value()
        working = D.count_working_days(start, end, self.policy.weekend, self.policy.holidays)
        return Leave(
            id=self.leave_id, emp_id=self.emp_id, type=leave_type, start_date=start, end_date=end,
            amount=self.sp_amount.value(), unit=self.cb_unit.currentText(), days_actual=days,
            working_days=working, count_mode=rule.count_mode,
            order=self.e_order.text().strip(), order_date=self.d_order.value(),
            outside_balance=self.chk_outside.isChecked(), reason=self.e_reason.text().strip(),
            added_date="", status=self.cb_status.currentData(),
            is_adjustment=rule.is_adjustment, manual_days=self.chk_manual.isChecked())

    def _recalc(self) -> None:
        if not hasattr(self, "lbl_period"):
            return
        self.lbl_period.setText(D.human_period(*self._compute_end()))
        if not self.chk_manual.isChecked():
            self.sp_days.blockSignals(True)
            self.sp_days.setValue(self._compute_days())
            self.sp_days.blockSignals(False)
        candidate = self._candidate()
        existing = self.employee.leaves
        before = validation.preview_balance(self.employee, existing, self.policy, None,
                                            exclude_id=self.leave_id)
        after = validation.preview_balance(self.employee, existing, self.policy, candidate)
        self.lbl_before.set_value(before.balance, theme.balance_color(before.balance, self.policy.low_balance_days),
                                  " يوم")
        self.lbl_days.set_value(candidate.days_actual, "accent", " يوم")
        self.lbl_after.set_value(after.balance, theme.balance_color(after.balance, self.policy.low_balance_days),
                                 " يوم")
        note, key = validation.balance_note(after, self.policy)
        self.lbl_note.setText(note)
        self.lbl_note.setStyleSheet(theme.label_style(key))
        issues = validation.validate_leave(candidate, self.employee, existing, self.policy,
                                           leave_id=self.leave_id)
        self.issues.set_issues(issues)

    # ------------------------------------------------------------------
    def _save(self) -> None:
        if not self.ctx.can("edit_leave"):
            W.error(self, "لا تملك صلاحية تسجيل الإجازات.")
            return
        candidate = self._candidate()
        issues = validation.validate_leave(candidate, self.employee, self.employee.leaves,
                                           self.policy, leave_id=self.leave_id)
        self.issues.set_issues(issues)
        errors = [i.message for i in issues if i.is_error]
        if errors:
            W.error(self, "\n".join(errors), "تعذّر الحفظ")
            return
        warnings = [i.message for i in issues if i.level == "warning"]
        if warnings and not W.confirm(self, "تنبيهات:\n\n" + "\n".join(f"• {w}" for w in warnings) +
                                      "\n\nهل تريد الحفظ على أي حال؟"):
            return
        fields = candidate.to_fields()
        if self.leave_id:
            self.ctx.db.update_leave(self.leave_id, fields, self.ctx.user())
        else:
            self.ctx.db.add_leave(self.emp_id, fields, self.ctx.user())
        if self.on_save:
            self.on_save()
        self.accept()


# ---------------------------------------------------------------------------
# المرفقات
# ---------------------------------------------------------------------------
class AttachmentsDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None, leave_id: int | None = None, emp_id: str = ""):
        super().__init__(parent, ctx, "مرفقات الإجازة")
        self.leave_id = leave_id
        self.emp_id = emp_id
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label("مرفقات الإجازة (صورة الأمر / كتاب)", 14))
        layout.addWidget(W.muted_label(f"تُخزَّن المرفقات في: {self.ctx.paths.attachments_dir}"))
        self.table = W.TablePanel(["#", "الملف", "أُضيف في", "بواسطة"])
        layout.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(W.button("➕ إضافة مرفق", "Accent", self._add))
        row.addWidget(W.button("📂 فتح المحدد", "Blue", self._open))
        row.addWidget(W.button("🗑 حذف المحدد", "Warn", self._delete))
        row.addStretch()
        row.addWidget(self.close_button())
        layout.addLayout(row)
        self._refresh()

    def _items(self):
        return self.ctx.db.list_attachments(self.leave_id) if self.leave_id else []

    def _refresh(self) -> None:
        items = self._items()
        self._data = items
        rows = [[i + 1, item.filename, item.added_at, item.added_by] for i, item in enumerate(items)]
        self.table.set_rows(rows, empty_text="لا توجد مرفقات")

    def _add(self) -> None:
        if not self.leave_id:
            W.info(self, "احفظ الإجازة أولاً ثم أضف المرفقات.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "اختر الملف", "",
                                              "ملفات (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.docx)")
        if not path:
            return
        source = Path(path)
        stored = f"{uuid.uuid4().hex}{source.suffix.lower()}"
        try:
            self.ctx.paths.attachments_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, self.ctx.paths.attachments_dir / stored)
        except OSError as exc:
            W.error(self, f"تعذّر نسخ الملف: {exc}")
            return
        self.ctx.db.add_attachment(self.leave_id, self.emp_id, source.name, stored, self.ctx.user())
        self._refresh()

    def _open(self) -> None:
        row = self.table.current_row()
        if row < 0:
            W.warn(self, "حدد مرفقاً.")
            return
        target = self.ctx.paths.attachments_dir / self._data[row].stored_name
        if not target.exists():
            W.error(self, "الملف غير موجود على القرص.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _delete(self) -> None:
        row = self.table.current_row()
        if row < 0:
            W.warn(self, "حدد مرفقاً.")
            return
        item = self._data[row]
        if not W.confirm(self, f"حذف المرفق «{item.filename}»؟"):
            return
        self.ctx.db.delete_attachment(item.id, self.ctx.user())
        try:
            (self.ctx.paths.attachments_dir / item.stored_name).unlink(missing_ok=True)
        except OSError:
            pass
        self._refresh()


# ---------------------------------------------------------------------------
# كشف الحساب
# ---------------------------------------------------------------------------
class StatementDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None, emp_id: str = ""):
        super().__init__(parent, ctx, "كشف حساب الرصيد")
        self.emp_id = emp_id
        self.policy = self.ctx.db.policy(refresh=True)
        self.employee = self.ctx.db.get_employee(emp_id)
        self.resize(980, 620)
        if not self.employee:
            W.error(self, "الموظف غير موجود.")
            self.reject()
            return
        self.balance = B.compute_balance(self.employee, self.employee.leaves, self.policy)
        self.statement = B.yearly_statement(self.employee, self.employee.leaves, self.policy)
        self.rows = reports.statement_rows(self.employee, self.policy)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label(f"كشف حساب: {self.employee.name}", 15))

        summary = W.card()
        summary_layout = QHBoxLayout(summary)
        values = [
            ("أيام الخدمة", self.balance.raw_days, "text"),
            ("خارج الرصيد", self.balance.outside, "text"),
            ("الدوام المحسوبة", self.balance.net_days, "text"),
            ("المستحقة", self.balance.earned, "pos"),
            ("المأخوذة", self.balance.taken, "gold"),
            ("الرصيد", self.balance.balance,
             theme.balance_color(self.balance.balance, self.policy.low_balance_days)),
        ]
        for title, value, key in values:
            widget = W.LabeledValue(title)
            widget.set_value(value, key, " يوم")
            summary_layout.addWidget(widget)
        layout.addWidget(summary)

        layout.addWidget(W.muted_label(self.statement.policy_note +
                                       " — قد يختلف مجموع الاستحقاق السنوي بيوم عن الاحتساب المتواصل "
                                       "بسبب تقريب كل سنة على حدة."))
        self.table = W.TablePanel(["سنة الخدمة", "من", "إلى", "أيام الخدمة", "خارج الرصيد",
                                   "صافي الدوام", "المستحق", "المأخوذ", "منتهي", "الرصيد المرحّل"])
        data = [[r["index"], r["start"], r["end"], r["service_days"], r["outside_days"],
                 r["net_days"], r["earned"], r["taken"], r["expired"], r["carry_out"]]
                for r in self.rows]
        self.table.set_rows(data, numeric_columns={3, 4, 5, 6, 7, 8, 9},
                            empty_text="لا توجد سنوات خدمة محتسبة")
        layout.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(W.button("📊 Excel", "Ghost", self._excel))
        row.addWidget(W.button("📄 PDF", "Ghost", self._pdf))
        row.addWidget(W.button("🖨 طباعة", "Blue", self._print))
        row.addStretch()
        row.addWidget(self.close_button())
        layout.addLayout(row)

    def _excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "حفظ كشف الحساب", f"statement_{self.emp_id}.xlsx",
                                              "Excel (*.xlsx)")
        if not path:
            return
        try:
            X.export_statement(path, self.employee, self.policy, self.rows, self.balance)
            W.info(self, f"تم التصدير:\n{path}")
        except Exception as exc:
            W.error(self, f"فشل التصدير: {exc}")

    def _pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "حفظ PDF", f"statement_{self.emp_id}.pdf", "PDF (*.pdf)")
        if not path:
            return
        try:
            P.export_statement(path, self.employee, self.policy, self.rows, self.balance)
            W.info(self, f"تم التصدير:\n{path}")
        except Exception as exc:
            W.error(self, f"فشل التصدير: {exc}")

    def _print(self) -> None:
        content = H.statement_html(self.employee, self.policy, self.statement, self.balance)
        path = H.save_and_open(content, self.ctx.paths.reports_dir, f"statement_{self.emp_id}.html")
        W.info(self, f"تم فتح كشف الحساب في المتصفح:\n{path.name}")


# ---------------------------------------------------------------------------
# تصفية نهاية الخدمة
# ---------------------------------------------------------------------------
class SettlementDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None, emp_id: str = ""):
        super().__init__(parent, ctx, "تصفية نهاية الخدمة")
        self.emp_id = emp_id
        self.policy = self.ctx.db.policy(refresh=True)
        self.employee = self.ctx.db.get_employee(emp_id)
        self.resize(620, 480)
        if not self.employee:
            W.error(self, "الموظف غير موجود.")
            self.reject()
            return
        self._build()
        self._recalc()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label(f"تصفية نهاية الخدمة — {self.employee.name}", 15))
        card = W.card()
        form = QFormLayout(card)
        self.d_asof = W.date_edit(self.employee.end_date or date.today())
        self.d_asof.dateChanged.connect(self._recalc)
        form.addRow("تاريخ التصفية", self.d_asof)
        self.sp_value = QDoubleSpinBox()
        self.sp_value.setRange(0, 100_000_000)
        self.sp_value.setDecimals(2)
        self.sp_value.setSuffix(" (قيمة اليوم)")
        self.sp_value.valueChanged.connect(self._recalc)
        form.addRow("قيمة اليوم الواحد (اختياري)", self.sp_value)
        layout.addWidget(card)

        summary = W.card()
        summary_layout = QHBoxLayout(summary)
        self.lbl_service = W.LabeledValue("صافي أيام الخدمة")
        self.lbl_earned = W.LabeledValue("المستحقة")
        self.lbl_taken = W.LabeledValue("المأخوذة")
        self.lbl_balance = W.LabeledValue("الرصيد المستحق")
        self.lbl_amount = W.LabeledValue("المبلغ")
        for widget in (self.lbl_service, self.lbl_earned, self.lbl_taken, self.lbl_balance, self.lbl_amount):
            summary_layout.addWidget(widget)
        layout.addWidget(summary)
        layout.addWidget(W.muted_label("الرصيد السالب يعني أن الموظف استهلك أكثر من استحقاقه "
                                       "(مسموح حسب الضوابط الإدارية) ويُعرض للمعلومة عند التصفية."))
        layout.addStretch()
        layout.addLayout(self.buttons_row(self.close_button()))

    def _recalc(self) -> None:
        as_of = W.date_of(self.d_asof)
        value = self.sp_value.value() or None
        result = B.settlement(self.employee, self.employee.leaves, self.policy,
                              today=as_of, day_value=value, as_of_end_of_service=False)
        self.lbl_service.set_value(result.service_days, "text", " يوم")
        self.lbl_earned.set_value(result.earned, "pos", " يوم")
        self.lbl_taken.set_value(result.taken, "gold", " يوم")
        self.lbl_balance.set_value(result.balance_days,
                                   theme.balance_color(result.balance_days, self.policy.low_balance_days), " يوم")
        self.lbl_amount.set_value(f"{result.amount:,.2f}" if result.amount is not None else "—", "accent")
