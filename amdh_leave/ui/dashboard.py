"""لوحة المؤشرات: إحصاءات ورسوم بيانية بلا مكتبات خارجية."""

from __future__ import annotations

from PyQt6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout

from ..exporters import excel as X
from ..exporters import html as H
from ..services import reports
from . import theme, widgets as W
from .dialogs_base import BaseDialog
from ..i18n import tr, trf

MONTHS = ("كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران", "تموز",
          "آب", "أيلول", "تشرين الأول", "تشرين الثاني", "كانون الأول")


class DashboardDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, tr("لوحة المؤشرات"))
        self.policy = self.ctx.db.policy(refresh=True)
        self.resize(1180, 720)
        self._build()
        self._refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(W.title_label(tr("لوحة المؤشرات"), 16))
        header.addStretch()
        header.addWidget(W.button(tr("🔄 تحديث"), "Blue", self._refresh))
        header.addWidget(W.button("📊 Excel", "Ghost", self._export_excel))
        header.addWidget(W.button("📄 HTML", "Ghost", self._export_html))
        header.addWidget(self.close_button())
        layout.addLayout(header)

        self.kpi_grid = QGridLayout()
        self.kpis: dict[str, W.KPICard] = {}
        cards = [
            ("employees", "عدد الموظفين"), ("balance", "إجمالي الأرصدة"),
            ("earned", "إجمالي المستحقة"), ("taken", "إجمالي المأخوذة"),
            ("negative", "أرصدة سالبة (مسموح)"), ("on_leave_today", "على إجازة اليوم"),
            ("pending", "إجازات قيد الانتظار"), ("institutions", "عدد المؤسسات"),
        ]
        for i, (key, title) in enumerate(cards):
            card = W.KPICard(title)
            self.kpis[key] = card
            self.kpi_grid.addWidget(card, i // 4, i % 4)
        layout.addLayout(self.kpi_grid)

        charts = QHBoxLayout()
        self.chart_top = W.BarChart(value_suffix=" يوم")
        self.chart_inst = W.BarChart(value_suffix=" يوم")
        charts.addWidget(self.chart_top)
        charts.addWidget(self.chart_inst)
        layout.addLayout(charts)

        charts2 = QHBoxLayout()
        self.chart_type = W.BarChart(value_suffix=" يوم")
        self.chart_month = W.BarChart(value_suffix=" يوم")
        charts2.addWidget(self.chart_type)
        charts2.addWidget(self.chart_month)
        layout.addLayout(charts2)

        layout.addWidget(W.muted_label(tr("الموظفون على إجازة اليوم")))
        self.on_leave = W.TablePanel([tr("الاسم"), tr("الرقم الوظيفي"), tr("المؤسسة"), tr("النوع"), tr("من"), tr("إلى")])
        layout.addWidget(self.on_leave)

    # ------------------------------------------------------------------
    def _collect(self) -> dict:
        employees = self.ctx.employees()
        return reports.dashboard_data(employees, self.policy)

    def _refresh(self) -> None:
        self.policy = self.ctx.db.policy(refresh=True)
        data = self._collect()
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

        self.chart_top.set_data([(r["name"] or r["emp_id"], r["balance"]) for r in data["top"]],
                                "أعلى 10 أرصدة (يوم)")
        self.chart_inst.set_data([(k, v["balance"]) for k, v in data["by_institution"].items()],
                                 "إجمالي الرصيد حسب المؤسسة")
        self.chart_type.set_data([(k, v["days"]) for k, v in data["by_type"].items()],
                                 "أيام الإجازات حسب النوع")
        self.chart_month.set_data([(MONTHS[i], days) for i, days in enumerate(data["monthly"])],
                                  f"أيام الإجازات شهرياً لعام {data['year']}")

        rows = [[item["name"], item["emp_id"], item["institution"], item["type"],
                 item["start"], item["end"]] for item in data["on_leave"]]
        self.on_leave.set_rows(rows, empty_text=tr("لا يوجد موظفون في إجازة اليوم"),
                               footer=trf("العدد: {v0}", v0=len(rows)))

    # ------------------------------------------------------------------
    def _export_excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "حفظ لوحة المؤشرات", "dashboard.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            X.export_employees(path, self.data["rows"], title=tr("لوحة المؤشرات"))
            W.info(self, trf("تم التصدير:\n{v0}", v0=path))
        except Exception as exc:
            W.error(self, trf("فشل التصدير: {v0}", v0=exc))

    def _export_html(self) -> None:
        content = H.global_report_html(self.data["rows"], self.policy, "لوحة المؤشرات")
        path = H.save_and_open(content, self.ctx.paths.reports_dir, "dashboard.html")
        W.info(self, trf("تم فتح اللوحة في المتصفح:\n{v0}", v0=path.name))
