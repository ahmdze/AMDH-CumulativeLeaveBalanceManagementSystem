"""خزنة كلمات المرور: كلمة مرور القاعدة، مفاتيح نسخ المؤسسات، ونسخ الصيانة.

تنبيه: القيم تُخزَّن داخل قاعدة البيانات (المشفّرة عند التفعيل). فقدان القاعدة
يعني فقدان الخزنة، لذلك تُصدَّر «بطاقة استرداد» خارجية للطباعة.
"""

from __future__ import annotations

import html
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QTextEdit, QVBoxLayout, QWidget,
)

from . import theme, widgets as W
from .dialogs_base import BaseDialog

KINDS = [
    ("master", "كلمة مرور قاعدة المركز"),
    ("institution_key", "مفتاح نسخة مؤسسة"),
    ("maintenance", "كلمة مرور صيانة (admin)"),
    ("institution_user", "دخول مستخدم مؤسسة"),
    ("backup", "نسخة احتياطية"),
    ("other", "أخرى"),
]
KIND_LABELS = dict(KINDS)


class VaultEntryDialog(BaseDialog):
    def __init__(self, parent, ctx, entry: dict | None = None) -> None:
        super().__init__(parent, ctx, "تعديل مدخل" if entry else "إضافة مدخل")
        self.entry = entry or {}
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        card = W.card()
        form = QFormLayout(card)
        self.cb_kind = QComboBox()
        for key, label in KINDS:
            self.cb_kind.addItem(label, key)
        self.e_label = QLineEdit(str(self.entry.get("label", "")))
        self.e_institution = QLineEdit(str(self.entry.get("institution", "")))
        self.e_file = QLineEdit(str(self.entry.get("file_name", "")))
        self.e_path = QLineEdit(str(self.entry.get("file_path", "")))
        self.e_password = QLineEdit(str(self.entry.get("password", "")))
        self.e_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_note = QPlainTextEdit(str(self.entry.get("note", "")))
        self.e_note.setFixedHeight(60)
        form.addRow("النوع", self.cb_kind)
        form.addRow("التسمية", self.e_label)
        form.addRow("المؤسسة", self.e_institution)
        form.addRow("اسم الملف", self.e_file)
        form.addRow("مسار الملف", self.e_path)
        form.addRow("كلمة المرور/المفتاح", self.e_password)
        form.addRow("ملاحظات", self.e_note)
        layout.addWidget(card)
        layout.addLayout(self.buttons_row(W.button("إلغاء", "Ghost", self.reject, width=90),
                                          W.button("💾 حفظ", "Accent", self._save, width=120)))

    def _save(self) -> None:
        if not self.e_label.text().strip() and not self.e_institution.text().strip():
            W.warn(self, "أدخل تسمية أو مؤسسة للمدخل.")
            return
        values = {
            "kind": self.cb_kind.currentData(),
            "label": self.e_label.text().strip(),
            "institution": self.e_institution.text().strip(),
            "file_name": self.e_file.text().strip(),
            "file_path": self.e_path.text().strip(),
            "password": self.e_password.text(),
            "note": self.e_note.toPlainText().strip(),
        }
        if self.entry.get("id"):
            self.ctx.db.update_vault_entry(int(self.entry["id"]), **values)
        else:
            self.ctx.db.add_vault_entry(**values, user=self.ctx.user())
        self.ctx.db.log(self.ctx.user(), "تعديل" if self.entry else "إضافة", "vault",
                        self.entry.get("id", ""), values["label"])
        self.accept()


class VaultDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None) -> None:
        super().__init__(parent, ctx, "خزنة كلمات المرور")
        if ctx is not None and not ctx.can("manage_encryption"):
            W.error(self, "خزنة كلمات المرور متاحة لمن يملك صلاحية إدارة التشفير.")
            self.reject()
            return
        self.resize(1080, 620)
        self.show_passwords = False
        self.entries: list[dict] = []
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(W.title_label("🔐 خزنة كلمات المرور", 15))
        header.addStretch()
        header.addWidget(W.button("🖨 بطاقة استرداد", "Gold", self._export_card))
        header.addWidget(W.button("🔄 تحديث", "Ghost", self._refresh))
        layout.addLayout(header)
        layout.addWidget(W.muted_label(
            "تُحفظ كلمة مرور قاعدة المركز ومفاتيح نسخ المؤسسات هنا. "
            "الخزنة محمية فقط عندما تكون قاعدة البيانات مشفّرة. "
            "صدّر «بطاقة استرداد» واطبعها واحفظها خارج الجهاز؛ الخزنة وحدها لا تكفي "
            "إذا فُقدت قاعدة البيانات."))
        self.table = W.TablePanel(["#", "النوع", "التسمية", "المؤسسة", "الملف",
                                   "كلمة المرور", "ملاحظات", "التاريخ"])
        self.table.table.doubleClicked.connect(lambda _i: self._edit())
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(W.button("➕ إضافة", "Accent", self._add))
        row.addWidget(W.button("✏ تعديل", "Ghost", self._edit))
        row.addWidget(W.button("🗑 حذف", "Warn", self._delete))
        row.addWidget(W.button("👁 إظهار/إخفاء", "Blue", self._toggle))
        row.addWidget(W.button("📋 نسخ كلمة المرور", "Ghost", self._copy))
        row.addStretch()
        row.addWidget(W.button("إغلاق", "Ghost", self.accept, width=90))
        layout.addLayout(row)
        self._refresh()

    def _refresh(self) -> None:
        self.entries = self.ctx.db.list_vault()
        rows = []
        for index, item in enumerate(self.entries, 1):
            password = item.get("password", "")
            shown = password if self.show_passwords else ("••••••••" if password else "")
            rows.append([index, KIND_LABELS.get(item.get("kind"), item.get("kind", "")),
                         item.get("label", ""), item.get("institution", ""),
                         item.get("file_name", ""), shown, item.get("note", ""),
                         item.get("created_at", "")])
        self.table.set_rows(rows, empty_text="لا توجد مداخل في الخزنة")

    def _selected(self) -> dict | None:
        row = self.table.current_row()
        if row < 0 or row >= len(self.entries):
            W.warn(self, "حدد مدخلاً أولاً.")
            return None
        return self.entries[row]

    def _add(self) -> None:
        VaultEntryDialog(self, self.ctx).exec()
        self._refresh()

    def _edit(self) -> None:
        entry = self._selected()
        if entry:
            VaultEntryDialog(self, self.ctx, entry).exec()
            self._refresh()

    def _delete(self) -> None:
        entry = self._selected()
        if entry and W.confirm(self, f"حذف مدخل «{entry.get('label') or entry.get('institution')}»؟"):
            self.ctx.db.delete_vault_entry(int(entry["id"]))
            self.ctx.db.log(self.ctx.user(), "حذف", "vault", str(entry["id"]), "")
            self._refresh()

    def _toggle(self) -> None:
        self.show_passwords = not self.show_passwords
        self._refresh()

    def _copy(self) -> None:
        entry = self._selected()
        if entry:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(str(entry.get("password", "")))
            W.info(self, "نُسخت كلمة المرور إلى الحافظة.")

    def _export_card(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "حفظ بطاقة الاسترداد",
            str(self.ctx.paths.reports_dir / "بطاقة_استرداد_التشفير.html"),
            "HTML (*.html)")
        if not path:
            return
        rows = []
        for item in self.entries:
            rows.append(
                "<tr>"
                f"<td>{html.escape(KIND_LABELS.get(item.get('kind'), item.get('kind', '')))}</td>"
                f"<td>{html.escape(item.get('label', ''))}</td>"
                f"<td>{html.escape(item.get('institution', ''))}</td>"
                f"<td>{html.escape(item.get('file_name', ''))}</td>"
                f"<td dir='ltr'>{html.escape(item.get('password', ''))}</td>"
                f"<td>{html.escape(item.get('created_at', ''))}</td>"
                "</tr>")
        content = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar"><head><meta charset="utf-8">
<title>بطاقة استرداد كلمات المرور</title>
<style>
body {{ font-family: 'Segoe UI', Tahoma, Arial; background: #fff; color: #111; padding: 24px; }}
h1 {{ color: #0f766e; }} table {{ width: 100%; border-collapse: collapse; }}
th, td {{ border: 1px solid #999; padding: 6px 8px; font-size: 12px; }}
th {{ background: #e2e8f0; }} .warn {{ background:#fff7ed; border:1px solid #fb923c;
padding:10px; margin:12px 0; }}
</style></head><body>
<h1>بطاقة استرداد كلمات مرور النظام</h1>
<div class="warn">سرّي للغاية — اطبع هذه البطاقة واحفظها في مكان آمن خارج جهاز الحاسوب.
فقدان كلمة مرور قاعدة البيانات يعني فقدان القدرة على فتح النسخ الاحتياطية المشفّرة.</div>
<p>تاريخ التصدير: {datetime.now():%Y-%m-%d %H:%M}</p>
<table><thead><tr><th>النوع</th><th>التسمية</th><th>المؤسسة</th><th>الملف</th>
<th>كلمة المرور/المفتاح</th><th>التاريخ</th></tr></thead><tbody>
{''.join(rows) or '<tr><td colspan="6">لا توجد مداخل</td></tr>'}
</tbody></table>
</body></html>"""
        from pathlib import Path
        Path(path).write_text(content, encoding="utf-8")
        self.ctx.db.log(self.ctx.user(), "تصدير", "vault", "", "بطاقة استرداد")
        if W.confirm(self, f"تم حفظ البطاقة:\n{path}\n\nهل تريد فتحها للطباعة؟"):
            W.open_path(self, Path(path))
