"""بحث متقدم متعدد المعايير للإجازات."""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDateEdit, QFormLayout, QHBoxLayout, QLabel,
    QVBoxLayout, QWidget,
)

from ..services.dates import parse_iso, to_iso
from . import widgets as W
from .dialogs_base import BaseDialog


class AdvancedSearchDialog(BaseDialog):
    """نافذة بحث متقدم للإجازات بفلترة متعددة المعايير."""

    def __init__(self, parent=None, ctx=None, refresh_callback=None):
        super().__init__(parent, ctx, "بحث متقدم")
        self.refresh_callback = refresh_callback
        self.resize(520, 480)
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)

        # البحث بالاسم أو الرقم الوظيفي
        self.e_name = W.search_line("الاسم أو الرقم الوظيفي...")
        layout.addWidget(self.e_name)

        card = W.card()
        form = QFormLayout(card)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # نوع الإجازة
        self.cb_type = QComboBox()
        self.cb_type.addItem("الكل", "")
        rules = self.ctx.db.list_rules()
        for r in rules:
            self.cb_type.addItem(r, r)
        form.addRow("نوع الإجازة:", self.cb_type)

        # حالة الإجازة
        self.cb_status = QComboBox()
        self.cb_status.addItem("الكل", "")
        self.cb_status.addItem("مقبول", "approved")
        self.cb_status.addItem("قيد الانتظار", "pending")
        self.cb_status.addItem("مرفوض", "rejected")
        form.addRow("الحالة:", self.cb_status)

        # المؤسسة
        self.cb_institution = QComboBox()
        self.cb_institution.addItem("الكل", "")
        institutions = self.ctx.db.distinct_values("institution")
        for inst in institutions:
            self.cb_institution.addItem(inst, inst)
        form.addRow("المؤسسة:", self.cb_institution)

        # تاريخ من
        self.d_from = QDateEdit()
        self.d_from.setCalendarPopup(True)
        self.d_from.setDate(date(2020, 1, 1))
        self.d_from.setDisplayFormat("yyyy-MM-dd")
        form.addRow("تاريخ من:", self.d_from)

        # تاريخ إلى
        self.d_to = QDateEdit()
        self.d_to.setCalendarPopup(True)
        self.d_to.setDate(date.today())
        self.d_to.setDisplayFormat("yyyy-MM-dd")
        form.addRow("تاريخ إلى:", self.d_to)

        layout.addWidget(card)

        # نتائج
        self.lbl_results = W.muted_label("")
        layout.addWidget(self.lbl_results)

        self.results_table = W.TablePanel([
            "الاسم", "الرقم الوظيفي", "النوع", "من", "إلى",
            "الأيام", "الحالة", "المؤسسة"
        ])
        layout.addWidget(self.results_table)

        # أزرار
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(W.button("🔍 بحث", "Accent", self._search))
        buttons.addWidget(W.button("📊 Excel", "Ghost", self._export_excel))
        buttons.addWidget(self.close_button())
        layout.addLayout(buttons)

    # ------------------------------------------------------------------
    def _search(self) -> None:
        name_q = self.e_name.text().strip()
        leave_type = self.cb_type.currentData() or ""
        status = self.cb_status.currentData() or ""
        institution = self.cb_institution.currentData() or ""
        date_from = self.d_from.date().toPyDate()
        date_to = self.d_to.date().toPyDate()

        # جلب كل الإجازات
        all_leaves = self.ctx.db.all_leaves(include_deleted=False)
        employees = self.ctx.db.list_employees(with_leaves=False)
        emp_map = {e.emp_id: e for e in employees}

        results = []
        for lv in all_leaves:
            emp = emp_map.get(lv.emp_id)
            if not emp:
                continue

            # فلترة الاسم/الرقم
            if name_q:
                search_in = f"{emp.name} {emp.emp_id}".lower()
                if name_q.lower() not in search_in:
                    continue

            # فلترة النوع
            if leave_type and lv.type != leave_type:
                continue

            # فلترة الحالة
            if status and lv.status != status:
                continue

            # فلترة المؤسسة
            if institution and emp.institution != institution:
                continue

            # فلترة التاريخ
            if lv.start_date:
                if lv.start_date < date_from or lv.start_date > date_to:
                    continue

            status_label = {"approved": "مقبول", "pending": "قيد الانتظار",
                           "rejected": "مرفوض"}.get(lv.status, lv.status or "")
            results.append([
                emp.name, emp.emp_id, lv.type or "",
                to_iso(lv.start_date) if lv.start_date else "",
                to_iso(lv.end_date) if lv.end_date else "",
                lv.days_actual or 0,
                status_label,
                emp.institution or ""
            ])

        results.sort(key=lambda r: r[3], reverse=True)
        self.results_table.set_rows(
            results,
            empty_text="لا توجد نتائج مطابقة",
            footer=f"العدد: {len(results)}"
        )
        self.lbl_results.setText(f"تم العثور على {len(results)} نتيجة")

    def _export_excel(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        from ..exporters import excel as X

        rows = self.results_table.get_rows()
        if not rows:
            W.warn(self, "لا توجد نتائج للتصدير")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "تصدير نتائج البحث", "search_results.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            X.export_employees(path, rows, title="نتائج البحث المتقدم")
            W.info(self, f"تم التصدير:\n{path}")
        except Exception as exc:
            W.error(self, f"فشل التصدير: {exc}")
