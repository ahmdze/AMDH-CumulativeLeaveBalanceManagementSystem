"""حوار إضافة/تعديل موظف."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFormLayout, QLineEdit, QTextEdit, QVBoxLayout,
)

from .. import config
from ..models import Employee
from ..services import dates as D
from ..services import validation
from . import widgets as W
from .dialogs_base import BaseDialog, IssuesBox

STATUS_LABELS = {"active": "على الملاك", "leave": "بإجازة", "retired": "متقاعد/منتهية خدمته"}


class EmployeeDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None, emp_id: str | None = None, on_save=None):
        super().__init__(parent, ctx, "تعديل موظف" if emp_id else "إضافة موظف جديد")
        self.emp_id = emp_id
        self.edit_mode = emp_id is not None
        self.on_save = on_save
        self.resize(560, 640)
        self._build()
        if self.edit_mode:
            self._load()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label("تعديل بيانات الموظف" if self.edit_mode
                                       else "إضافة موظف جديد", 15))
        frame = W.card()
        form = QFormLayout(frame)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(12)

        self.e_id = QLineEdit()
        self.e_id.setPlaceholderText("مثال: 57454545")
        self.e_name = QLineEdit()
        self.e_title = QLineEdit()
        self.e_workplace = QLineEdit()
        self.e_institution = QLineEdit()
        self.e_notes = QTextEdit()
        self.e_notes.setFixedHeight(70)

        self.cb_gender = QComboBox()
        self.cb_gender.addItems(["ذكر", "أنثى"])
        self.cb_status = QComboBox()
        for key, label in STATUS_LABELS.items():
            self.cb_status.addItem(label, key)

        self.d_start = W.date_edit()
        self.d_end = W.OptionalDate("انتهاء الخدمة", None)

        form.addRow("الرقم الوظيفي *", self.e_id)
        form.addRow("الاسم الكامل *", self.e_name)
        form.addRow("العنوان الوظيفي", self.e_title)
        form.addRow("مكان العمل", self.e_workplace)
        form.addRow("المؤسسة / القسم", self.e_institution)
        form.addRow("الجنس", self.cb_gender)
        form.addRow("الحالة", self.cb_status)
        form.addRow("تاريخ المباشرة *", self.d_start)
        form.addRow("", self.d_end)
        form.addRow("ملاحظات", self.e_notes)
        layout.addWidget(frame)

        self.issues = IssuesBox()
        layout.addWidget(self.issues)
        if self.edit_mode:
            self.e_id.setEnabled(False)
            hint = W.muted_label("الرقم الوظيفي غير قابل للتعديل بعد الإنشاء.")
            layout.addWidget(hint)

        layout.addStretch()
        layout.addLayout(self.buttons_row(W.button("إلغاء", "Ghost", self.reject, width=110),
                                          W.button("💾 حفظ", "Accent", self._save, width=140)))

    # ------------------------------------------------------------------
    def _load(self) -> None:
        employee = self.ctx.db.get_employee(self.emp_id)
        if not employee:
            W.error(self, "الموظف غير موجود.")
            self.reject()
            return
        self.e_id.setText(employee.emp_id)
        self.e_name.setText(employee.name)
        self.e_title.setText(employee.job_title)
        self.e_workplace.setText(employee.workplace)
        self.e_institution.setText(employee.institution)
        self.e_notes.setPlainText(employee.notes)
        self.cb_gender.setCurrentText(employee.gender if employee.gender in ("ذكر", "أنثى") else "ذكر")
        index = self.cb_status.findData(employee.status)
        if index >= 0:
            self.cb_status.setCurrentIndex(index)
        W.set_date(self.d_start, employee.start_date)
        self.d_end.set_value(employee.end_date)

    # ------------------------------------------------------------------
    def _fields(self) -> dict:
        return {
            "name": self.e_name.text().strip(),
            "job_title": self.e_title.text().strip(),
            "workplace": self.e_workplace.text().strip(),
            "institution": self.e_institution.text().strip(),
            "gender": self.cb_gender.currentText(),
            "start_date": D.to_iso(W.date_of(self.d_start)),
            "end_date": D.to_iso(self.d_end.value()),
            "notes": self.e_notes.toPlainText().strip(),
            "status": self.cb_status.currentData(),
        }

    def _save(self) -> None:
        emp_id = self.emp_id if self.edit_mode else self.e_id.text().strip()
        if not self.ctx.can("edit_employee"):
            W.error(self, "لا تملك صلاحية تعديل الموظفين.")
            return
        fields = self._fields()
        issues = validation.validate_employee(fields, emp_id, edit_mode=self.edit_mode,
                                              exists=self.ctx.db.employee_exists)
        self.issues.set_issues(issues)
        if any(i.is_error for i in issues):
            W.error(self, "\n".join(i.message for i in issues if i.is_error), "تعذّر الحفظ")
            return
        if self.edit_mode:
            self.ctx.db.update_employee(emp_id, fields, self.ctx.user())
        else:
            self.ctx.db.add_employee(emp_id, fields, self.ctx.user())
        if self.on_save:
            self.on_save()
        self.accept()
