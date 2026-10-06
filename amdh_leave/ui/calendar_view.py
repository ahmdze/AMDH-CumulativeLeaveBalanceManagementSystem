"""تقويم الإجازات الشهري (شبكة أيام تعرض من هو في إجازة)."""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from ..exporters import excel as X
from ..exporters import html as H
from ..services import dates as D
from ..services import reports
from . import theme, widgets as W
from .dialogs_base import BaseDialog

MONTHS = ("كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران", "تموز",
          "آب", "أيلول", "تشرين الأول", "تشرين الثاني", "كانون الأول")


class CalendarDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, "تقويم الإجازات")
        self.policy = self.ctx.db.policy(refresh=True)
        today = date.today()
        self.year = today.year
        self.month = today.month
        self.resize(1180, 700)
        self._build()
        self._refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(W.title_label("تقويم الإجازات", 16))
        header.addWidget(W.button("◀ السابق", "Ghost", lambda: self._shift(-1)))
        header.addWidget(W.button("اليوم", "Blue", self._go_today))
        header.addWidget(W.button("التالي ▶", "Ghost", lambda: self._shift(1)))
        self.cb_month = QComboBox()
        self.cb_month.addItems(MONTHS)
        self.cb_month.currentIndexChanged.connect(self._on_month_changed)
        header.addWidget(self.cb_month)
        self.cb_year = QComboBox()
        for year in range(date.today().year - 6, date.today().year + 3):
            self.cb_year.addItem(str(year), year)
        self.cb_year.currentIndexChanged.connect(self._on_month_changed)
        header.addWidget(self.cb_year)
        header.addStretch()
        header.addWidget(W.button("📊 Excel", "Ghost", self._export_excel))
        header.addWidget(W.button("📄 HTML", "Ghost", self._export_html))
        header.addWidget(self.close_button())
        layout.addLayout(header)

        self.days_table = QTableWidget()
        W.setup_table(self.days_table, sortable=False)
        self.days_table.setColumnCount(7)
        self.days_table.setRowCount(6)
        self.days_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.days_table.verticalHeader().setVisible(True)
        self.days_table.itemSelectionChanged.connect(self._on_day_selected)
        layout.addWidget(self.days_table, 3)

        self.detail_label = W.muted_label("اختر يوماً لعرض تفاصيله")
        layout.addWidget(self.detail_label)
        self.detail = W.TablePanel(["الاسم", "الرقم الوظيفي", "المؤسسة", "النوع", "من", "إلى"],
                                   sortable=False)
        layout.addWidget(self.detail, 2)
        self._fill_headers()

    def _fill_headers(self) -> None:
        labels = D.weekday_labels(self.policy.first_day_of_week)
        self.days_table.setHorizontalHeaderLabels(labels)

    # ------------------------------------------------------------------
    def _shift(self, delta: int) -> None:
        month = self.month + delta
        year = self.year
        if month < 1:
            month, year = 12, year - 1
        elif month > 12:
            month, year = 1, year + 1
        self.month, self.year = month, year
        self._sync_controls()
        self._refresh()

    def _go_today(self) -> None:
        today = date.today()
        self.year, self.month = today.year, today.month
        self._sync_controls()
        self._refresh()

    def _on_month_changed(self) -> None:
        self.month = self.cb_month.currentIndex() + 1
        self.year = self.cb_year.currentData() or self.year
        self._refresh()

    def _sync_controls(self) -> None:
        for widget in (self.cb_month, self.cb_year):
            widget.blockSignals(True)
        self.cb_month.setCurrentIndex(self.month - 1)
        index = self.cb_year.findData(self.year)
        if index < 0:
            self.cb_year.addItem(str(self.year), self.year)
            index = self.cb_year.findData(self.year)
        self.cb_year.setCurrentIndex(index)
        for widget in (self.cb_month, self.cb_year):
            widget.blockSignals(False)

    def _refresh(self) -> None:
        self.policy = self.ctx.db.policy(refresh=True)
        self._fill_headers()
        employees = self.ctx.employees()
        self.data = reports.calendar_month(employees, self.policy, self.year, self.month)
        grid = self.data["grid"]
        per_day = self.data["per_day"]
        today = date.today()

        self.days_table.blockSignals(True)
        self.days_table.clearContents()
        for r, week in enumerate(grid[:6]):
            for c, day in enumerate(week):
                item = QTableWidgetItem()
                if day is None:
                    item.setText("")
                    self.days_table.setItem(r, c, item)
                    continue
                items = per_day.get(day, [])
                names = "\n".join(f"{emp.name} ({lv.type})" for emp, lv in items[:4])
                if len(items) > 4:
                    names += f"\n+{len(items) - 4} أخرى"
                item.setText(f"{day.day}\n{names}" if names else str(day.day))
                item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
                weekend = D.is_weekend(day, self.policy.weekend)
                holiday = day in self.policy.holidays
                if holiday:
                    item.setBackground(QColor(theme.color("gold")))
                elif weekend:
                    item.setBackground(QColor(theme.color("card")))
                elif day == today:
                    item.setForeground(QColor(theme.color("accent")))
                item.setData(Qt.ItemDataRole.UserRole, day)
                self.days_table.setItem(r, c, item)
        self.days_table.blockSignals(False)
        self.days_table.resizeRowsToContents()

        count = sum(len(v) for v in per_day.values())
        self.detail_label.setText(
            f"{MONTHS[self.month - 1]} {self.year} — عدد أيام الإجازات المسجلة: {count}"
            + ("  (الخلايا الذهبية عطل رسمية، والداكنة عطلة أسبوعية)" if count else ""))

    # ------------------------------------------------------------------
    def _on_day_selected(self) -> None:
        row = self.days_table.currentRow()
        col = self.days_table.currentColumn()
        item = self.days_table.item(row, col) if row >= 0 and col >= 0 else None
        day = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not day:
            self.detail.set_rows([], empty_text="اختر يوماً فيه إجازات")
            return
        entries = self.data["per_day"].get(day, [])
        rows = [[emp.name, emp.emp_id, emp.institution, lv.type,
                 D.to_iso(lv.start_date), D.to_iso(lv.end_date)] for emp, lv in entries]
        self.detail.set_rows(rows, empty_text=f"لا توجد إجازات في {D.to_iso(day)}",
                             footer=f"تاريخ مختار: {D.to_iso(day)} — العدد: {len(rows)}")

    # ------------------------------------------------------------------
    def _export_excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "حفظ التقويم",
                                              f"calendar_{self.year}_{self.month:02d}.xlsx",
                                              "Excel (*.xlsx)")
        if not path:
            return
        try:
            if not X.HAS_XLSX:
                raise RuntimeError("مكتبة openpyxl غير مثبتة.")
            import openpyxl
            from openpyxl.styles import Alignment, Font, PatternFill
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "التقويم"
            ws.sheet_view.rightToLeft = True
            ws.append(D.weekday_labels(self.policy.first_day_of_week))
            for cell in ws[1]:
                cell.font = Font(bold=True, color="7DD3C8")
                cell.fill = PatternFill("solid", fgColor="1C2D3E")
            for week in self.data["grid"]:
                row_values = []
                for day in week:
                    if day is None:
                        row_values.append("")
                        continue
                    items = self.data["per_day"].get(day, [])
                    text = str(day.day)
                    if items:
                        text += "\n" + "\n".join(f"{e.name} ({lv.type})" for e, lv in items)
                    row_values.append(text)
                ws.append(row_values)
            for column in ws.columns:
                ws.column_dimensions[column[0].column_letter].width = 30
            for row in ws.iter_rows(min_row=2):
                for cell in row:
                    cell.alignment = Alignment(wrap_text=True, vertical="top", horizontal="right")
            wb.save(path)
            W.info(self, f"تم التصدير:\n{path}")
        except Exception as exc:
            W.error(self, f"فشل التصدير: {exc}")

    def _export_html(self) -> None:
        content = H.calendar_html(self.data, self.policy,
                                  self.ctx.session.scoped_institution)
        path = H.save_and_open(content, self.ctx.paths.reports_dir,
                               f"calendar_{self.year}_{self.month:02d}.html")
        W.info(self, f"تم فتح التقويم في المتصفح:\n{path.name}")
