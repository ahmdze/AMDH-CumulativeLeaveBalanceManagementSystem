"""حوار إضافة/تعديل موظف — البيانات الأساسية + الرصيد الافتتاحي."""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QLineEdit, QSpinBox, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget,
)

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
        self.resize(640, 760)
        self._build()
        if self.edit_mode:
            self._load()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label("تعديل بيانات الموظف" if self.edit_mode
                                       else "إضافة موظف جديد", 15))
        tabs = QTabWidget()
        tabs.addTab(self._tab_basic(), "البيانات الأساسية")
        tabs.addTab(self._tab_opening(), "الرصيد الافتتاحي")
        layout.addWidget(tabs, 1)

        self.issues = IssuesBox()
        layout.addWidget(self.issues)
        if self.edit_mode:
            self.e_id.setEnabled(False)
            layout.addWidget(W.muted_label("الرقم الوظيفي غير قابل للتعديل بعد الإنشاء."))
        layout.addLayout(self.buttons_row(W.button("إلغاء", "Ghost", self.reject, width=110),
                                          W.button("💾 حفظ", "Accent", self._save, width=140)))

    def _tab_basic(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        frame = W.card()
        form = QFormLayout(frame)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(12)

        self.e_id = QLineEdit()
        self.e_id.setPlaceholderText("مثال: 57454545")
        self.e_name = QLineEdit()
        self.e_title = QLineEdit()
        self.e_workplace = QLineEdit()
        self.e_institution = QComboBox()
        self.e_institution.setEditable(True)
        self.e_institution.addItem("")
        for institution in self.ctx.db.list_institutions(active_only=True):
            label = institution.name + (f" ({institution.code})" if institution.code else "")
            self.e_institution.addItem(label, institution.name)
        self.e_institution.setToolTip(
            "المؤسسة الحالية للموظف — تُختار من قائمة المؤسسات المسجّلة")
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
        outer.addWidget(frame)
        if self.ctx.session.scoped_institution:
            self.e_institution.setEnabled(False)
            self.e_institution.setToolTip(
                f"مقيَّد بمؤسستك: {self.ctx.session.scoped_institution}")
        outer.addStretch()
        return page

    def _tab_opening(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        note = W.muted_label(
            "الرصيد الافتتاحي هو **آخر رصيد متبقٍ** حسب الحساب اليدوي قبل تشغيل النظام. "
            "يُحسب من اليوم التالي لتاريخ الاحتساب، وتُضاف إليه الإجازات المستحقة بعد "
            "التاريخ وتُخصم الإجازات المسجّلة بعده. لا تُسجَّل إجازات تخصم من الرصيد "
            "قبل أو عند تاريخ الاحتساب.")
        note.setWordWrap(True)
        outer.addWidget(note)

        frame = W.card()
        form = QFormLayout(frame)
        form.setSpacing(12)
        self.chk_opening = QCheckBox("له رصيد افتتاحي محسوب يدوياً")
        self.sp_opening = QSpinBox()
        self.sp_opening.setRange(-100000, 100000)
        self.sp_opening.setSuffix(" يوم")
        self.sp_opening.setValue(0)
        self.d_opening = W.date_edit()
        W.set_date(self.d_opening, date.today())
        self.e_opening_by = QLineEdit()
        self.e_opening_by.setPlaceholderText("اسم الشخص/الجهة التي حسبت الرصيد")
        self.e_opening_note = QTextEdit()
        self.e_opening_note.setFixedHeight(80)
        self.e_opening_note.setPlaceholderText("تفاصيل الحساب أو مرجع الكتاب/الورقة")

        form.addRow("", self.chk_opening)
        form.addRow("الرصيد المتبقي", self.sp_opening)
        form.addRow("تاريخ الاحتساب", self.d_opening)
        form.addRow("من قام بالحساب *", self.e_opening_by)
        form.addRow("تفاصيل الحساب", self.e_opening_note)
        outer.addWidget(frame)

        self.lbl_opening_warning = W.muted_label("")
        self.lbl_opening_warning.setWordWrap(True)
        self.lbl_opening_warning.setStyleSheet("color: #FBBF24;")
        outer.addWidget(self.lbl_opening_warning)
        if self.edit_mode:
            self.lbl_opening_warning.setText(
                "تنبيه: تعديل الرصيد الافتتاحي يعيد ضبط أساس الحساب ويُسجَّل في سجل التدقيق.")
        outer.addStretch()
        self.chk_opening.toggled.connect(self._toggle_opening)
        self._toggle_opening(False)
        return page

    def _toggle_opening(self, enabled: bool) -> None:
        for widget in (self.sp_opening, self.d_opening, self.e_opening_by, self.e_opening_note):
            widget.setEnabled(enabled)

    # ------------------------------------------------------------------
    def _load(self) -> None:
        employee = self.ctx.db.get_employee(self.emp_id)
        if not employee:
            W.error(self, "الموظف غير موجود.")
            self.reject()
            return
        self.employee = employee
        self.e_id.setText(employee.emp_id)
        self.e_name.setText(employee.name)
        self.e_title.setText(employee.job_title)
        self.e_workplace.setText(employee.workplace)
        if employee.institution and self.e_institution.findData(employee.institution) < 0:
            self.e_institution.addItem(employee.institution, employee.institution)
        index = self.e_institution.findData(employee.institution)
        if index >= 0:
            self.e_institution.setCurrentIndex(index)
        else:
            self.e_institution.setCurrentText(employee.institution)
        self.e_notes.setPlainText(employee.notes)
        self.cb_gender.setCurrentText(employee.gender if employee.gender in ("ذكر", "أنثى") else "ذكر")
        index = self.cb_status.findData(employee.status)
        if index >= 0:
            self.cb_status.setCurrentIndex(index)
        W.set_date(self.d_start, employee.start_date)
        self.d_end.set_value(employee.end_date)
        self.chk_opening.setChecked(bool(employee.opening_balance_set))
        self.sp_opening.setValue(int(employee.opening_balance or 0))
        if employee.opening_balance_date:
            W.set_date(self.d_opening, employee.opening_balance_date)
        self.e_opening_by.setText(employee.opening_balance_by)
        self.e_opening_note.setPlainText(employee.opening_balance_note)
        self._toggle_opening(self.chk_opening.isChecked())

    # ------------------------------------------------------------------
    def _institution_value(self) -> str:
        """المؤسسة المختارة (النص كما هو إن كُتب يدوياً أو القيمة المرتبطة)."""
        data = self.e_institution.currentData()
        text = self.e_institution.currentText().strip()
        if data and text == self.e_institution.currentText():
            return str(data)
        index = self.e_institution.findText(text)
        if index >= 0 and self.e_institution.itemData(index):
            return str(self.e_institution.itemData(index))
        return text.split(" (")[0].strip() if " (" in text else text

    def _fields(self) -> dict:
        scope = self.ctx.session.scoped_institution
        institution = scope or self._institution_value()
        opening_set = self.chk_opening.isChecked()
        return {
            "name": self.e_name.text().strip(),
            "job_title": self.e_title.text().strip(),
            "workplace": self.e_workplace.text().strip(),
            "institution": institution,
            "gender": self.cb_gender.currentText(),
            "start_date": D.to_iso(W.date_of(self.d_start)),
            "end_date": D.to_iso(self.d_end.value()),
            "notes": self.e_notes.toPlainText().strip(),
            "status": self.cb_status.currentData(),
            "opening_balance_set": int(opening_set),
            "opening_balance": self.sp_opening.value() if opening_set else 0,
            "opening_balance_date": D.to_iso(W.date_of(self.d_opening)) if opening_set else "",
            "opening_balance_by": self.e_opening_by.text().strip() if opening_set else "",
            "opening_balance_note": self.e_opening_note.toPlainText().strip() if opening_set else "",
        }

    def _opening_changed(self, fields: dict) -> bool:
        if not self.edit_mode:
            return bool(fields.get("opening_balance_set"))
        previous = getattr(self, "employee", None)
        if previous is None:
            return False
        old = (int(bool(previous.opening_balance_set)), int(previous.opening_balance or 0),
               D.to_iso(previous.opening_balance_date) if previous.opening_balance_date else "",
               previous.opening_balance_by, previous.opening_balance_note)
        new = (int(fields.get("opening_balance_set") or 0), int(fields.get("opening_balance") or 0),
               fields.get("opening_balance_date") or "",
               fields.get("opening_balance_by") or "",
               fields.get("opening_balance_note") or "")
        return old != new

    def _save(self) -> None:
        emp_id = self.emp_id if self.edit_mode else self.e_id.text().strip()
        if not self.ctx.can("edit_employee"):
            W.error(self, "لا تملك صلاحية تعديل الموظفين.")
            return
        fields = self._fields()
        issues = validation.validate_employee(fields, emp_id, edit_mode=self.edit_mode,
                                              exists=self.ctx.db.employee_exists)
        if self.edit_mode and fields.get("opening_balance_set"):
            issues += validation.validate_opening_against_leaves(
                fields, self.ctx.db.list_leaves(emp_id), self.ctx.policy)
        self.issues.set_issues(issues)
        if any(i.is_error for i in issues):
            W.error(self, "\n".join(i.message for i in issues if i.is_error), "تعذّر الحفظ")
            return
        if self.edit_mode and self._opening_changed(fields):
            if not W.confirm(
                    self,
                    "تعديل الرصيد الافتتاحي يعيد ضبط أساس الحساب.\n"
                    "سيُسجَّل التغيير في سجل التدقيق وسجل تاريخ الرصيد الافتتاحي.\n\n"
                    "هل تريد المتابعة؟", "تأكيد تعديل الرصيد الافتتاحي"):
                return
        if self.edit_mode:
            previous = self.ctx.db.get_employee(emp_id)
            self.ctx.db.update_employee(emp_id, fields, self.ctx.user())
            if previous and previous.institution != fields["institution"]:
                self.ctx.db.add_move(emp_id, previous.institution, fields["institution"],
                                     moved_on=D.date.today(), source_file="—",
                                     note="نقل يدوي من نافذة الموظف", user=self.ctx.user())
                self.ctx.db.set_employee_institution(emp_id, fields["institution"],
                                                     moved_on=D.date.today(),
                                                     user=self.ctx.user())
        else:
            self.ctx.db.add_employee(emp_id, fields, self.ctx.user())
        if self.on_save:
            self.on_save()
        self.accept()
