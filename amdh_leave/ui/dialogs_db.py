"""حوارات قاعدة البيانات: تصدير/دمج، قالب Excel، معالج الاستيراد الذكي."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QScrollArea,
    QVBoxLayout, QWidget,
)

from ..exporters import excel as X
from ..services import dates as D
from ..services import validation
from . import theme, widgets as W
from .dialogs_base import BaseDialog

# الحقول الهدف في الاستيراد + مرادفات التلقين التلقائي
IMPORT_FIELDS: list[tuple[str, str, list[str]]] = [
    ("emp_id", "الرقم الوظيفي *", ["emp_id", "الرقم الوظيفي", "الرقم", "id", "رقم الموظف"]),
    ("name", "الاسم *", ["name", "الاسم", "الاسم الكامل", "اسم الموظف"]),
    ("job_title", "العنوان الوظيفي", ["job_title", "العنوان الوظيفي", "العنوان", "الوظيفة", "المنصب"]),
    ("workplace", "مكان العمل", ["workplace", "مكان العمل", "موقع العمل", "الدائرة"]),
    ("institution", "المؤسسة / القسم", ["institution", "المؤسسة", "القسم", "المديرية"]),
    ("gender", "الجنس", ["gender", "الجنس"]),
    ("start_date", "تاريخ المباشرة *", ["start_date", "تاريخ المباشرة", "المباشرة", "تاريخ التعيين"]),
    ("end_date", "انتهاء الخدمة", ["end_date", "انتهاء الخدمة", "تاريخ الانتهاء"]),
    ("notes", "ملاحظات", ["notes", "ملاحظات", "الملاحظات"]),
]

IMPORT_MODES = [
    ("update", "تحديث الموجود وإضافة الجديد"),
    ("skip", "إضافة الجديد فقط (تجاهل الموجود)"),
]


class DatabaseOperationsDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None, refresh_callback=None):
        super().__init__(parent, ctx, "عمليات قاعدة البيانات")
        self.refresh_callback = refresh_callback
        self.resize(520, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label("إدارة قاعدة البيانات", 15))
        layout.addWidget(W.muted_label(f"المسار: {self.ctx.paths.db_path}"))
        for text, style, slot in (
            ("💾 نسخة احتياطية الآن", "Accent", self._backup_now),
            ("📀 تصدير قاعدة البيانات", "Blue", self._export_db),
            ("📂 استيراد/دمج قاعدة بيانات", "Gold", self._import_db),
            ("📄 تصدير قالب Excel للموظفين", "Ghost", self._export_template),
            ("📊 استيراد موظفين من Excel (معالج)", "Ghost", self._import_excel),
            ("🔍 فحص سلامة القاعدة", "Ghost", self._integrity),
            ("🧹 ضغط القاعدة (VACUUM)", "Ghost", self._vacuum),
            ("🗑 سلة المحذوفات", "Ghost", self._trash),
            ("📂 فتح مجلد البيانات", "Ghost", self._open_folder),
        ):
            layout.addWidget(W.button(text, style, slot))
        layout.addStretch()
        layout.addLayout(self.buttons_row(self.close_button()))

    # ------------------------------------------------------------------
    def _backup_now(self) -> None:
        path = self.ctx.backup.create("manual")
        if path:
            W.info(self, f"تم إنشاء نسخة احتياطية:\n{path.name}")
        else:
            W.error(self, "تعذّر إنشاء النسخة (راجع ملف السجل).")

    def _export_db(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "تصدير قاعدة البيانات",
                                              f"employees_backup_{date.today()}.db",
                                              "قاعدة بيانات (*.db)")
        if not path:
            return
        try:
            self.ctx.db.backup_to(path)
            W.info(self, f"تم التصدير:\n{path}")
            self.ctx.db.log(self.ctx.user(), "تصدير", "database", Path(path).name, "")
        except Exception as exc:
            W.error(self, f"فشل التصدير: {exc}")

    def _import_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "استيراد قاعدة بيانات", "", "قاعدة بيانات (*.db)")
        if not path:
            return
        mode = self._ask_mode()
        if mode is None:
            return
        if self.ctx.policy.backup_before_import:
            self.ctx.backup.create("pre_import")
        self.ctx.backup.import_mode = mode
        result = self.ctx.backup.import_merge(path, self.ctx.user())
        if result["errors"]:
            W.error(self, "أخطاء:\n" + "\n".join(result["errors"]))
            return
        W.info(self, f"اكتمل الدمج:\nموظفون مضافون: {result['added']}\n"
                     f"موظفون محدَّثون: {result['updated']}\nمتجاوَزون: {result['skipped']}\n"
                     f"إجازات منسوخة: {result['leaves']}")
        if self.refresh_callback:
            self.refresh_callback()

    def _ask_mode(self) -> str | None:
        from PyQt6.QtWidgets import QInputDialog
        items = [label for _key, label in IMPORT_MODES]
        choice, ok = QInputDialog.getItem(self, "وضع الدمج", "كيف نتعامل مع الموظف الموجود؟",
                                          items, 0, False)
        if not ok:
            return None
        for key, label in IMPORT_MODES:
            if label == choice:
                return key
        return "update"

    def _export_template(self) -> None:
        if not X.HAS_XLSX:
            W.error(self, "مكتبة openpyxl غير مثبتة.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "حفظ قالب Excel", "template_employees.xlsx",
                                              "Excel (*.xlsx)")
        if not path:
            return
        try:
            X.export_template(path)
            W.info(self, f"تم حفظ القالب:\n{path}")
        except Exception as exc:
            W.error(self, f"فشل الحفظ: {exc}")

    def _import_excel(self) -> None:
        ImportWizardDialog(self, self.ctx, refresh_callback=self.refresh_callback).exec()

    def _integrity(self) -> None:
        ok, message = self.ctx.db.integrity_check()
        (W.info if ok else W.error)(self, f"النتيجة: {message}", "سلامة القاعدة")

    def _vacuum(self) -> None:
        self.ctx.db.vacuum()
        W.info(self, "تم ضغط قاعدة البيانات.")

    def _trash(self) -> None:
        from .dialogs_base import TrashDialog
        TrashDialog(self, self.ctx).exec()

    def _open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.paths.data_dir)))


# ---------------------------------------------------------------------------
# معالج استيراد الموظفين من Excel
# ---------------------------------------------------------------------------
class ImportWizardDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None, refresh_callback=None):
        super().__init__(parent, ctx, "استيراد موظفين من Excel")
        self.refresh_callback = refresh_callback
        self.path: Path | None = None
        self.headers: list[str] = []
        self.raw_rows: list[dict] = []
        self.mapping: dict[str, QComboBox] = {}
        self.resize(1000, 720)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label("استيراد موظفين من ملف Excel", 15))

        file_row = QHBoxLayout()
        self.lbl_file = W.muted_label("لم يتم اختيار ملف")
        file_row.addWidget(W.button("📂 اختيار ملف", "Blue", self._choose_file))
        self.cb_sheet = QComboBox()
        self.cb_sheet.setMinimumWidth(180)
        self.cb_sheet.currentTextChanged.connect(self._load_rows)
        file_row.addWidget(QLabel("الورقة:"))
        file_row.addWidget(self.cb_sheet)
        file_row.addWidget(self.lbl_file, 1)
        layout.addLayout(file_row)

        mapping_card = W.card()
        self.mapping_grid = QGridLayout(mapping_card)
        layout.addWidget(mapping_card)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("وضع الاستيراد:"))
        self.cb_mode = QComboBox()
        for key, label in IMPORT_MODES:
            self.cb_mode.addItem(label, key)
        mode_row.addWidget(self.cb_mode)
        mode_row.addStretch()
        mode_row.addWidget(W.button("🔍 تحقق ومعاينة", "Gold", self._validate))
        layout.addLayout(mode_row)

        self.summary = W.muted_label("اختر ملفاً ثم اضغط «تحقق ومعاينة».")
        layout.addWidget(self.summary)
        self.preview = W.TablePanel(["#", "الرقم الوظيفي", "الاسم", "المباشرة", "المؤسسة", "النتيجة"],
                                    sortable=False)
        layout.addWidget(self.preview)
        self.details = QLabel("")
        self.details.setWordWrap(True)
        self.details.setStyleSheet(theme.label_style("muted"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.addWidget(self.details)
        scroll.setWidget(holder)
        scroll.setMaximumHeight(150)
        layout.addWidget(scroll)

        self.btn_import = W.button("📥 تنفيذ الاستيراد", "Accent", self._run_import, width=180)
        self.btn_import.setEnabled(False)
        layout.addLayout(self.buttons_row(self.close_button("إلغاء"), self.btn_import))

    # ------------------------------------------------------------------
    def _choose_file(self) -> None:
        if not X.HAS_XLSX:
            W.error(self, "مكتبة openpyxl غير مثبتة.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "اختر ملف Excel", "", "Excel (*.xlsx *.xlsm)")
        if not path:
            return
        self.path = Path(path)
        self.lbl_file.setText(self.path.name)
        try:
            names = X.sheet_names(self.path)
        except Exception as exc:
            W.error(self, f"تعذّر قراءة الملف: {exc}")
            return
        self.cb_sheet.blockSignals(True)
        self.cb_sheet.clear()
        self.cb_sheet.addItems(names)
        self.cb_sheet.blockSignals(False)
        self._load_rows(names[0] if names else None)

    def _load_rows(self, sheet: str | None = None) -> None:
        if not self.path:
            return
        try:
            self.headers, self.raw_rows = X.read_table(self.path, sheet or None)
        except Exception as exc:
            W.error(self, f"تعذّر قراءة الورقة: {exc}")
            return
        self._build_mapping()
        self.summary.setText(f"عدد الصفوف في الملف: {len(self.raw_rows)} — "
                             f"عدد الأعمدة: {len(self.headers)}. اضغط «تحقق ومعاينة».")

    def _build_mapping(self) -> None:
        while self.mapping_grid.count():
            item = self.mapping_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.mapping.clear()
        for i, (key, label, synonyms) in enumerate(IMPORT_FIELDS):
            combo = QComboBox()
            combo.addItem("(تجاهل)", "")
            for header in self.headers:
                combo.addItem(header, header)
            guess = self._guess(synonyms)
            if guess:
                index = combo.findData(guess)
                if index >= 0:
                    combo.setCurrentIndex(index)
            self.mapping[key] = combo
            row, col = divmod(i, 3)
            self.mapping_grid.addWidget(QLabel(label), row, col * 2)
            self.mapping_grid.addWidget(combo, row, col * 2 + 1)

    def _guess(self, synonyms: list[str]) -> str:
        lowered = {h.strip().lower(): h for h in self.headers}
        for synonym in synonyms:
            if synonym.strip().lower() in lowered:
                return lowered[synonym.strip().lower()]
        for header in self.headers:
            for synonym in synonyms:
                if synonym.strip().lower() in header.strip().lower():
                    return header
        return ""

    # ------------------------------------------------------------------
    def _mapped_rows(self) -> list[dict]:
        out = []
        for raw in self.raw_rows:
            row = {}
            for key, combo in self.mapping.items():
                header = combo.currentData()
                row[key] = raw.get(header) if header else None
            out.append(row)
        return out

    def _validate(self) -> None:
        if not self.raw_rows:
            W.warn(self, "اختر ملفاً أولاً.")
            return
        mapped = self._mapped_rows()
        self._mapped = mapped
        existing_ids = {e.emp_id for e in self.ctx.db.list_employees(with_leaves=False)}
        seen: set[str] = set()
        results = []
        errors = 0
        warnings = 0
        details: list[str] = []
        for i, row in enumerate(mapped, 1):
            emp_id = str(row.get("emp_id") or "").strip()
            issues = validation.validate_import_row(row, existing_ids, seen)
            seen.add(emp_id)
            level = "ok"
            if any(issue.is_error for issue in issues):
                level = "error"
                errors += 1
            elif any(issue.level == "info" for issue in issues):
                level = "update"
            if issues and level != "ok":
                for issue in issues:
                    if issue.level in ("error", "warning"):
                        details.append(f"صف {i}: {issue.message}")
                        if issue.level == "warning":
                            warnings += 1
            results.append({
                "index": i, "emp_id": emp_id,
                "name": str(row.get("name") or ""),
                "start_date": D.to_iso(row.get("start_date")),
                "institution": str(row.get("institution") or ""),
                "level": level, "issues": issues,
            })
        self._validated = results
        labels = {"ok": "جاهز للإضافة", "update": "سيُحدَّث الموجود", "error": "خطأ — لن يُستورد"}
        rows = [[r["index"], r["emp_id"], r["name"], r["start_date"], r["institution"],
                 labels[r["level"]]] for r in results[:400]]
        self.preview.set_rows(rows, empty_text="لا توجد صفوف")
        self.summary.setText(f"الصفوف: {len(results)} | صالحة: "
                             f"{sum(1 for r in results if r['level'] != 'error')} | أخطاء: {errors} | "
                             f"تحذيرات: {warnings}")
        self.details.setText("<br>".join(details[:200]) or "لا توجد ملاحظات.")
        self.btn_import.setEnabled(any(r["level"] != "error" for r in results))

    # ------------------------------------------------------------------
    def _run_import(self) -> None:
        if not getattr(self, "_validated", None):
            W.warn(self, "اضغط «تحقق ومعاينة» أولاً.")
            return
        mode = self.cb_mode.currentData()
        if self.ctx.policy.backup_before_import:
            self.ctx.backup.create("pre_import")
        added = updated = skipped = 0
        errors: list[str] = []
        try:
            with self.ctx.db.transaction() as conn:
                for row in self._validated:
                    if row["level"] == "error":
                        skipped += 1
                        continue
                    emp_id = row["emp_id"]
                    exists = conn.execute("SELECT 1 FROM employees WHERE emp_id=?",
                                          (emp_id,)).fetchone() is not None
                    if exists and mode == "skip":
                        skipped += 1
                        continue
                    fields = self._fields_for(row["index"] - 1)
                    if exists:
                        conn.execute("""UPDATE employees SET name=?, job_title=?, workplace=?,
                                     institution=?, gender=?, start_date=?, end_date=?, notes=?,
                                     updated_at=datetime('now','localtime') WHERE emp_id=?""",
                                     (fields["name"], fields["job_title"], fields["workplace"],
                                      fields["institution"], fields["gender"], fields["start_date"],
                                      fields["end_date"], fields["notes"], emp_id))
                        updated += 1
                    else:
                        conn.execute("""INSERT INTO employees(emp_id, name, job_title, workplace,
                                     institution, gender, start_date, end_date, notes, status,
                                     created_at, updated_at)
                                     VALUES (?,?,?,?,?,?,?,?,?,'active',
                                     datetime('now','localtime'), datetime('now','localtime'))""",
                                     (emp_id, fields["name"], fields["job_title"], fields["workplace"],
                                      fields["institution"], fields["gender"], fields["start_date"],
                                      fields["end_date"], fields["notes"]))
                        added += 1
        except Exception as exc:
            errors.append(str(exc))
        self.ctx.db.log(self.ctx.user(), "استيراد", "excel", self.path.name if self.path else "",
                        f"إضافة {added} - تحديث {updated} - تخطي {skipped}")
        if errors:
            W.error(self, "فشل الاستيراد:\n" + "\n".join(errors))
            return
        W.info(self, f"اكتمل الاستيراد:\nأُضيف: {added}\nحُدِّث: {updated}\nتُجوهل: {skipped}")
        if self.refresh_callback:
            self.refresh_callback()
        self.accept()

    def _fields_for(self, index: int) -> dict:
        row = self._mapped[index]
        gender = str(row.get("gender") or "").strip()
        return {
            "name": str(row.get("name") or "").strip(),
            "job_title": str(row.get("job_title") or "").strip(),
            "workplace": str(row.get("workplace") or "").strip(),
            "institution": str(row.get("institution") or "").strip(),
            "gender": gender if gender in ("ذكر", "أنثى") else "ذكر",
            "start_date": D.to_iso(row.get("start_date")),
            "end_date": D.to_iso(row.get("end_date")),
            "notes": str(row.get("notes") or "").strip(),
        }
