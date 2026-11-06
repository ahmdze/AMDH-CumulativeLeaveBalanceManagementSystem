"""واجهة استيراد ملفات المؤسسات (النقل) وعرض تقرير الدمج التفصيلي.

المسار الكامل:
  1. اختيار ملف ``.amdhz`` أو ``.db`` من مؤسسة.
  2. عرض بيانه (المؤسسة، الإصدار، الأعداد، بصمة الضوابط) والتحقق من الملف.
  3. **معاينة** كاملة بلا أي كتابة: ما سيُضاف، ما سيُحدَّث، التعارضات، الانتقالات، المرفقات.
  4. تأكيد ⇒ نسخة احتياطية تلقائية ⇒ تنفيذ الدمج في معاملة واحدة.
  5. تقرير تفصيلي يُحفظ في سجل الاستيراد، قابل للتصدير إلى Excel، مع زر تراجع.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..services import merge as M
from ..services import transfer as T
from . import theme
from . import widgets as W

TRANSFER_FILTER = (
    "ملفات النقل (*.amdhz *.db *.zip);;أرشيف نقل (*.amdhz *.zip);;قاعدة بيانات (*.db);;كل الملفات (*)"
)


# ---------------------------------------------------------------------------
# التقرير
# ---------------------------------------------------------------------------
class ReportDialog(QDialog):
    """تقرير استيراد تفصيلي (ملخص + تعارضات + انتقالات + تقاطعات + متجاهلون)."""

    def __init__(
        self, parent, ctx, report: M.MergeReport, record=None, backup_path: Path | None = None
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.report = report
        self.record = record
        self.backup_path = backup_path
        self.setWindowTitle("تقرير استيراد ملف مؤسسة")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumSize(940, 640)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        header = QHBoxLayout()
        title = QLabel(f"📥  تقرير استيراد — {self.report.institution or 'غير محددة'}")
        title.setStyleSheet(theme.label_style("accent", 15, bold=True))
        header.addWidget(title)
        header.addStretch()
        if self.report.conflicts:
            badge = QLabel(f"  ⚠ {self.report.conflicts} تعارضاً  ")
            badge.setStyleSheet(theme.label_style("neg", 11, bold=True))
            header.addWidget(badge)
        layout.addLayout(header)

        self.tabs = QTabWidget()
        summary = QTextEdit()
        summary.setReadOnly(True)
        summary.setPlainText("\n".join(self.report.summary_lines()))
        self.tabs.addTab(summary, "الملخص")

        self.tabs.addTab(self._table_tab(M.conflict_rows(self.report), "لا توجد تعارضات."), "التعارضات")
        self.tabs.addTab(
            self._table_tab(M.move_rows(self.report), "لا توجد انتقالات بين المؤسسات."), "الانتقالات"
        )
        self.tabs.addTab(self._table_tab(M.overlap_rows(self.report), "لا توجد تقاطعات زمنية."), "التقاطعات")
        skipped = [
            ["الرقم الوظيفي", "الاسم", "السبب"],
            [
                [item.get("emp_id", ""), item.get("name", ""), item.get("reason", "")]
                for item in self.report.skipped_list
            ],
        ]
        self.tabs.addTab(self._table_tab(skipped, "لا توجد سجلات متجاهلة."), "المتجاهلون")
        layout.addWidget(self.tabs, 1)

        if self.report.warnings:
            warning_box = QPlainTextEdit()
            warning_box.setReadOnly(True)
            warning_box.setFixedHeight(76)
            warning_box.setPlainText("\n".join("⚠️ " + item for item in self.report.warnings))
            layout.addWidget(warning_box)

        buttons = QHBoxLayout()
        buttons.addWidget(W.button("📊 تصدير التقرير إلى Excel", "Gold", self._export, width=230))
        if self.backup_path:
            buttons.addWidget(W.button("↩ تراجع عن هذا الاستيراد", "Warn", self._undo, width=200))
        buttons.addStretch()
        buttons.addWidget(W.button("إغلاق", "Ghost", self.accept, width=90))
        layout.addLayout(buttons)

    def _table_tab(self, data, empty_text: str) -> QWidget:
        headers, rows = data
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        if not rows:
            layout.addWidget(W.muted_label(empty_text))
            layout.addStretch()
            return page
        table = W.TablePanel(headers)
        table.set_rows(rows)
        layout.addWidget(table)
        return page

    def _export(self) -> None:
        default = f"تقرير_استيراد_{self.report.institution or 'مؤسسة'}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "تصدير التقرير", default, "Excel (*.xlsx)")
        if not path:
            return
        try:
            output = M.export_report_excel(path, self.report)
        except Exception as exc:  # noqa: BLE001
            W.error(self, f"تعذّر التصدير: {exc}")
            return
        if W.confirm(self, f"تم التصدير إلى:\n{output}\n\nهل تريد فتحه الآن؟"):
            W.open_path(self, output)

    def _undo(self) -> None:
        if not W.confirm(
            self,
            "سيُعاد إرجاع قاعدة البيانات إلى ما كانت عليه قبل هذا "
            "الاستيراد (مع أخذ نسخة أمان للحالة الحالية).\n\nمتابعة؟",
            "تراجع عن الاستيراد",
        ):
            return
        ok, message = self.ctx.backup.restore(self.backup_path)
        if ok:
            self.ctx.refresh_policy()
            W.info(self, message + "\n\nأُعيدت الحالة السابقة للاستيراد.")
            self.accept()
        else:
            W.error(self, message)


# ---------------------------------------------------------------------------
# سجل الاستيراد والتصدير
# ---------------------------------------------------------------------------
class ImportHistoryDialog(QDialog):
    def __init__(self, parent, ctx) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("سجل الاستيراد والتصدير")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumSize(1000, 560)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        self._build()
        self._refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)
        header = QHBoxLayout()
        title = QLabel("📋  سجل الاستيراد والتصدير")
        title.setStyleSheet(theme.label_style("accent", 15, bold=True))
        header.addWidget(title)
        header.addStretch()
        header.addWidget(QLabel("المؤسسة:"))
        self.cb_institution = QComboBox()
        self.cb_institution.addItem("الكل", "")
        for institution in self.ctx.db.list_institutions():
            self.cb_institution.addItem(institution.name, institution.name)
        self.cb_institution.currentIndexChanged.connect(self._refresh)
        header.addWidget(self.cb_institution)
        header.addWidget(W.button("🧾 عرض التقرير", "Ghost", self._show_report))
        header.addWidget(W.button("🔄 تحديث", "Ghost", self._refresh))
        layout.addLayout(header)

        self.table = W.TablePanel(
            [
                "#",
                "التاريخ",
                "الاتجاه",
                "المؤسسة",
                "المستخدم",
                "الملف",
                "موظفون +",
                "موظفون ~",
                "إجازات +",
                "إجازات ~",
                "انتقالات",
                "مرفقات",
                "تعارضات",
            ]
        )
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        buttons.addWidget(W.button("🖨 تصدير المعروض", "Gold", self._export_table))
        buttons.addStretch()
        buttons.addWidget(W.button("إغلاق", "Ghost", self.accept, width=90))
        layout.addLayout(buttons)

    def _refresh(self) -> None:
        self.records = self.ctx.db.list_imports(
            limit=300, institution=self.cb_institution.currentData() or ""
        )
        rows = []
        for record in self.records:
            rows.append(
                [
                    str(record.id),
                    record.ts,
                    "استيراد" if record.direction == "import" else "تصدير",
                    record.institution or record.scope,
                    record.username,
                    record.source_file,
                    record.employees_added,
                    record.employees_updated,
                    record.leaves_added,
                    record.leaves_updated,
                    record.moves,
                    record.attachments,
                    record.employees_conflict,
                ]
            )
        self.table.set_rows(rows)

    def _current(self):
        row = self.table.current_row()
        if row < 0 or row >= len(self.records):
            return None
        return self.records[row]

    def _show_report(self) -> None:
        record = self._current()
        if record is None:
            W.warn(self, "حدد سجلاً أولاً.")
            return
        report = M.MergeReport.from_json(record.report)
        if not report.source_file:
            report.source_file = record.source_file
        if not report.institution:
            report.institution = record.institution
        ReportDialog(self, self.ctx, report, record=record).exec()

    def _export_table(self) -> None:
        from ..exporters import excel as X

        path, _ = QFileDialog.getSaveFileName(self, "تصدير السجل", "سجل_الاستيراد.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        headers = [
            "#",
            "التاريخ",
            "الاتجاه",
            "المؤسسة",
            "المستخدم",
            "الملف",
            "موظفون مضافون",
            "موظفون محدَّثون",
            "إجازات مضافة",
            "إجازات محدَّثة",
            "انتقالات",
            "مرفقات",
            "تعارضات",
        ]
        rows = [
            [
                str(record.id),
                record.ts,
                "استيراد" if record.direction == "import" else "تصدير",
                record.institution or record.scope,
                record.username,
                record.source_file,
                record.employees_added,
                record.employees_updated,
                record.leaves_added,
                record.leaves_updated,
                record.moves,
                record.attachments,
                record.employees_conflict,
            ]
            for record in self.records
        ]
        try:
            X.write_table(path, headers, rows, sheet="سجل الاستيراد")
        except Exception as exc:  # noqa: BLE001
            W.error(self, f"تعذّر التصدير: {exc}")
            return
        W.info(self, f"تم التصدير إلى:\n{path}")


# ---------------------------------------------------------------------------
# استيراد ملف مؤسسة
# ---------------------------------------------------------------------------
class TransferImportDialog(QDialog):
    def __init__(self, parent, ctx) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.path: Path | None = None
        self.plan: M.MergePlan | None = None
        self.report: M.MergeReport | None = None
        self.setWindowTitle("استيراد ملف مؤسسة")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumSize(1000, 700)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        header = QHBoxLayout()
        title = QLabel("📥  استيراد ملف مؤسسة إلى قاعدة المركز")
        title.setStyleSheet(theme.label_style("accent", 15, bold=True))
        header.addWidget(title)
        header.addStretch()
        self.e_path = QLineEdit()
        self.e_path.setReadOnly(True)
        self.e_path.setPlaceholderText("اختر ملف النقل (.amdhz أو .db)")
        self.e_path.setMinimumWidth(420)
        header.addWidget(self.e_path)
        header.addWidget(W.button("📂 اختيار ملف", "Accent", self._choose, width=130))
        layout.addLayout(header)

        self.lbl_info = W.muted_label("لم يُختَر ملف بعد.")
        layout.addWidget(self.lbl_info)

        options = QHBoxLayout()
        self.chk_attachments = QCheckBox("نقل المرفقات")
        self.chk_attachments.setChecked(True)
        self.chk_other = QCheckBox("السماح بموظفي مؤسسات أخرى")
        options.addWidget(self.chk_attachments)
        options.addWidget(self.chk_other)
        options.addWidget(QLabel("عند التعارض:"))
        self.cb_prefer = QComboBox()
        self.cb_prefer.addItem("الأحدث تعديلاً", "newest")
        self.cb_prefer.addItem("ملف المؤسسة", "source")
        self.cb_prefer.addItem("نسخة المركز", "target")
        options.addWidget(self.cb_prefer)
        options.addWidget(QLabel("المؤسسة المعلنة:"))
        self.e_institution = QLineEdit()
        self.e_institution.setPlaceholderText("تُقرأ من بيان الملف")
        self.e_institution.setMinimumWidth(200)
        options.addWidget(self.e_institution)
        options.addStretch()
        layout.addLayout(options)

        self.tabs = QTabWidget()
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setPlainText("اضغط «معاينة» لعرض ما سيحدث قبل أي تعديل.")
        self.tabs.addTab(self.summary, "الملخص")
        self.conflicts = QTextEdit()
        self.conflicts.setReadOnly(True)
        self.tabs.addTab(self.conflicts, "التعارضات والانتقالات")
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.tabs.addTab(self.details, "تفاصيل الخطة")
        layout.addWidget(self.tabs, 1)

        buttons = QHBoxLayout()
        self.btn_preview = W.button("🔍 معاينة", "Ghost", self._preview, width=130)
        self.btn_apply = W.button("📥 تنفيذ الاستيراد", "Accent", self._apply, width=180)
        self.btn_apply.setEnabled(False)
        buttons.addWidget(self.btn_preview)
        buttons.addWidget(self.btn_apply)
        buttons.addWidget(W.button("📋 سجل الاستيراد", "Ghost", self._history))
        buttons.addStretch()
        buttons.addWidget(W.button("إغلاق", "Ghost", self.reject, width=90))
        layout.addLayout(buttons)

    # -- الخطوات -------------------------------------------------------
    def fill_from_path(self, path: Path) -> None:
        """يضبط الملف ويعرض بيانه ومعاينته (تُستخدم من نافذة عمليات القاعدة)."""
        self.path = Path(path)
        self.e_path.setText(str(self.path))
        self.plan = None
        self.report = None
        self.btn_apply.setEnabled(False)
        try:
            info = T.read_transfer_info(self.path)
        except Exception as exc:  # noqa: BLE001
            W.error(self, f"تعذّر قراءة الملف: {exc}")
            return
        self._show_info(info)

    def _choose_path_filled(self, info: dict) -> None:
        self._show_info(info)

    def _show_info(self, info: dict) -> None:
        manifest = info.get("manifest") or {}
        if not self.e_institution.text().strip() and manifest.get("institution"):
            self.e_institution.setText(str(manifest["institution"]))
        counts = manifest.get("counts") or {}
        lines = [
            f"الملف: {info['name']} ({info['size'] / 1024:,.0f} ك.ب)",
            f"النوع: {'أرشيف نقل (مع مرفقات)' if info['archive'] else 'قاعدة بيانات'}",
            f"المؤسسة: {manifest.get('institution') or 'غير محددة'}",
            f"إصدار المخطط: {manifest.get('schema_version') or '—'} | "
            f"إصدار البرنامج: {manifest.get('app_version') or '—'}",
            f"أُنشئ في: {manifest.get('generated_at') or '—'} بواسطة {manifest.get('generated_by') or '—'}",
        ]
        if counts:
            lines.append(
                f"المحتوى: {counts.get('employees', '?')} موظفاً، "
                f"{counts.get('leaves', '?')} إجازة، "
                f"{counts.get('attachments', 0)} مرفقاً"
            )
        if info["attachment_files"]:
            lines.append(f"ملفات مرفقات في الأرشيف: {info['attachment_files']}")
        lines.append(f"بصمة الملف: {info['checksum'][:24]}…")
        self.lbl_info.setText(" | ".join(lines[:4]))
        self.summary.setPlainText("\n".join(lines) + "\n\nاضغط «معاينة» لعرض تفاصيل الدمج.")
        self._preview()

    def _choose(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "اختر ملف النقل", "", TRANSFER_FILTER)
        if not path:
            return
        self.fill_from_path(Path(path))

    def _options(self) -> M.MergeOptions:
        return M.MergeOptions(
            institution=self.e_institution.text().strip(),
            allow_other_institutions=self.chk_other.isChecked(),
            prefer=self.cb_prefer.currentData(),
            transfer_attachments=self.chk_attachments.isChecked(),
        )

    def _preview(self) -> None:
        if not self.path:
            W.warn(self, "اختر ملفاً أولاً.")
            return
        try:
            self.plan, self.report, _info = T.preview_transfer(self.ctx.db, self.path, self._options())
        except Exception as exc:  # noqa: BLE001
            W.error(self, f"تعذّرت المعاينة: {exc}")
            return
        report = self.report
        self.summary.setPlainText("\n".join(report.summary_lines()))
        conflict_lines = []
        if report.conflict_list:
            conflict_lines.append(f"التعارضات ({len(report.conflict_list)}):")
            for item in report.conflict_list[:80]:
                conflict_lines.append(
                    f"  • [{item.get('kind')}] {item.get('emp_id')} — "
                    f"{item.get('detail')} ⇒ {item.get('winner')}"
                )
        if report.move_list:
            conflict_lines.append("")
            conflict_lines.append(f"انتقالات بين المؤسسات ({len(report.move_list)}):")
            for item in report.move_list[:80]:
                conflict_lines.append(
                    f"  • {item.get('emp_id')} ({item.get('name')}): "
                    f"{item.get('from_institution')} ← "
                    f"{item.get('to_institution')} بتاريخ "
                    f"{item.get('moved_on')}"
                )
        if report.overlap_list:
            conflict_lines.append("")
            conflict_lines.append(f"تقاطعات زمنية ({len(report.overlap_list)}):")
            for item in report.overlap_list[:40]:
                conflict_lines.append(
                    f"  • {item.get('emp_id')}: {item.get('new_type')} "
                    f"{item.get('new_start')} تتقاطع مع "
                    f"{item.get('existing_type')} {item.get('existing_start')}"
                )
        if report.skipped_list:
            conflict_lines.append("")
            conflict_lines.append(f"سجلات ستُتجاهل ({len(report.skipped_list)}):")
            for item in report.skipped_list[:40]:
                conflict_lines.append(f"  • {item.get('emp_id')} ({item.get('name')}): {item.get('reason')}")
        self.conflicts.setPlainText("\n".join(conflict_lines) or "لا توجد تعارضات أو انتقالات.")

        plan_lines = [
            f"سيُضاف: {len(self.plan.employees_add)} موظفاً، "
            f"{len(self.plan.leaves_add)} إجازة، {len(self.plan.attachments_add)} مرفقاً",
            f"سيُحدَّث: {len(self.plan.employees_update)} موظفاً، {len(self.plan.leaves_update)} إجازة",
            f"بلا تغيير: {len(self.plan.employees_unchanged)} موظفاً، {len(self.plan.leaves_unchanged)} إجازة",
            f"مؤسسات الملف: {'، '.join(self.plan.source_institutions) or '—'}",
        ]
        if self.plan.employees_add:
            plan_lines.append("")
            plan_lines.append(
                "موظفون جدد: "
                + "، ".join(
                    f"{record.get('emp_id')} ({record.get('name')})"
                    for record in self.plan.employees_add[:40]
                )
            )
        if self.plan.leaves_add:
            plan_lines.append("")
            plan_lines.append(
                "إجازات ستُضاف: "
                + "، ".join(
                    f"{record.get('emp_id')}/{record.get('type')}/{record.get('start_date')}"
                    for record in self.plan.leaves_add[:40]
                )
            )
        self.details.setPlainText("\n".join(plan_lines))
        self.btn_apply.setEnabled(
            bool(
                self.plan.employees_add
                or self.plan.employees_update
                or self.plan.leaves_add
                or self.plan.leaves_update
                or self.plan.attachments_add
            )
        )

    def _apply(self) -> None:
        if not self.path or self.plan is None:
            W.warn(self, "اعرض المعاينة أولاً.")
            return
        self._preview()
        if self.report is None:
            return
        total = (
            self.report.employees_added
            + self.report.employees_updated
            + self.report.leaves_added
            + self.report.leaves_updated
        )
        if not W.confirm(
            self,
            f"سيُدمج ملف «{self.path.name}» في قاعدة المركز:\n\n"
            f"• إضافة {self.report.employees_added} موظفاً و"
            f"{self.report.leaves_added} إجازة\n"
            f"• تحديث {self.report.employees_updated} موظفاً و"
            f"{self.report.leaves_updated} إجازة\n"
            f"• انتقالات: {self.report.moves} | مرفقات: {self.report.attachments_added}\n"
            f"• تعارضات: {self.report.conflicts}\n\n"
            + ("لا يوجد تغيير فعلي.\n\n" if total == 0 else "")
            + "ستُؤخذ نسخة احتياطية تلقائياً قبل التنفيذ. متابعة؟",
            "تأكيد الدمج",
        ):
            return

        backup_path = None
        try:
            backup_path = self.ctx.backup.create("pre_import")
        except Exception as exc:  # noqa: BLE001
            from ..logging_setup import get_logger

            get_logger("import").warning("تعذّر إنشاء نسخة قبل الاستيراد: %s", exc)
        try:
            report = T.apply_transfer(
                self.ctx.db,
                self.path,
                self._options(),
                user=self.ctx.user(),
                attachments_dir=self.ctx.paths.attachments_dir,
            )
        except Exception as exc:  # noqa: BLE001
            W.error(self, f"فشل الاستيراد: {exc}\n\nلم يُغيَّر أي شيء (تُراجَع المعاملة كاملة).")
            return
        self.ctx.refresh_policy()
        W.info(self, "\n".join(report.summary_lines()), "تم الاستيراد")
        ReportDialog(self, self.ctx, report, backup_path=backup_path).exec()
        self.btn_apply.setEnabled(False)
        self.plan = None

    def _history(self) -> None:
        ImportHistoryDialog(self, self.ctx).exec()


# ---------------------------------------------------------------------------
# التصدير
# ---------------------------------------------------------------------------
def export_for_institution(parent, ctx, institution: str = "", center_side: bool = True) -> Path | None:
    """يصدّر ملف نقل لمؤسسة واحدة (أو لكل المؤسسات إن لم تُحدَّد)."""
    institution = institution or ctx.session.scoped_institution or ""
    default = f"نقل_{institution or 'كل_المؤسسات'}_{datetime.now():%Y-%m-%d}.amdhz"
    path, _ = QFileDialog.getSaveFileName(
        parent,
        "تصدير ملف نقل",
        str(ctx.paths.reports_dir / default),
        "أرشيف نقل (*.amdhz);;قاعدة بيانات (*.db)",
    )
    if not path:
        return None
    include_attachments = True
    if Path(path).suffix.lower() == ".db":
        include_attachments = W.confirm(
            parent,
            "ملف .db لا يحمل المرفقات (ملفات الأوامر).\n\n"
            "هل تريد المتابعة بلا مرفقات؟\n(اختر «لا» لتصدير أرشيف .amdhz مع المرفقات)",
            "تنبيه المرفقات",
        )
        if not include_attachments:
            path = str(Path(path).with_suffix(".amdhz"))
    try:
        manifest = T.export_transfer(
            ctx.db,
            path,
            institution=institution,
            include_attachments=include_attachments,
            user=ctx.user(),
            attachments_dir=ctx.paths.attachments_dir,
            center=ctx.db.center_institution(),
        )
    except Exception as exc:  # noqa: BLE001
        W.error(parent, f"تعذّر التصدير: {exc}")
        return None
    output = Path(manifest["path"])
    counts = manifest.get("counts", {})
    lines = [
        f"تم إنشاء ملف النقل:\n{output}",
        "",
        f"المؤسسة: {manifest.get('institution') or 'كل المؤسسات'}",
        f"الموظفون: {counts.get('employees', 0)} (محذوفون: {counts.get('employees_deleted', 0)})",
        f"الإجازات: {counts.get('leaves', 0)} (محذوفة: {counts.get('leaves_deleted', 0)})",
        f"المرفقات: {counts.get('attachments', 0)} (ملفات: {counts.get('attachment_files', 0)})",
        "",
        "الملف منقّى: لا يحوي حسابات المستخدمين ولا سجل التدقيق.",
        "سلّمه للمركز ليستورده من «استيراد ملف مؤسسة».",
    ]
    if W.confirm(parent, "\n".join(lines) + "\n\nهل تريد فتح مجلد الملف؟", "تم التصدير"):
        W.open_path(parent, output.parent)
    return output
