"""لوحة المؤشرات: إحصاءات ورسوم بيانية بلا مكتبات خارجية."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QScrollArea,
    QVBoxLayout, QWidget,
)

from ..exporters import excel as X
from ..exporters import html as H
from ..services import reports
from . import theme, widgets as W
from .dialogs_base import BaseDialog

MONTHS = ("كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران", "تموز",
          "آب", "أيلول", "تشرين الأول", "تشرين الثاني", "كانون الأول")


class DashboardDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, "لوحة المؤشرات")
        self.policy = self.ctx.db.policy(refresh=True)
        self.resize(980, 650)
        self._filter_institution = ""
        self._build()
        self._refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)

        # الشريط العلوي (خارج الـ scroll)
        header = QHBoxLayout()
        header.addWidget(W.title_label("لوحة المؤشرات", 16))
        header.addStretch()

        # فلتر المؤسسة
        self.cb_institution = QComboBox()
        self.cb_institution.addItem("الكل", "")
        institutions = self.ctx.db.distinct_values("institution")
        for inst in institutions:
            self.cb_institution.addItem(inst, inst)
        self.cb_institution.currentTextChanged.connect(self._on_filter_change)
        header.addWidget(W.muted_label("المؤسسة:"))
        header.addWidget(self.cb_institution, 0, Qt.AlignmentFlag.AlignVCenter)

        header.addWidget(W.button("🔄 تحديث", "Blue", self._refresh))
        header.addWidget(W.button("📊 Excel", "Ghost", self._export_excel))
        header.addWidget(W.button("📄 HTML", "Ghost", self._export_html))
        header.addWidget(self.close_button())
        layout.addLayout(header)

        # Scroll area للمحتوى الكبير
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget()
        content_layout = QVBoxLayout(content)

        self.kpi_grid = QGridLayout()
        self.kpis: dict[str, W.KPICard] = {}
        cards = [
            ("employees", "عدد الموظفين"), ("balance", "إجمالي الأرصدة"),
            ("earned", "إجمالي المستحقة"), ("taken", "إجمالي المأخوذة"),
            ("negative", "أرصدة سالبة (مسموح)"), ("on_leave_today", "على إجازة اليوم"),
            ("pending", "إجازات قيد الانتظار"), ("institutions", "عدد المؤسسات"),
            ("avg_balance", "متوسط الرصيد"), ("most_used_type", "أكثر نوع استخداماُ"),
            ("consumption_rate", "نسبة الاستهلاك"), ("low_balance", "أرصدة منخفضة"),
        ]
        for i, (key, title) in enumerate(cards):
            card = W.KPICard(title)
            self.kpis[key] = card
            self.kpi_grid.addWidget(card, i // 4, i % 4)
        content_layout.addLayout(self.kpi_grid)

        # الصف الأول: أعلى أرصدة + رسم دائري
        charts = QHBoxLayout()
        self.chart_top = W.BarChart(value_suffix=" يوم")
        self.chart_pie = W.PieChart()
        charts.addWidget(self.chart_top)
        charts.addWidget(self.chart_pie)
        content_layout.addLayout(charts)

        # الصف الثاني: رسم خطي + رسم أعمدة حسب المؤسسة
        charts2 = QHBoxLayout()
        self.chart_month = W.LineChart()
        self.chart_inst = W.BarChart(value_suffix=" يوم")
        charts2.addWidget(self.chart_month)
        charts2.addWidget(self.chart_inst)
        content_layout.addLayout(charts2)

        content_layout.addWidget(W.muted_label("الموظفون على إجازة اليوم"))
        self.on_leave = W.TablePanel(["الاسم", "الرقم الوظيفي", "المؤسسة", "النوع", "من", "إلى"])
        content_layout.addWidget(self.on_leave)

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _on_filter_change(self, text: str) -> None:
        self._filter_institution = self.cb_institution.currentData() or ""
        self._refresh()

    # ------------------------------------------------------------------
    def _collect(self) -> dict:
        employees = self.ctx.employees()
        if self._filter_institution:
            employees = [e for e in employees if e.institution == self._filter_institution]
        data = reports.dashboard_data(employees, self.policy)
        stats = reports.advanced_statistics(employees, self.policy)
        return data, stats

    def _refresh(self) -> None:
        self.policy = self.ctx.db.policy(refresh=True)
        data, stats = self._collect()
        self.data = data
        kpis = data["kpis"]
        self.kpis["employees"].set_value(kpis["employees"])
        self.kpis["balance"].set_value(kpis["balance"], theme.balance_color(kpis["balance"]), " يوم")
        self.kpis["earned"].set_value(kpis["earned"], "pos", " يوم")
        self.kpis["taken"].set_value(kpis["taken"], "gold", " يوم")
        self.kpis["negative"].set_value(kpis["negative"], "neg" if kpis["negative"] else "muted")
        self.kpis["on_leave_today"].set_value(kpis["on_leave_today"])
        self.kpis["pending"].set_value(kpis["pending"], "gold" if kpis["pending"] else "muted")
        self.kpis["institutions"].set_value(kpis["institutions"])
        # KPIs جديدة
        self.kpis["avg_balance"].set_value(f"{stats['avg_balance']:.1f}", "accent", " يوم")
        self.kpis["most_used_type"].set_value(stats["most_used_type"] or "—")
        self.kpis["consumption_rate"].set_value(f"{stats['consumption_rate']:.1f}%", 
                                                "gold" if stats["consumption_rate"] > 80 else "pos")
        self.kpis["low_balance"].set_value(kpis.get("low_balance", 0), 
                                           "neg" if kpis.get("low_balance") else "muted")

        self.chart_top.set_data([(r["name"] or r["emp_id"], r["balance"]) for r in data["top"]],
                                "أعلى 10 أرصدة (يوم)")
        self.chart_inst.set_data([(k, v["balance"]) for k, v in data["by_institution"].items()],
                                 "إجمالي الرصيد حسب المؤسسة")
        # رسم دائري للإجازات حسب النوع
        self.chart_pie.set_data([(k, v["days"]) for k, v in data["by_type"].items()],
                                "توزيع الإجازات حسب النوع")
        # رسم خطي شهري
        self.chart_month.set_data([(MONTHS[i], days) for i, days in enumerate(data["monthly"])],
                                  f"أيام الإجازات شهرياً لعام {data['year']}")

        rows = [[item["name"], item["emp_id"], item["institution"], item["type"],
                 item["start"], item["end"]] for item in data["on_leave"]]
        self.on_leave.set_rows(rows, empty_text="لا يوجد موظفون في إجازة اليوم",
                               footer=f"العدد: {len(rows)}")

    # ------------------------------------------------------------------
    def _export_excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "حفظ لوحة المؤشرات", "dashboard.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            X.export_employees(path, self.data["rows"], title="لوحة المؤشرات")
            W.info(self, f"تم التصدير:\n{path}")
        except Exception as exc:
            W.error(self, f"فشل التصدير: {exc}")

    def _export_html(self) -> None:
        content = H.global_report_html(self.data["rows"], self.policy, "لوحة المؤشرات")
        path = H.save_and_open(content, self.ctx.paths.reports_dir, "dashboard.html")
        W.info(self, f"تم فتح اللوحة في المتصفح:\n{path.name}")
