"""حوار «تصدير للمركز»: المؤسسة تلقائياً، والشهر الحالي أو فترة محددة."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from ..services import institutions as INST
from ..services import transfer as T
from . import theme
from . import widgets as W


def _month_bounds(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    first = today.replace(day=1)
    if first.month == 12:
        last = first.replace(year=first.year + 1, month=1, day=1)
    else:
        last = first.replace(month=first.month + 1, day=1)
    return first, date.fromordinal(last.toordinal() - 1)


class ExportToCenterDialog(QDialog):
    """تصدير ملف نقل مُوسَّم بالمؤسسة والفترة، مع أعداد وتنبيه قبل التنفيذ."""

    def __init__(self, parent, ctx, institution: str = "") -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.institution = institution or ctx.session.scoped_institution or ""
        self.result_path: Path | None = None
        self.setWindowTitle("تصدير للمركز")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumSize(620, 520)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        self._build()
        self._refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        title = QLabel("📤  تصدير بيانات المؤسسة إلى مركز الدائرة")
        title.setStyleSheet(theme.label_style("accent", 15, bold=True))
        layout.addWidget(title)
        layout.addWidget(
            W.muted_label(
                "يُصدَّر ملف نقل منقّى (بلا مستخدمين ولا سجل تدقيق) مع المرفقات، "
                "ثم يُسلَّم إلى المركز ليستورده من «استيراد من مؤسسة»."
            )
        )

        scope = W.card()
        scope_row = QHBoxLayout(scope)
        scope_row.addWidget(QLabel("المؤسسة:"))
        self.cb_institution = QComboBox()
        self.cb_institution.setMinimumWidth(260)
        if self.ctx.session.is_admin:
            self.cb_institution.addItem("كل المؤسسات", "")
            for item in self.ctx.db.list_institutions(active_only=True):
                self.cb_institution.addItem(item.name, item.name)
            index = self.cb_institution.findData(self.institution)
            self.cb_institution.setCurrentIndex(max(0, index))
            self.cb_institution.currentIndexChanged.connect(self._refresh)
        else:
            self.cb_institution.addItem(self.institution or "—", self.institution)
            self.cb_institution.setEnabled(False)
        scope_row.addWidget(self.cb_institution, 1)
        layout.addWidget(scope)

        period = QGroupBox("الفترة")
        period_layout = QVBoxLayout(period)
        row = QHBoxLayout()
        self.rb_month = QRadioButton("الشهر الحالي")
        self.rb_month.setChecked(True)
        self.rb_range = QRadioButton("فترة محددة (من / إلى)")
        group = QButtonGroup(self)
        group.addButton(self.rb_month)
        group.addButton(self.rb_range)
        row.addWidget(self.rb_month)
        row.addWidget(self.rb_range)
        row.addStretch()
        period_layout.addLayout(row)

        dates = QHBoxLayout()
        first, last = _month_bounds()
        self.dt_from = QDateEdit()
        self.dt_from.setCalendarPopup(True)
        self.dt_from.setDisplayFormat("yyyy-MM-dd")
        self.dt_from.setDate(QDate(first.year, first.month, first.day))
        self.dt_from.setEnabled(False)
        self.dt_to = QDateEdit()
        self.dt_to.setCalendarPopup(True)
        self.dt_to.setDisplayFormat("yyyy-MM-dd")
        self.dt_to.setDate(QDate(last.year, last.month, last.day))
        self.dt_to.setEnabled(False)
        dates.addWidget(QLabel("من:"))
        dates.addWidget(self.dt_from)
        dates.addWidget(QLabel("إلى:"))
        dates.addWidget(self.dt_to)
        dates.addStretch()
        period_layout.addLayout(dates)
        self.rb_range.toggled.connect(self._toggle_dates)
        layout.addWidget(period)

        stats = W.card()
        stats_layout = QHBoxLayout(stats)
        self.lbl_employees = W.LabeledValue("الموظفون")
        self.lbl_leaves = W.LabeledValue("الإجازات")
        self.lbl_attachments = W.LabeledValue("المرفقات")
        for widget in (self.lbl_employees, self.lbl_leaves, self.lbl_attachments):
            stats_layout.addWidget(widget)
        layout.addWidget(stats)

        self.lbl_last = W.muted_label("")
        self.lbl_warning = W.muted_label("")
        self.lbl_warning.setWordWrap(True)
        layout.addWidget(self.lbl_last)
        layout.addWidget(self.lbl_warning)

        self.lbl_file = W.muted_label("")
        layout.addWidget(self.lbl_file)
        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.addWidget(W.button("📤 تصدير", "Accent", self._export, width=130))
        buttons.addWidget(W.button("إلغاء", "Ghost", self.reject, width=90))
        buttons.addStretch()
        layout.addLayout(buttons)

    # ------------------------------------------------------------------
    def _toggle_dates(self, enabled: bool) -> None:
        self.dt_from.setEnabled(enabled)
        self.dt_to.setEnabled(enabled)

    def _selected_institution(self) -> str:
        if self.ctx.session.is_admin:
            return str(self.cb_institution.currentData() or "")
        return self.institution

    def _period(self) -> tuple[str, str]:
        if self.rb_month.isChecked():
            first, last = _month_bounds()
        else:
            first = self.dt_from.date().toPyDate()
            last = self.dt_to.date().toPyDate()
            if last < first:
                first, last = last, first
        return first.isoformat(), last.isoformat()

    def _code(self, institution: str) -> str:
        if not institution:
            return "ALL"
        record = self.ctx.db.get_institution(institution)
        return (record.code if record and record.code else "INST").replace(" ", "_")

    def _default_name(self) -> str:
        institution = self._selected_institution()
        first, last = self._period()
        label = first[:7] if first[:7] == last[:7] else f"{first}_{last}"
        return f"AMDH_{self._code(institution)}_{label}.amdhz"

    def _last_export(self, institution: str) -> str:
        if institution:
            record = self.ctx.db.get_institution(institution)
            return record.last_export_at if record else ""
        dates = [item.last_export_at for item in self.ctx.db.list_institutions() if item.last_export_at]
        return max(dates) if dates else ""

    def _refresh(self) -> None:
        institution = self._selected_institution()
        counts = INST.institution_counts(self.ctx.db, institution)
        self.lbl_employees.set_value(counts["employees"], "accent", " موظف")
        self.lbl_leaves.set_value(counts["leaves"], "gold", " إجازة")
        self.lbl_attachments.set_value(counts["attachments"], "blue", " مرفق")
        last = self._last_export(institution)
        self.lbl_last.setText(f"آخر تصدير: {last or 'لا يوجد'}")
        changed = INST.last_change_at(self.ctx.db, institution)
        if last and changed and changed <= last:
            self.lbl_warning.setText(
                "⚠ لم تتغيّر بيانات هذه المؤسسة منذ آخر تصدير — يمكنك التصدير على أي حال."
            )
            self.lbl_warning.setStyleSheet(theme.label_style("gold", 10))
        elif not last:
            self.lbl_warning.setText("ℹ هذه أول عملية تصدير لهذه المؤسسة.")
            self.lbl_warning.setStyleSheet(theme.label_style("muted", 10))
        else:
            self.lbl_warning.setText("")
        self.lbl_file.setText(f"اسم الملف المقترح: {self._default_name()}")
        self._toggle_dates(self.rb_range.isChecked())

    # ------------------------------------------------------------------
    def _export(self) -> None:
        institution = self._selected_institution()
        if self.ctx.session.is_admin and not institution:
            if not W.confirm(self, "لم تختر مؤسسة؛ سيُصدَّر ملف «كل المؤسسات». متابعة؟"):
                return
        first, last = self._period()
        default = self.ctx.paths.reports_dir / self._default_name()
        path, _ = QFileDialog.getSaveFileName(
            self, "حفظ ملف النقل", str(default), "أرشيف نقل (*.amdhz);;قاعدة بيانات (*.db)"
        )
        if not path:
            return
        include_attachments = True
        if Path(path).suffix.lower() == ".db":
            include_attachments = W.confirm(
                self,
                "ملف .db لا يحمل المرفقات.\n\nهل تريد المتابعة بلا مرفقات؟\n"
                "(اختر «لا» لتصدير أرشيف .amdhz مع المرفقات)",
                "تنبيه المرفقات",
            )
            if not include_attachments:
                path = str(Path(path).with_suffix(".amdhz"))
        try:
            manifest = T.export_transfer(
                self.ctx.db,
                path,
                institution=institution,
                include_attachments=include_attachments,
                user=self.ctx.user(),
                attachments_dir=self.ctx.paths.attachments_dir,
                period=(first, last),
                center=self.ctx.db.center_institution(),
            )
        except Exception as exc:  # noqa: BLE001
            W.error(self, f"تعذّر التصدير: {exc}")
            return
        output = Path(manifest["path"])
        counts = manifest.get("counts", {})
        self.result_path = output
        W.info(
            self,
            f"تم إنشاء ملف النقل:\n{output}\n\n"
            f"المؤسسة: {manifest.get('institution') or 'كل المؤسسات'}\n"
            f"الفترة: {first} ← {last}\n"
            f"الموظفون: {counts.get('employees', 0)} | "
            f"الإجازات: {counts.get('leaves', 0)} | "
            f"المرفقات: {counts.get('attachments', 0)}\n\n"
            "سلّم هذا الملف إلى مركز الدائرة ليستورده من «استيراد من مؤسسة».",
            "تم التصدير",
        )
        if W.confirm(self, "هل تريد فتح مجلد الملف الآن؟"):
            W.open_path(self, output.parent)
        self.accept()


def export_for_center(parent, ctx, institution: str = "") -> Path | None:
    dialog = ExportToCenterDialog(parent, ctx, institution)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.result_path
    return None
