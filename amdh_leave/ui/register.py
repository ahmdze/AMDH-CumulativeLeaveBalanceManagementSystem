"""سجل إجازات الموظف (نافذة منفصلة) مع تصدير ومرفقات وحالة الطلب."""

from __future__ import annotations

from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout

from .. import config
from ..exporters import excel as X
from ..exporters import html as H
from ..exporters import pdf as P
from ..services import balance as B
from ..services import dates as D
from . import theme, widgets as W
from .dialogs_base import BaseDialog
from .dialogs_leave import AttachmentsDialog, LeaveDialog
from ..i18n import tr, trf


class LeavesRegisterDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None, emp_id: str = "", on_save=None):
        super().__init__(parent, ctx, tr("سجل الإجازات"))
        self.emp_id = emp_id
        self.on_save = on_save
        self.policy = self.ctx.db.policy(refresh=True)
        self.resize(1120, 640)
        self._build()
        self._refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        employee = self.ctx.db.get_employee(self.emp_id)
        name = employee.name if employee else self.emp_id
        layout.addWidget(W.title_label(trf("سجل إجازات: {v0}", v0=name), 15))

        summary = W.card()
        summary_layout = QHBoxLayout(summary)
        self.lbls: dict[str, W.LabeledValue] = {}
        for key, title in (("raw_days", "أيام الخدمة"), ("outside", "خارج الرصيد"),
                           ("net_days", "الدوام المحسوبة"), ("earned", "المستحقة"),
                           ("taken", "المأخوذة"), ("balance", "الرصيد")):
            widget = W.LabeledValue(title)
            self.lbls[key] = widget
            summary_layout.addWidget(widget)
        layout.addWidget(summary)

        row = QHBoxLayout()
        row.addWidget(W.button(tr("➕ إضافة إجازة"), "Accent", self._add))
        row.addWidget(W.button(tr("✏ تعديل المحددة"), "Blue", self._edit))
        row.addWidget(W.button(tr("🗑 حذف المحددة"), "Warn", self._delete))
        row.addWidget(W.button(tr("📎 مرفقات"), "Ghost", self._attachments))
        row.addWidget(W.button(tr("📄 كشف الحساب"), "Gold", self._statement))
        row.addStretch()
        row.addWidget(W.button("📊 Excel", "Ghost", self._export_excel))
        row.addWidget(W.button("📄 PDF", "Ghost", self._export_pdf))
        row.addWidget(W.button(tr("🖨 طباعة"), "Blue", self._print))
        layout.addLayout(row)

        self.table = W.TablePanel(["#", tr("النوع"), tr("من"), tr("إلى"), tr("العدد"), tr("الأيام المؤثرة"),
                                   tr("أيام العمل"), tr("خارج الرصيد"), tr("الحالة"), tr("الأمر"), tr("تاريخ الأمر"),
                                   tr("السبب"), tr("أُضيفت في"), tr("بواسطة")])
        layout.addWidget(self.table)
        layout.addLayout(self.buttons_row(self.close_button()))

    # ------------------------------------------------------------------
    def _leaves(self):
        return [lv for lv in self.ctx.db.list_leaves(self.emp_id)]

    def _refresh(self) -> None:
        employee = self.ctx.db.get_employee(self.emp_id)
        if not employee:
            W.error(self, tr("الموظف غير موجود."))
            self.reject()
            return
        self.employee = employee
        self.leaves = self._leaves()
        balance = B.compute_balance(employee, employee.leaves, self.policy)
        for key in ("raw_days", "outside", "net_days", "earned", "taken", "balance"):
            value = getattr(balance, key)
            key_color = theme.balance_color(balance.balance, self.policy.low_balance_days) \
                if key == "balance" else "text"
            if key == "earned":
                key_color = "pos"
            if key == "taken":
                key_color = "gold"
            self.lbls[key].set_value(value, key_color, " يوم")

        rows = []
        for i, lv in enumerate(self.leaves, 1):
            start, end = B.leave_span(lv)
            rows.append([
                i, lv.type, D.to_iso(start), D.to_iso(end), f"{lv.amount} {lv.unit}",
                lv.days_actual, lv.working_days,
                "نعم" if B.is_service_exclusion(self.policy, lv) else "لا",
                config.LEAVE_STATUS_LABELS.get(lv.status, lv.status),
                lv.order, D.to_iso(lv.order_date), lv.reason, lv.added_date, lv.created_by,
            ])
        colors = {}
        for i, lv in enumerate(self.leaves):
            if lv.status == "pending":
                colors[(i, 8)] = theme.color("gold")
            elif lv.status == "rejected":
                colors[(i, 8)] = theme.color("neg")
            if lv.is_adjustment:
                colors[(i, 1)] = theme.color("gold")
        self.table.set_rows(rows, numeric_columns={4, 5, 6}, colors=colors,
                            empty_text=tr("لا توجد إجازات مسجلة لهذا الموظف"),
                            footer=trf("عدد الإجازات: {v0}", v0=len(rows)))

    def _selected_leave(self):
        row = self.table.current_row()
        if row < 0 or row >= len(self.leaves):
            W.warn(self, tr("حدد إجازة أولاً."))
            return None
        return self.leaves[row]

    # ------------------------------------------------------------------
    def _add(self) -> None:
        if not self.ctx.can("edit_leave"):
            W.error(self, tr("لا تملك صلاحية تسجيل الإجازات."))
            return
        LeaveDialog(self, self.ctx, self.emp_id, on_save=self._saved).exec()

    def _edit(self) -> None:
        leave = self._selected_leave()
        if not leave:
            return
        if not self.ctx.can("edit_leave"):
            W.error(self, tr("لا تملك صلاحية تعديل الإجازات."))
            return
        LeaveDialog(self, self.ctx, self.emp_id, leave_id=leave.id, on_save=self._saved).exec()

    def _delete(self) -> None:
        leave = self._selected_leave()
        if not leave:
            return
        if not self.ctx.can("delete_leave"):
            W.error(self, tr("لا تملك صلاحية حذف الإجازات."))
            return
        if not W.confirm(self, f"حذف إجازة «{leave.type}» بتاريخ {D.to_iso(leave.start_date)}؟\n"
                               "يمكن استعادتها لاحقاً من سلة المحذوفات."):
            return
        self.ctx.db.soft_delete_leave(leave.id, self.ctx.user())
        self._saved()

    def _attachments(self) -> None:
        leave = self._selected_leave()
        if not leave:
            return
        AttachmentsDialog(self, self.ctx, leave.id, self.emp_id).exec()

    def _statement(self) -> None:
        from .dialogs_leave import StatementDialog
        StatementDialog(self, self.ctx, self.emp_id).exec()

    def _saved(self) -> None:
        self._refresh()
        if self.on_save:
            self.on_save()

    # ------------------------------------------------------------------
    def _export_excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "حفظ Excel", f"leaves_{self.emp_id}.xlsx",
                                              "Excel (*.xlsx)")
        if not path:
            return
        try:
            X.export_leaves(path, self.employee, self.policy)
            W.info(self, trf("تم التصدير:\n{v0}", v0=path))
        except Exception as exc:
            W.error(self, trf("فشل التصدير: {v0}", v0=exc))

    def _export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "حفظ PDF", f"leaves_{self.emp_id}.pdf", "PDF (*.pdf)")
        if not path:
            return
        try:
            P.export_employee_leaves(path, self.employee, self.policy)
            W.info(self, trf("تم التصدير:\n{v0}", v0=path))
        except Exception as exc:
            W.error(self, trf("فشل التصدير: {v0}", v0=exc))

    def _print(self) -> None:
        balance = B.compute_balance(self.employee, self.employee.leaves, self.policy)
        statement = B.yearly_statement(self.employee, self.employee.leaves, self.policy)
        content = H.employee_detail_html(self.employee, self.policy, balance, statement)
        path = H.save_and_open(content, self.ctx.paths.reports_dir, f"employee_{self.emp_id}.html")
        W.info(self, trf("تم فتح التقرير في المتصفح:\n{v0}", v0=path.name))
