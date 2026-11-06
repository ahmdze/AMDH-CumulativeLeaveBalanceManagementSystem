"""مركز الإشعارات والتنبيهات."""

from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QVBoxLayout

from ..exporters import excel as X
from ..exporters import html as H
from ..services import reports
from . import theme
from . import widgets as W
from .dialogs_base import BaseDialog

KIND_LABELS = {
    "negative_balance": "رصيد سالب (مسموح)",
    "low_balance": "رصيد منخفض",
    "ending_soon": "إجازة تنتهي قريباً",
    "started_today": "بدء إجازة",
    "pending": "قيد الانتظار",
    "service_ending": "قرب انتهاء الخدمة",
    "missing_data": "بيانات ناقصة",
}


class NotificationsDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, "الإشعارات والتنبيهات")
        self.policy = self.ctx.db.policy(refresh=True)
        self.resize(1000, 640)
        self._build()
        self._refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(W.title_label("الإشعارات والتنبيهات", 16))
        header.addStretch()
        self.cb_severity = QComboBox()
        self.cb_severity.addItem("كل الأهميات", "")
        for key, label in reports.SEVERITY_LABELS.items():
            self.cb_severity.addItem(label, key)
        self.cb_severity.currentIndexChanged.connect(self._apply_filter)
        self.cb_kind = QComboBox()
        self.cb_kind.addItem("كل الأنواع", "")
        for key, label in KIND_LABELS.items():
            self.cb_kind.addItem(label, key)
        self.cb_kind.currentIndexChanged.connect(self._apply_filter)
        header.addWidget(self.cb_severity)
        header.addWidget(self.cb_kind)
        header.addWidget(W.button("🔄 تحديث", "Blue", self._refresh))
        header.addWidget(W.button("📊 Excel", "Ghost", self._export_excel))
        header.addWidget(W.button("📄 HTML", "Ghost", self._export_html))
        header.addWidget(self.close_button())
        layout.addLayout(header)

        self.note = W.muted_label("الرصيد السالب مسموح حسب الضوابط الإدارية ويُعرض كمعلومة لا كخطأ.")
        layout.addWidget(self.note)
        self.table = W.TablePanel(
            ["الأهمية", "النوع", "الموظف", "الرقم الوظيفي", "المؤسسة", "التاريخ", "التنبيه"]
        )
        layout.addWidget(self.table)
        self.footer = QLabel("")
        self.footer.setStyleSheet(theme.label_style("muted"))
        layout.addWidget(self.footer)

    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        self.policy = self.ctx.db.policy(refresh=True)
        employees = self.ctx.employees()
        self.alerts = reports.collect_alerts(employees, self.policy)
        self._apply_filter()

    def _apply_filter(self) -> None:
        severity = self.cb_severity.currentData() or ""
        kind = self.cb_kind.currentData() or ""
        items = [
            a
            for a in self.alerts
            if (not severity or a.severity == severity) and (not kind or a.kind == kind)
        ]
        self.filtered = items
        colors = {"high": theme.color("neg"), "medium": theme.color("gold"), "info": theme.color("muted")}
        rows = []
        row_colors = {}
        for i, alert in enumerate(items):
            rows.append(
                [
                    reports.SEVERITY_LABELS.get(alert.severity, alert.severity),
                    KIND_LABELS.get(alert.kind, alert.kind),
                    alert.name,
                    alert.emp_id,
                    alert.institution,
                    alert.day.strftime("%Y-%m-%d") if alert.day else "",
                    alert.message,
                ]
            )
            row_colors[(i, 0)] = colors.get(alert.severity, theme.color("text"))
        self.table.set_rows(rows, colors=row_colors, empty_text="لا توجد تنبيهات مطابقة")
        counts = {key: len([a for a in self.alerts if a.severity == key]) for key in reports.SEVERITY_LABELS}
        self.footer.setText(
            f"الإجمالي: {len(self.alerts)} | مهم: {counts['high']} | متوسط: {counts['medium']} | "
            f"معلومة: {counts['info']} | المعروض: {len(items)}"
        )

    # ------------------------------------------------------------------
    def _export_excel(self) -> None:
        if not self.filtered:
            W.warn(self, "لا توجد تنبيهات للتصدير.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "حفظ التنبيهات", "alerts.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            X.export_alerts(path, self.filtered)
            W.info(self, f"تم التصدير:\n{path}")
        except Exception as exc:
            W.error(self, f"فشل التصدير: {exc}")

    def _export_html(self) -> None:
        content = H.alerts_html(self.filtered, self.policy)
        path = H.save_and_open(content, self.ctx.paths.reports_dir, "alerts.html")
        W.info(self, f"تم فتح التقرير في المتصفح:\n{path.name}")
