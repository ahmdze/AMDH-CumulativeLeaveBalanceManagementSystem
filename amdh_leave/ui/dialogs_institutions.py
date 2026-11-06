"""واجهة إدارة المؤسسات: إضافة/تعديل/حذف، استيراد وتصدير Excel، والمستخدم المرتبط.

كل مؤسسة لها مستخدم مرتبط تلقائياً؛ وهذا المستخدم مقيَّد بمؤسسته فيرى ويُدخل بيانات
موظفي مؤسسته فقط، ثم يصدّر «ملف نقل» ليستورده مدير المركز.
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
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QVBoxLayout,
)

from .. import config
from ..services import institutions as INST
from ..services import merge as M
from ..services import provisioning as P
from . import dialogs_import as DI
from . import theme
from . import widgets as W
from .dialogs_credentials import CredentialsDialog
from .dialogs_export import export_for_center

COLUMNS = [
    ("المؤسسة", 230, "name"),
    ("الرمز", 80, "code"),
    ("النوع", 120, "kind"),
    ("المستخدم المرتبط", 130, "username"),
    ("الموظفون", 80, "employees"),
    ("آخر استيراد", 150, "last_import_at"),
    ("أرسلت هذا الشهر", 120, "reported"),
    ("مُفعّلة", 80, "active"),
]


# ---------------------------------------------------------------------------
# نموذج إضافة/تعديل مؤسسة
# ---------------------------------------------------------------------------
class InstitutionDialog(QDialog):
    """إضافة أو تعديل مؤسسة (مع خيار إنشاء المستخدم المرتبط)."""

    def __init__(self, parent, ctx, institution=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.institution = institution
        self.result_data: dict | None = None
        self.created_user: dict | None = None
        self.setWindowTitle("تعديل مؤسسة" if institution else "إضافة مؤسسة")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(560)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        self._build()
        if institution:
            self._load(institution)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        card = W.card()
        grid = QGridLayout(card)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(9)

        self.e_name = QLineEdit()
        self.e_name.setPlaceholderText("مثال: مستشفى الكرامة")
        self.e_code = QLineEdit()
        self.e_code.setPlaceholderText("رمز قصير لاتيني يُستخدم لاسم المستخدم (H1)")
        self.cb_kind = QComboBox()
        self.cb_kind.addItems(INST.KINDS)
        self.e_manager = QLineEdit()
        self.e_phone = QLineEdit()
        self.e_address = QLineEdit()
        self.e_notes = QPlainTextEdit()
        self.e_notes.setFixedHeight(58)
        self.e_username = QLineEdit()
        self.e_username.setPlaceholderText("يُولَّد تلقائياً إن تُرك فارغاً")
        self.chk_active = QCheckBox("مُفعّلة")
        self.chk_active.setChecked(True)
        self.chk_center = QCheckBox("هذه هي مؤسسة مركز الدائرة (النسخة الرئيسية)")
        self.chk_user = QCheckBox("إنشاء/تحديث مستخدم مرتبط بهذه المؤسسة")
        self.chk_user.setChecked(True)
        self.cb_password = QComboBox()
        self.cb_password.addItem("توليد كلمة مرور عشوائية", "generate")
        self.cb_password.addItem("كلمة مرور موحّدة أدخلها", "unified")
        self.e_password = QLineEdit()
        self.e_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_password.setPlaceholderText("كلمة المرور الموحّدة")
        self.e_password.setEnabled(False)
        self.cb_password.currentIndexChanged.connect(
            lambda: self.e_password.setEnabled(self.cb_password.currentData() == "unified")
        )

        rows = [
            ("اسم المؤسسة *", self.e_name),
            ("الرمز", self.e_code),
            ("النوع", self.cb_kind),
            ("المدير/المسؤول", self.e_manager),
            ("الهاتف", self.e_phone),
            ("العنوان", self.e_address),
            ("ملاحظات", self.e_notes),
            ("اسم المستخدم", self.e_username),
            ("الحالة", self.chk_active),
        ]
        for index, (label, widget) in enumerate(rows):
            grid.addWidget(QLabel(label), index, 0)
            grid.addWidget(widget, index, 1)
        grid.addWidget(self.chk_center, len(rows), 0, 1, 2)
        grid.addWidget(self.chk_user, len(rows) + 1, 0, 1, 2)
        grid.addWidget(self.cb_password, len(rows) + 2, 0)
        grid.addWidget(self.e_password, len(rows) + 2, 1)
        grid.setColumnStretch(1, 1)
        layout.addWidget(card)

        self.lbl_hint = W.muted_label(
            "المستخدم المرتبط يرى موظفي مؤسسته فقط ويستطيع تصدير ملف نقل ليستورده المركز."
        )
        layout.addWidget(self.lbl_hint)

        buttons = QHBoxLayout()
        buttons.addWidget(W.button("💾 حفظ", "Accent", self._save, width=120))
        buttons.addWidget(W.button("إلغاء", "Ghost", self.reject, width=90))
        buttons.addStretch()
        layout.addLayout(buttons)

    def _load(self, institution) -> None:
        self.e_name.setText(institution.name)
        self.e_name.setEnabled(False)
        self.e_code.setText(institution.code)
        index = self.cb_kind.findText(institution.kind)
        self.cb_kind.setCurrentIndex(max(0, index))
        self.e_manager.setText(institution.manager)
        self.e_phone.setText(institution.phone)
        self.e_address.setText(institution.address)
        self.e_notes.setPlainText(institution.notes)
        self.e_username.setText(institution.username)
        self.chk_active.setChecked(institution.active)
        self.chk_center.setChecked(institution.is_center)
        self.chk_user.setChecked(False)

    def _save(self) -> None:
        name = self.e_name.text().strip()
        if not name:
            W.warn(self, "اسم المؤسسة إلزامي.")
            return
        existing = self.ctx.db.get_institution(name)
        if (
            existing is None
            and self.institution is None
            and name in {item.name for item in self.ctx.db.list_institutions()}
        ):
            W.warn(self, "توجد مؤسسة بهذا الاسم.")
            return
        data = {
            "name": name,
            "code": self.e_code.text().strip(),
            "kind": self.cb_kind.currentText(),
            "manager": self.e_manager.text().strip(),
            "phone": self.e_phone.text().strip(),
            "address": self.e_address.text().strip(),
            "notes": self.e_notes.toPlainText().strip(),
            "username": self.e_username.text().strip(),
            "active": self.chk_active.isChecked(),
            "is_center": self.chk_center.isChecked(),
        }
        institution = self.ctx.db.save_institution(data, self.ctx.user())
        if self.chk_center.isChecked():
            self.ctx.db.set_center_institution(name)
        if self.chk_user.isChecked():
            mode = self.cb_password.currentData()
            password = self.e_password.text() if mode == "unified" else ""
            if mode == "unified" and not password:
                W.warn(self, "أدخل كلمة المرور الموحّدة أو اختر التوليد التلقائي.")
                return
            account, plain = INST.create_user_for_institution(
                self.ctx.db, institution, password=password, user=self.ctx.user()
            )
            self.created_user = {"institution": name, "username": account.username, "password": plain}
        self.result_data = data
        self.accept()


# ---------------------------------------------------------------------------
# استيراد المؤسسات من Excel
# ---------------------------------------------------------------------------
class ImportInstitutionsDialog(QDialog):
    """استيراد مؤسسات من Excel: معاينة الأعمدة ثم الإنشاء مع المستخدمين."""

    def __init__(self, parent, ctx, path: Path) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.path = Path(path)
        self.headers: list[str] = []
        self.rows: list[dict] = []
        self.mapping: dict[str, str] = {}
        self.result: dict | None = None
        self.setWindowTitle("استيراد مؤسسات من Excel")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumSize(760, 560)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        self._build()
        self._load()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(9)
        layout.addWidget(QLabel(f"الملف: {self.path.name}"))
        self.lbl_summary = W.muted_label("")
        layout.addWidget(self.lbl_summary)

        card = W.card()
        grid = QGridLayout(card)
        grid.setHorizontalSpacing(10)
        self.combos: dict[str, QComboBox] = {}
        for index, (key, label, _synonyms) in enumerate(INST.INSTITUTION_FIELDS):
            combo = QComboBox()
            combo.addItem("— بلا —", "")
            self.combos[key] = combo
            grid.addWidget(QLabel(label), index // 2, (index % 2) * 2)
            grid.addWidget(combo, index // 2, (index % 2) * 2 + 1)
        layout.addWidget(card)

        options = QHBoxLayout()
        self.chk_users = QCheckBox("إنشاء مستخدم مرتبط لكل مؤسسة")
        self.chk_users.setChecked(True)
        self.cb_password = QComboBox()
        self.cb_password.addItem("توليد كلمة مرور لكل مؤسسة", "generate")
        self.cb_password.addItem("كلمة مرور موحّدة", "unified")
        self.e_password = QLineEdit()
        self.e_password.setPlaceholderText("كلمة المرور الموحّدة")
        self.e_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_password.setEnabled(False)
        self.cb_password.currentIndexChanged.connect(
            lambda: self.e_password.setEnabled(self.cb_password.currentData() == "unified")
        )
        self.chk_update = QCheckBox("تحديث المؤسسات الموجودة")
        self.chk_update.setChecked(True)
        options.addWidget(self.chk_users)
        options.addWidget(self.cb_password)
        options.addWidget(self.e_password)
        options.addWidget(self.chk_update)
        options.addStretch()
        layout.addLayout(options)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview, 1)

        buttons = QHBoxLayout()
        self.btn_import = W.button("📥 استيراد", "Accent", self._import, width=130)
        buttons.addWidget(self.btn_import)
        buttons.addWidget(W.button("إلغاء", "Ghost", self.reject, width=90))
        buttons.addStretch()
        layout.addLayout(buttons)

    def _load(self) -> None:
        try:
            self.headers, self.rows = INST.read_excel(self.path)
        except Exception as exc:  # noqa: BLE001
            W.error(self, f"تعذّر قراءة الملف: {exc}")
            self.reject()
            return
        self.mapping = INST.guess_mapping(self.headers)
        for key, combo in self.combos.items():
            combo.addItems(self.headers)
            target = self.mapping.get(key, "")
            if target:
                combo.setCurrentText(target)
            combo.currentTextChanged.connect(self._refresh_preview)
        self.lbl_summary.setText(f"عدد الصفوف: {len(self.rows)} | الأعمدة المكتشفة: {len(self.headers)}")
        self._refresh_preview()

    def _current_mapping(self) -> dict[str, str]:
        return {
            key: (combo.currentText() if combo.currentIndex() > 0 else "")
            for key, combo in self.combos.items()
        }

    def _refresh_preview(self) -> None:
        mapping = self._current_mapping()
        lines = ["معاينة أول الصفوف:"]
        existing = {item.name for item in self.ctx.db.list_institutions()}
        seen: set[str] = set()
        for index, raw in enumerate(self.rows[:12], start=1):
            row = INST.normalize_row(raw, mapping)
            issues = INST.validate_row(row, existing, seen)
            seen.add(row["name"])
            notes = " ".join(issue.message for issue in issues)
            users = (
                "مستخدم جديد"
                if self.chk_users.isChecked() and row["name"] not in existing
                else ("تحديث" if row["name"] in existing else "")
            )
            lines.append(
                f"{index}. {row['name'] or '(بلا اسم)'} | {row['code']} | {row['kind']} | {users} {notes}"
            )
        if len(self.rows) > 12:
            lines.append(f"… وبقية {len(self.rows) - 12} صفاً")
        self.preview.setPlainText("\n".join(lines))

    def _import(self) -> None:
        mode = self.cb_password.currentData()
        password = self.e_password.text()
        if self.chk_users.isChecked() and mode == "unified" and not password:
            W.warn(self, "أدخل كلمة المرور الموحّدة.")
            return
        self.result = INST.import_from_rows(
            self.ctx.db,
            self.rows,
            self._current_mapping(),
            user=self.ctx.user(),
            create_users=self.chk_users.isChecked(),
            password_mode=mode,
            unified_password=password,
            update_existing=self.chk_update.isChecked(),
        )
        self.accept()


# ---------------------------------------------------------------------------
# إدارة المؤسسات
# ---------------------------------------------------------------------------
class InstitutionsDialog(QDialog):
    def __init__(self, parent, ctx) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("المؤسسات")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumSize(1080, 640)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        self._build()
        self._refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        header = QHBoxLayout()
        title = QLabel("🏥  المؤسسات")
        title.setStyleSheet(theme.label_style("accent", 15, bold=True))
        header.addWidget(title)
        header.addStretch()
        self.lbl_summary = W.muted_label("")
        header.addWidget(self.lbl_summary)
        layout.addLayout(header)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("البحث:"))
        self.e_search = QLineEdit()
        self.e_search.setPlaceholderText("اسم المؤسسة أو الرمز أو المستخدم")
        self.e_search.textChanged.connect(self._refresh)
        filters.addWidget(self.e_search, 2)
        filters.addWidget(QLabel("الحالة:"))
        self.cb_filter = QComboBox()
        self.cb_filter.addItem("الكل", "all")
        self.cb_filter.addItem("أرسلت هذا الشهر", "reported")
        self.cb_filter.addItem("لم تُرسل هذا الشهر", "pending")
        self.cb_filter.addItem("المُعطّلة", "inactive")
        self.cb_filter.currentIndexChanged.connect(self._refresh)
        filters.addWidget(self.cb_filter)
        filters.addStretch()
        filters.addWidget(W.button("🔄 تحديث", "Ghost", self._refresh))
        layout.addLayout(filters)

        self.table = W.TablePanel([column[0] for column in COLUMNS])
        self.table.table.itemSelectionChanged.connect(self._on_selection)
        self.table.table.doubleClicked.connect(lambda _i: self._edit())
        for index, (_title, width, _key) in enumerate(COLUMNS):
            self.table.table.setColumnWidth(index, width)
        self.table.table.setColumnHidden(7, False)
        layout.addWidget(self.table, 1)

        row1 = QHBoxLayout()
        row1.addWidget(W.button("➕ إضافة مؤسسة", "Accent", self._add))
        row1.addWidget(W.button("✏ تعديل", "Ghost", self._edit))
        row1.addWidget(W.button("🗑 حذف", "Warn", self._delete))
        row1.addWidget(W.button("🔑 إنشاء/تصفير المستخدم", "Blue", self._reset_user))
        row1.addWidget(W.button("👤 مستخدمو المؤسسات", "Ghost", self._open_users))
        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(W.button("📊 تصدير Excel", "Gold", self._export_excel))
        row2.addWidget(W.button("📂 استيراد Excel", "Gold", self._import_excel))
        row2.addWidget(W.button("📄 قالب Excel", "Ghost", self._template))
        row2.addWidget(W.button("📋 سجل الاستيراد", "Ghost", self._open_history))
        row2.addStretch()
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(W.button("📥 استيراد ملف مؤسسة", "Accent", self._import_transfer))
        row3.addWidget(W.button("📤 تصدير ملف نقل للمؤسسة", "Blue", self._export_transfer))
        row3.addWidget(W.button("📦 تجهيز نسخة المؤسسة", "Gold", self._provision))
        row3.addWidget(W.button("🖨 آخر تقرير استيراد", "Ghost", self._last_report))
        row3.addWidget(W.button("⚠ المؤسسات التي لم تُرسل", "Warn", self._show_pending))
        row3.addStretch()
        row3.addWidget(W.button("إغلاق", "Ghost", self.accept, width=90))
        layout.addLayout(row3)

    # -- عرض -----------------------------------------------------------
    def _refresh(self) -> None:
        status = INST.institutions_status(self.ctx.db)
        search = self.e_search.text().strip().lower()
        mode = self.cb_filter.currentData()
        rows = []
        for item in status:
            if search and search not in f"{item['name']} {item['code']}".lower():
                continue
            if mode == "reported" and not item["reported_this_month"]:
                continue
            if mode == "pending" and (item["reported_this_month"] or item["is_center"]):
                continue
            if mode == "inactive" and item["active"]:
                continue
            rows.append(item)
        self.table.set_rows(
            [
                [
                    item["name"],
                    item["code"],
                    item["kind"],
                    item.get("username") or "",
                    item["employees"],
                    item["last_import_at"] or "—",
                    "نعم" if item["reported_this_month"] else "لا",
                    "نعم" if item["active"] else "لا",
                ]
                for item in rows
            ]
        )
        total = len(status)
        pending = len(
            [
                item
                for item in status
                if not item["reported_this_month"] and not item["is_center"] and item["active"]
            ]
        )
        employees = self.ctx.db.stats()["employees"]
        self.lbl_summary.setText(f"المؤسسات: {total} | الموظفون: {employees} | لم تُرسل هذا الشهر: {pending}")

    def _selected_name(self) -> str:
        row = self.table.current_row()
        if row < 0:
            return ""
        item = self.table.table.item(row, 0)
        return item.text() if item else ""

    def _on_selection(self) -> None:
        name = self._selected_name()
        if name:
            self.ctx.db.set_meta({"last_institution": name})

    # -- عمليات --------------------------------------------------------
    def _show_credentials(self, institution, username: str, password: str) -> None:
        CredentialsDialog(
            self,
            self.ctx,
            institution=institution.name,
            code=institution.code,
            username=username,
            password=password,
            role_label=config.ROLE_LABELS.get("editor", "مدخل بيانات"),
        ).exec()

    def _add(self) -> None:
        dialog = InstitutionDialog(self, self.ctx)
        if dialog.exec() and dialog.created_user:
            institution = self.ctx.db.get_institution(dialog.created_user["institution"])
            if institution:
                self._show_credentials(
                    institution, dialog.created_user["username"], dialog.created_user["password"]
                )
        self._refresh()

    def _edit(self) -> None:
        name = self._selected_name()
        if not name:
            W.warn(self, "حدد مؤسسة أولاً.")
            return
        institution = self.ctx.db.get_institution(name)
        if institution is None:
            return
        dialog = InstitutionDialog(self, self.ctx, institution)
        if dialog.exec() and dialog.created_user:
            refreshed = self.ctx.db.get_institution(name) or institution
            self._show_credentials(
                refreshed, dialog.created_user["username"], dialog.created_user["password"]
            )
        self._refresh()

    def _delete(self) -> None:
        name = self._selected_name()
        if not name:
            W.warn(self, "حدد مؤسسة أولاً.")
            return
        if not W.confirm(
            self,
            f"حذف المؤسسة «{name}» ومستخدمها المرتبط؟\n\nلا يمكن التراجع، ولا يمكن الحذف إن كان لها موظفون.",
        ):
            return
        ok, message = self.ctx.db.delete_institution(name, user=self.ctx.user())
        (W.info if ok else W.warn)(self, message)
        self._refresh()

    def _reset_user(self) -> None:
        name = self._selected_name()
        if not name:
            W.warn(self, "حدد مؤسسة أولاً.")
            return
        institution = self.ctx.db.get_institution(name)
        if institution is None:
            return
        if not W.confirm(
            self, f"إنشاء/تصفير مستخدم المؤسسة «{name}»؟\n\nستُنشأ كلمة مرور جديدة تُعرض مرة واحدة."
        ):
            return
        account, password = INST.create_user_for_institution(self.ctx.db, institution, user=self.ctx.user())
        self._show_credentials(institution, account.username, password)
        self._refresh()

    def _open_users(self) -> None:
        from . import dialogs_admin

        dialogs_admin.UsersDialog(self, self.ctx).exec()

    def _export_excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "تصدير المؤسسات", "المؤسسات.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            output = INST.export_excel(path, self.ctx.db)
        except Exception as exc:  # noqa: BLE001
            W.error(self, f"تعذّر التصدير: {exc}")
            return
        if W.confirm(self, f"تم التصدير إلى:\n{output}\n\nهل تريد فتحه الآن؟"):
            W.open_path(self, output)

    def _template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "قالب استيراد المؤسسات", "قالب_المؤسسات.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            output = INST.export_template(path)
        except Exception as exc:  # noqa: BLE001
            W.error(self, f"تعذّر إنشاء القالب: {exc}")
            return
        W.info(self, f"أُنشئ القالب: {output}")

    def _import_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "استيراد مؤسسات من Excel", "", "Excel (*.xlsx *.xlsm)")
        if not path:
            return
        dialog = ImportInstitutionsDialog(self, self.ctx, Path(path))
        if dialog.exec() and dialog.result:
            result = dialog.result
            lines = [
                f"أُضيفت: {result['added']}",
                f"حُدِّثت: {result['updated']}",
                f"تُجوهلت: {result['skipped']}",
            ]
            if result["users"]:
                lines.append("")
                lines.append("المستخدمون المُنشأون:")
                lines.extend(
                    f"  • {item['institution']} — {item['username']} / {item['password']}"
                    for item in result["users"][:40]
                )
            if result["errors"]:
                lines.append("")
                lines.extend("⚠ " + error for error in result["errors"][:15])
            if result["users"] and W.confirm(
                self, "\n".join(lines) + "\n\nهل تريد حفظ بيانات الدخول في ملف Excel؟", "نتيجة الاستيراد"
            ):
                target, _ = QFileDialog.getSaveFileName(
                    self, "حفظ بيانات الدخول", "بيانات_دخول_المؤسسات.xlsx", "Excel (*.xlsx)"
                )
                if target:
                    INST.export_credentials(target, result["users"])
                    W.open_path(self, target)
            else:
                W.info(self, "\n".join(lines), "نتيجة الاستيراد")
        self._refresh()

    def _import_transfer(self) -> None:
        DI.TransferImportDialog(self, self.ctx).exec()
        self._refresh()

    def _export_transfer(self) -> None:
        name = self._selected_name()
        if not name:
            W.warn(self, "حدد مؤسسة لتصدير ملف نقله.")
            return
        export_for_center(self, self.ctx, name)
        self._refresh()

    def _provision(self) -> None:
        """تجهيز حزمة تشغيل كاملة للمؤسسة (برنامج + بيانات + مستخدم + مفتاح)."""
        name = self._selected_name()
        if not name:
            W.warn(self, "حدد مؤسسة أولاً.")
            return
        if not self.ctx.session.is_admin:
            W.error(self, "تجهيز نسخ المؤسسات متاح لمدير النظام فقط.")
            return
        institution = self.ctx.db.get_institution(name)
        if institution is None:
            return
        if institution.is_center or self.ctx.db.center_institution() == name:
            W.warn(self, "لا يمكن تجهيز نسخة لمؤسسة مركز الدائرة نفسها.")
            return
        admin_password, ok = QInputDialog.getText(
            self,
            "نسخة المؤسسة",
            "كلمة مرور admin للصيانة في هذه النسخة:\n(تُحفظ كبصمة فقط، ولا تُكتب في ملفات الحزمة)",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not admin_password:
            return
        if len(admin_password) < 8:
            if not W.confirm(self, "كلمة مرور الصيانة قصيرة (أقل من 8 أحرف).\nهل تريد المتابعة على أي حال؟"):
                return
        if not W.confirm(
            self,
            f"سيُجهَّز مجلد كامل للمؤسسة «{name}» يحوي:\n"
            "• نسخة البرنامج (AMDH-Leave.exe و_internal)\n"
            "• قاعدة بيانات مؤسستها + admin + مستخدمها\n"
            "• مفتاح فتح تلقائي + مرفقات + بيانات دخول\n\n"
            "وسيُصفَّر مستخدم المؤسسة الحالي وتُعرض كلمة مروره الجديدة مرة واحدة.\n"
            "متابعة؟",
            "تجهيز نسخة المؤسسة",
        ):
            return
        parent = QFileDialog.getExistingDirectory(self, "اختر مجلداً لحزمة المؤسسة")
        if not parent:
            return
        try:
            account, user_password = INST.create_user_for_institution(
                self.ctx.db, institution, user=self.ctx.user()
            )
        except Exception as exc:  # noqa: BLE001
            W.error(self, f"تعذّر إنشاء مستخدم المؤسسة: {exc}")
            return
        code = (institution.code or "INST").replace(" ", "_")
        folder = Path(parent) / f"AMDH_{code}_{datetime.now():%Y%m%d}"
        suffix = 2
        while folder.exists():
            folder = Path(parent) / f"AMDH_{code}_{datetime.now():%Y%m%d}_{suffix}"
            suffix += 1
        try:
            result = P.build_institution_folder(
                self.ctx,
                name,
                folder,
                admin_password=admin_password,
                user_password=user_password,
                include_program=True,
                make_zip=True,
            )
        except Exception as exc:  # noqa: BLE001
            W.error(
                self,
                f"تعذّر تجهيز الحزمة: {exc}\n\n"
                f"مستخدم المؤسسة: {account.username}\nكلمة المرور: {user_password}",
            )
            return
        try:
            package_file = result.get("zip") or result.get("folder")
            file_name = Path(package_file).name if package_file else ""
            self.ctx.db.add_vault_entry(
                kind="institution_key",
                label=f"مفتاح نسخة {name}",
                institution=name,
                file_name=file_name,
                file_path=str(result.get("folder", "")),
                password=result["key"],
                note="مفتاح فتح تلقائي لنسخة المؤسسة.",
                user=self.ctx.user(),
            )
            self.ctx.db.add_vault_entry(
                kind="maintenance",
                label=f"admin — {name}",
                institution=name,
                file_name=file_name,
                password=admin_password,
                note="كلمة مرور حساب الصيانة في نسخة المؤسسة.",
                user=self.ctx.user(),
            )
            self.ctx.db.add_vault_entry(
                kind="institution_user",
                label=result["username"],
                institution=name,
                file_name=file_name,
                password=result["password"],
                note="حساب مدخل البيانات في نسخة المؤسسة.",
                user=self.ctx.user(),
            )
        except Exception:  # noqa: BLE001
            pass
        lines = [
            f"تم تجهيز نسخة المؤسسة: {name}",
            f"المجلد: {result['folder']}",
        ]
        if result.get("zip"):
            lines.append(f"ملف ZIP: {result['zip']}")
        lines.extend(
            [
                "",
                f"اسم المستخدم: {result['username']}",
                f"كلمة المرور: {result['password']}",
                f"الموظفون: {result['counts']['employees']} | "
                f"الإجازات: {result['counts']['leaves']} | "
                f"المرفقات: {result['counts']['attachments']}",
                "",
                "حساب admin في النسخة يستخدم كلمة مرور الصيانة التي أدخلتها، وهي غير مكتوبة في الحزمة.",
                "سلّم بيانات_الدخول.txt مع الحزمة، واحفظ كلمة مرور admin في مكان آمن.",
            ]
        )
        W.info(self, "\n".join(lines), "نسخة المؤسسة")
        self._refresh()

    def _open_history(self) -> None:
        DI.ImportHistoryDialog(self, self.ctx).exec()

    def _last_report(self) -> None:
        name = self._selected_name()
        if not name:
            W.warn(self, "حدد مؤسسة أولاً.")
            return
        record = self.ctx.db.last_import_for(name)
        if record is None:
            W.info(self, "لا يوجد سجل استيراد لهذه المؤسسة بعد.")
            return
        report = M.MergeReport.from_json(record.report)
        if not report.source_file:
            report.source_file = record.source_file
            report.institution = record.institution
        DI.ReportDialog(self, self.ctx, report, record=record).exec()

    def _show_pending(self) -> None:
        pending = INST.pending_institutions(self.ctx.db)
        if not pending:
            W.info(self, "كل المؤسسات أرسلت بياناتها هذا الشهر. ✅")
            return
        lines = [f"المؤسسات التي لم تُرسل بياناتها في شهر {INST.month_label()} ({len(pending)}):", ""]
        lines.extend(
            f"  • {item['name']} ({item['code']}) — آخر استيراد: {item['last_import_at'] or 'لا يوجد'}"
            for item in pending
        )
        W.warn(self, "\n".join(lines), "المتابعة الشهرية")
