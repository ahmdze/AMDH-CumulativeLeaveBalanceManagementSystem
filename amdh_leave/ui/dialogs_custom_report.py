"""تقرير مخصص: بناء حر باختيار الحقول والتجميع والفلترة.

يوفر:
  - اختيار الحقول من قائمة (اسم، رقم وظيفي، نوع إجازة، تاريخ، إلخ).
  - اختيار التجميع (حسب المؤسسة، حسب النوع، حسب الشهر).
  - اختيار الفلترة (تاريخ، نوع، مؤسسة، حالة).
  - معاينة التقرير قبل التصدير.
  - تصدير إلى Excel أو PDF.
  - حفظ القوالب في app_meta لإعادة استخدامها.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..services import dates as D
from . import widgets as W
from .dialogs_base import BaseDialog

# الحقول المتاحة للتقارير
EMPLOYEE_FIELDS = [
    ("emp_id", "الرقم الوظيفي"),
    ("name", "الاسم"),
    ("job_title", "العنوان الوظيفي"),
    ("workplace", "مكان العمل"),
    ("institution", "المؤسسة"),
    ("gender", "الجنس"),
    ("start_date", "تاريخ التعيين"),
]

LEAVE_FIELDS = [
    ("type", "نوع الإجازة"),
    ("start_date", "تاريخ البداية"),
    ("end_date", "تاريخ النهاية"),
    ("days_actual", "الأيام"),
    ("status", "الحالة"),
    ("order", "رقم الأمر"),
    ("reason", "السبب"),
]

BALANCE_FIELDS = [
    ("raw_days", "أيام الخدمة"),
    ("net_days", "الدوام المحسوبة"),
    ("earned", "المستحقة"),
    ("taken", "المأخوذة"),
    ("balance", "الرصيد"),
]

GROUP_BY_OPTIONS = [
    ("none", "بدون تجميع"),
    ("institution", "حسب المؤسسة"),
    ("type", "حسب نوع الإجازة"),
    ("month", "حسب الشهر"),
    ("workplace", "حسب مكان العمل"),
]


class CustomReportDialog(BaseDialog):
    """حوار بناء تقرير مخصص."""

    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, "تقرير مخصص")
        self.resize(900, 700)
        layout = QVBoxLayout(self)

        # الشريط العلوي: نوع التقرير
        top = QHBoxLayout()
        top.addWidget(QLabel("نوع التقرير:"))
        self.report_type = QComboBox()
        self.report_type.addItems(["تقرير موظفين", "تقرير إجازات", "تقرير أرصدة"])
        self.report_type.currentIndexChanged.connect(self._on_type_change)
        top.addWidget(self.report_type, 1)
        top.addStretch()
        layout.addLayout(top)

        # المقسم: الإعدادات | المعاينة
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # لوحة الإعدادات
        settings = self._build_settings()
        splitter.addWidget(settings)

        # لوحة المعاينة
        self.preview = W.TablePanel(["—"])
        self.preview.table.setSortingEnabled(True)
        splitter.addWidget(self.preview)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        # القوالب المحفوظة
        template_row = QHBoxLayout()
        template_row.addWidget(QLabel("قوالب محفوظة:"))
        self.template_combo = QComboBox()
        self._load_templates()
        self.template_combo.currentTextChanged.connect(self._load_template)
        template_row.addWidget(self.template_combo, 1)
        template_row.addWidget(W.button("💾 حفظ قالب", "Ghost", self._save_template))
        template_row.addWidget(W.button("🗑 حذف", "Warn", self._delete_template))
        template_row.addStretch()
        layout.addLayout(template_row)

        # أزرار الإجراءات
        row = QHBoxLayout()
        row.addWidget(W.button("👁 معاينة", "Accent", self._preview_report))
        row.addWidget(W.button("📊 تصدير Excel", "Gold", self._export_excel))
        row.addWidget(W.button("📄 تصدير PDF", "Ghost", self._export_pdf))
        row.addStretch()
        row.addWidget(self.close_button())
        layout.addLayout(row)

        self._on_type_change()

    def _build_settings(self) -> QWidget:
        """بناء لوحة الإعدادات."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        # اختيار الحقول
        fields_group = QGroupBox("الحقول المعروضة")
        fields_layout = QVBoxLayout(fields_group)
        self.fields_list = QListWidget()
        self.fields_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        fields_layout.addWidget(self.fields_list)
        layout.addWidget(fields_group)

        # التجميع
        group_group = QGroupBox("التجميع")
        group_layout = QVBoxLayout(group_group)
        self.group_by = QComboBox()
        self.group_by.addItems([f"{label} ({key})" for key, label in GROUP_BY_OPTIONS])
        group_layout.addWidget(self.group_by)
        layout.addWidget(group_group)

        # الفلترة
        filter_group = QGroupBox("الفلترة")
        filter_layout = QFormLayout(filter_group)
        filter_layout.setSpacing(6)

        self.filter_institution = QComboBox()
        self.filter_institution.insertItem(0, "كل المؤسسات")
        filter_layout.addRow("المؤسسة:", self.filter_institution)

        self.filter_type = QComboBox()
        self.filter_type.insertItem(0, "كل الأنواع")
        filter_layout.addRow("نوع الإجازة:", self.filter_type)

        self.filter_status = QComboBox()
        self.filter_status.insertItem(0, "كل الحالات")
        for key, label in config.LEAVE_STATUS_LABELS.items():
            self.filter_status.addItem(label, key)
        filter_layout.addRow("الحالة:", self.filter_status)

        self.filter_date_from = W.date_edit()
        self.filter_date_to = W.date_edit()
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("من:"))
        date_row.addWidget(self.filter_date_from)
        date_row.addWidget(QLabel("إلى:"))
        date_row.addWidget(self.filter_date_to)
        filter_layout.addRow("النطاق الزمني:", self._wrap(date_row))

        self.chk_include_deleted = QCheckBox("تضمين المحذوفات")
        filter_layout.addRow("", self.chk_include_deleted)

        layout.addWidget(filter_group)
        layout.addStretch()
        return page

    @staticmethod
    def _wrap(layout) -> QWidget:
        holder = QWidget()
        holder.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        return holder

    def _on_type_change(self) -> None:
        """تحديث الحقول المتاحة حسب نوع التقرير."""
        self.fields_list.clear()
        idx = self.report_type.currentIndex()
        if idx == 0:  # موظفين
            for key, label in EMPLOYEE_FIELDS:
                item = QListWidgetItem(f"☑ {label}")
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.fields_list.addItem(item)
            # إضافة حقول الرصيد
            for key, label in BALANCE_FIELDS:
                item = QListWidgetItem(f"☐ {label}")
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.fields_list.addItem(item)
        elif idx == 1:  # إجازات
            for key, label in LEAVE_FIELDS:
                item = QListWidgetItem(f"☑ {label}")
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.fields_list.addItem(item)
            # إضافة حقول الموظف
            for key, label in EMPLOYEE_FIELDS[:3]:
                item = QListWidgetItem(f"☐ {label}")
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.fields_list.addItem(item)
        else:  # أرصدة
            for key, label in EMPLOYEE_FIELDS[:4]:
                item = QListWidgetItem(f"☑ {label}")
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.fields_list.addItem(item)
            for key, label in BALANCE_FIELDS:
                item = QListWidgetItem(f"☑ {label}")
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.fields_list.addItem(item)

        # تحديث فلاتر المؤسسات والأنواع
        self._refresh_filters()

    def _refresh_filters(self) -> None:
        """تحديث قوائم الفلترة."""
        insts = self.ctx.db.distinct_values("institution")
        current = self.filter_institution.currentText()
        self.filter_institution.clear()
        self.filter_institution.insertItem(0, "كل المؤسسات")
        for inst in insts:
            self.filter_institution.addItem(inst)
        if current:
            self.filter_institution.setCurrentText(current)

        rules = self.ctx.db.list_rules()
        current = self.filter_type.currentText()
        self.filter_type.clear()
        self.filter_type.insertItem(0, "كل الأنواع")
        for rule in rules.values():
            if rule.active:
                self.filter_type.addItem(rule.type)
        if current:
            self.filter_type.setCurrentText(current)

    def _get_selected_fields(self) -> list[tuple[str, str]]:
        """إرجاع الحقول المحددة."""
        fields = []
        for i in range(self.fields_list.count()):
            item = self.fields_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                key = item.data(Qt.ItemDataRole.UserRole)
                label = item.text().replace("☑ ", "").replace("☐ ", "")
                fields.append((key, label))
        return fields

    def _build_data(self) -> tuple[list[str], list[list]]:
        """بناء بيانات التقرير."""
        fields = self._get_selected_fields()
        if not fields:
            W.warn(self, "اختر حقلاً واحداً على الأقل.")
            return [], []

        headers = [label for _, label in fields]
        rows = []
        report_type = self.report_type.currentIndex()

        # الفلاتر
        institution = self.filter_institution.currentText()
        if institution == "كل المؤسسات":
            institution = ""
        leave_type = self.filter_type.currentText()
        if leave_type == "كل الأنواع":
            leave_type = ""
        status = self.filter_status.currentData()
        if not status:
            status = ""
        date_from = W.date_of(self.filter_date_from)
        date_to = W.date_of(self.filter_date_to)

        employees = self.ctx.db.list_employees(institution=institution, with_leaves=True)

        if report_type == 0:  # موظفين
            for emp in employees:
                row = []
                for key, _ in fields:
                    if key in ("raw_days", "net_days", "earned", "taken", "balance"):
                        bal = (
                            self.ctx.db.policy().compute_balance_for(emp)
                            if hasattr(self.ctx.db.policy(), "compute_balance_for")
                            else None
                        )
                        val = getattr(bal, key, "—") if bal else "—"
                    else:
                        val = getattr(emp, key, "")
                        if isinstance(val, date):
                            val = D.to_iso(val)
                    row.append(str(val) if val is not None else "")
                rows.append(row)
        elif report_type == 1:  # إجازات
            for emp in employees:
                for lv in emp.leaves:
                    if lv.is_deleted and not self.chk_include_deleted.isChecked():
                        continue
                    if leave_type and lv.type != leave_type:
                        continue
                    if status and lv.status != status:
                        continue
                    if date_from and lv.start_date and lv.start_date < date_from:
                        continue
                    if date_to and lv.start_date and lv.start_date > date_to:
                        continue
                    row = []
                    for key, _ in fields:
                        if key in EMPLOYEE_FIELDS:
                            val = getattr(emp, key, "")
                        else:
                            val = getattr(lv, key, "")
                        if isinstance(val, date):
                            val = D.to_iso(val)
                        row.append(str(val) if val is not None else "")
                    rows.append(row)
        else:  # أرصدة
            policy = self.ctx.db.policy()
            for emp in employees:
                from ..services import balance as B

                bal = B.compute_balance(emp, emp.leaves, policy)
                row = []
                for key, _ in fields:
                    if key in ("raw_days", "net_days", "earned", "taken", "balance"):
                        val = getattr(bal, key, "—")
                    else:
                        val = getattr(emp, key, "")
                        if isinstance(val, date):
                            val = D.to_iso(val)
                    row.append(str(val) if val is not None else "")
                rows.append(row)

        return headers, rows

    def _preview_report(self) -> None:
        """معاينة التقرير."""
        headers, rows = self._build_data()
        if not headers:
            return
        self.preview.set_rows(
            rows,
            headers=headers,
            empty_text="لا توجد بيانات مطابقة للفلاتر",
            footer=f"عدد الصفوف: {len(rows)}",
        )

    def _export_excel(self) -> None:
        """تصدير إلى Excel."""
        from PyQt6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self, "تصدير Excel", f"تقرير_{D.to_iso(date.today())}.xlsx", "Excel Files (*.xlsx)"
        )
        if not path:
            return
        headers, rows = self._build_data()
        if not headers:
            return
        try:
            from ..exporters.excel import _build_custom

            _build_custom(path, headers, rows, "تقرير مخصص")
            W.info(self, f"تم التصدير إلى:\n{path}")
        except Exception as exc:
            W.error(self, f"تعذّر التصدير: {exc}")

    def _export_pdf(self) -> None:
        """تصدير إلى PDF."""
        from PyQt6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self, "تصدير PDF", f"تقرير_{D.to_iso(date.today())}.pdf", "PDF Files (*.pdf)"
        )
        if not path:
            return
        headers, rows = self._build_data()
        if not headers:
            return
        try:
            from ..exporters.pdf import _build

            _build(Path(path), "تقرير مخصص", f"عدد الصفوف: {len(rows)}", headers, rows)
            W.info(self, f"تم التصدير إلى:\n{path}")
        except Exception as exc:
            W.error(self, f"تعذّر التصدير: {exc}")

    def _load_templates(self) -> None:
        """تحميل القوالب المحفوظة."""
        self.template_combo.clear()
        self.template_combo.insertItem(0, "— اختر قالب —")
        meta = self.ctx.db.get_meta()
        key = "custom_report_templates"
        if key in meta:
            try:
                templates = json.loads(meta[key])
                for name in templates:
                    self.template_combo.addItem(name)
            except (json.JSONDecodeError, TypeError):
                pass

    def _get_current_config(self) -> dict:
        """إرجاع إعدادات التقرير الحالية."""
        fields = []
        for i in range(self.fields_list.count()):
            item = self.fields_list.item(i)
            fields.append(
                {
                    "key": item.data(Qt.ItemDataRole.UserRole),
                    "checked": item.checkState() == Qt.CheckState.Checked,
                }
            )
        return {
            "report_type": self.report_type.currentIndex(),
            "fields": fields,
            "group_by": self.group_by.currentIndex(),
            "institution": self.filter_institution.currentText(),
            "leave_type": self.filter_type.currentText(),
            "status": self.filter_status.currentData() or "",
        }

    def _save_template(self) -> None:
        """حفظ القالب الحالي."""
        from PyQt6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "حفظ القالب", "اسم القالب:")
        if not ok or not name.strip():
            return
        name = name.strip()
        meta = self.ctx.db.get_meta()
        key = "custom_report_templates"
        templates = {}
        if key in meta:
            try:
                templates = json.loads(meta[key])
            except (json.JSONDecodeError, TypeError):
                pass
        templates[name] = self._get_current_config()
        self.ctx.db.set_meta({key: json.dumps(templates, ensure_ascii=False)})
        self._load_templates()
        self.template_combo.setCurrentText(name)
        W.info(self, f"تم حفظ القالب: {name}")

    def _load_template(self, name: str) -> None:
        """تحميل قالب محفوظ."""
        if not name or name == "— اختر قالب —":
            return
        meta = self.ctx.db.get_meta()
        key = "custom_report_templates"
        if key not in meta:
            return
        try:
            templates = json.loads(meta[key])
            cfg = templates[name]
            self.report_type.setCurrentIndex(cfg.get("report_type", 0))
            self._on_type_change()
            # استعادة الحقول
            fields_cfg = cfg.get("fields", [])
            for i in range(self.fields_list.count()):
                item = self.fields_list.item(i)
                key = item.data(Qt.ItemDataRole.UserRole)
                for fc in fields_cfg:
                    if fc["key"] == key:
                        item.setCheckState(
                            Qt.CheckState.Checked if fc["checked"] else Qt.CheckState.Unchecked
                        )
                        break
            self.group_by.setCurrentIndex(cfg.get("group_by", 0))
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    def _delete_template(self) -> None:
        """حذف قالب محفوظ."""
        name = self.template_combo.currentText()
        if not name or name == "— اختر قالب —":
            W.warn(self, "اختر قالباً للحذف.")
            return
        if not W.confirm(self, f"حذف القالب «{name}»؟"):
            return
        meta = self.ctx.db.get_meta()
        key = "custom_report_templates"
        if key in meta:
            try:
                templates = json.loads(meta[key])
                templates.pop(name, None)
                self.ctx.db.set_meta({key: json.dumps(templates, ensure_ascii=False)})
            except (json.JSONDecodeError, TypeError):
                pass
        self._load_templates()
        W.info(self, f"تم حذف القالب: {name}")
