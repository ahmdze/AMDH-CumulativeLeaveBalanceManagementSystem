"""حوارات الإدارة: ضوابط الأنواع، العطل، المستخدمون، الدخول، سجل التدقيق."""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from .. import config
from ..exporters import excel as X
from ..models import AppUser, Holiday
from ..rules import LeaveRule
from ..services import dates as D
from ..services import security
from . import theme, widgets as W
from .dialogs_base import BaseDialog
from .dialogs_login import LoginDialog  # noqa: F401  (نُقل إلى dialogs_login)
from ..i18n import tr, trf


# ---------------------------------------------------------------------------
# ضوابط أنواع الإجازات
# ---------------------------------------------------------------------------
class RuleEditDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None, rule: LeaveRule | None = None,
                 existing_types: set[str] | None = None, on_save=None):
        super().__init__(parent, ctx, tr("تعديل ضابط نوع إجازة") if rule else tr("إضافة نوع إجازة"))
        self.rule = rule
        self.existing = existing_types or set()
        self.on_save = on_save
        self.resize(520, 560)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        card = W.card()
        form = QFormLayout(card)
        form.setSpacing(9)
        rule = self.rule or LeaveRule(type="")
        self.e_type = QLineEdit(rule.type)
        self.e_type.setEnabled(self.rule is None)
        self.chk_consumes = QCheckBox(tr("يُخصم من الرصيد السنوي"))
        self.chk_consumes.setChecked(rule.consumes_balance)
        self.chk_exclusion = QCheckBox(tr("تُستبعد أيامه من أيام الخدمة"))
        self.chk_exclusion.setChecked(rule.service_exclusion)
        self.chk_adjustment = QCheckBox(tr("نوع تسوية (يسمح بقيم سالبة)"))
        self.chk_adjustment.setChecked(rule.is_adjustment)
        self.cb_mode = QComboBox()
        for key in config.COUNT_MODES:
            self.cb_mode.addItem(config.COUNT_MODE_LABELS[key], key)
        self.cb_mode.setCurrentIndex(0 if rule.count_mode == "calendar" else 1)
        self.sp_quota = QSpinBox()
        self.sp_quota.setRange(0, 3650)
        self.sp_quota.setValue(rule.quota_days)
        self.sp_quota.setSuffix(" يوم (0 = بلا سقف)")
        self.cb_period = QComboBox()
        for key in config.QUOTA_PERIODS:
            self.cb_period.addItem(config.QUOTA_PERIOD_LABELS[key], key)
        index = self.cb_period.findData(rule.quota_period)
        self.cb_period.setCurrentIndex(max(0, index))
        self.chk_order = QCheckBox(tr("يتطلب رقم الأمر"))
        self.chk_order.setChecked(rule.requires_order)
        self.cb_gender = QComboBox()
        self.cb_gender.addItem("للجميع", "")
        self.cb_gender.addItem("ذكر", "ذكر")
        self.cb_gender.addItem("أنثى", "أنثى")
        gi = self.cb_gender.findData(rule.gender)
        self.cb_gender.setCurrentIndex(max(0, gi))
        self.sp_order = QSpinBox()
        self.sp_order.setRange(0, 999)
        self.sp_order.setValue(rule.order_index)
        self.chk_active = QCheckBox(tr("مُفعَّل"))
        self.chk_active.setChecked(rule.active)
        self.e_notes = QTextEdit(rule.notes)
        self.e_notes.setFixedHeight(60)

        form.addRow(tr("اسم النوع *"), self.e_type)
        form.addRow("", self.chk_consumes)
        form.addRow("", self.chk_exclusion)
        form.addRow("", self.chk_adjustment)
        form.addRow(tr("طريقة العد"), self.cb_mode)
        form.addRow(tr("السقف"), self.sp_quota)
        form.addRow(tr("فترة السقف"), self.cb_period)
        form.addRow("", self.chk_order)
        form.addRow(tr("الجنس"), self.cb_gender)
        form.addRow(tr("ترتيب الظهور"), self.sp_order)
        form.addRow("", self.chk_active)
        form.addRow(tr("ملاحظات"), self.e_notes)
        layout.addWidget(card)
        layout.addWidget(W.muted_label(
            "ملاحظة: «تُستبعد من أيام الخدمة» تعني عدم خصمها من الرصيد وعدم احتسابها خدمةً "
            "(مثل إجازة 5 سنوات)."))
        layout.addStretch()
        layout.addLayout(self.buttons_row(W.button(tr("إلغاء"), "Ghost", self.reject, width=110),
                                          W.button(tr("💾 حفظ"), "Accent", self._save, width=140)))

    def _save(self) -> None:
        name = self.e_type.text().strip()
        if not name:
            W.error(self, tr("اسم النوع إلزامي."))
            return
        if self.rule is None and name in self.existing:
            W.error(self, tr("هذا النوع موجود مسبقاً."))
            return
        rule = LeaveRule(
            type=name,
            consumes_balance=self.chk_consumes.isChecked(),
            service_exclusion=self.chk_exclusion.isChecked(),
            count_mode=self.cb_mode.currentData(),
            quota_days=self.sp_quota.value(),
            quota_period=self.cb_period.currentData(),
            requires_order=self.chk_order.isChecked(),
            is_adjustment=self.chk_adjustment.isChecked(),
            gender=self.cb_gender.currentData() or "",
            order_index=self.sp_order.value(),
            active=self.chk_active.isChecked(),
            notes=self.e_notes.toPlainText().strip(),
        )
        self.ctx.db.save_rule(rule)
        self.ctx.db.log(self.ctx.user(), "تعديل", "rule", name, "تحديث ضابط نوع إجازة")
        if self.on_save:
            self.on_save()
        self.accept()


class RulesEditorDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, tr("ضوابط أنواع الإجازات"))
        self.resize(980, 620)
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label(tr("ضوابط أنواع الإجازات"), 15))
        layout.addWidget(W.muted_label(
            tr("لكل نوع: هل يُخصم من الرصيد؟ هل يُستبعد من أيام الخدمة؟ طريقة العد، وسقف اختياري.")))
        self.table = W.TablePanel([tr("النوع"), tr("يُخصم من الرصيد"), tr("يُستبعد من الخدمة"), tr("طريقة العد"),
                                   tr("السقف"), tr("يتطلب أمراً"), tr("الجنس"), tr("تسوية"), tr("مُفعَّل"), tr("ملاحظات")])
        layout.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(W.button(tr("➕ إضافة نوع"), "Accent", self._add))
        row.addWidget(W.button(tr("✏ تعديل المحدد"), "Blue", self._edit))
        row.addWidget(W.button(tr("🗑 حذف المحدد"), "Warn", self._delete))
        row.addStretch()
        row.addWidget(self.close_button())
        layout.addLayout(row)
        self._refresh()

    def _rules(self) -> list[LeaveRule]:
        rules = list(self.ctx.db.policy(refresh=True).rules.values())
        rules.sort(key=lambda r: (r.is_adjustment, r.order_index, r.type))
        return rules

    def _refresh(self) -> None:
        self._data = self._rules()
        rows = []
        for rule in self._data:
            rows.append([rule.type, "نعم" if rule.consumes_balance else "لا",
                         "نعم" if rule.service_exclusion else "لا", rule.count_mode_label,
                         rule.quota_label, "نعم" if rule.requires_order else "لا",
                         rule.gender or "الجميع", "نعم" if rule.is_adjustment else "لا",
                         "نعم" if rule.active else "لا", rule.notes])
        self.table.set_rows(rows, empty_text=tr("لا توجد أنواع معرّفة"),
                            footer=trf("عدد الأنواع: {v0}", v0=len(rows)))

    def _selected(self) -> LeaveRule | None:
        idx = self.table.current_row()
        if idx < 0:
            W.warn(self, tr("حدد نوعاً أولاً."))
            return None
        return self._data[idx]

    def _add(self) -> None:
        if not self.ctx.can("edit_rules"):
            W.error(self, tr("لا تملك صلاحية تعديل الضوابط."))
            return
        RuleEditDialog(self, self.ctx, None, {r.type for r in self._data},
                       on_save=self._refresh).exec()

    def _edit(self) -> None:
        rule = self._selected()
        if not rule:
            return
        if not self.ctx.can("edit_rules"):
            W.error(self, tr("لا تملك صلاحية تعديل الضوابط."))
            return
        RuleEditDialog(self, self.ctx, rule, on_save=self._refresh).exec()

    def _delete(self) -> None:
        rule = self._selected()
        if not rule:
            return
        if not self.ctx.can("edit_rules"):
            W.error(self, tr("لا تملك صلاحية تعديل الضوابط."))
            return
        if not W.confirm(self, f"حذف النوع «{rule.type}»؟\n"
                               "لن تتأثر الإجازات المسجلة مسبقاً بهذا النوع."):
            return
        self.ctx.db.delete_rule(rule.type)
        self._refresh()


# ---------------------------------------------------------------------------
# العطل الرسمية
# ---------------------------------------------------------------------------
class HolidaysDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, tr("العطل الرسمية"))
        self.resize(620, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label(tr("العطل الرسمية"), 15))
        layout.addWidget(W.muted_label("تُستبعد العطل من حساب «أيام العمل» للأنواع التي "
                                       "طريقة عدّها أيام عمل."))
        card = W.card()
        form = QFormLayout(card)
        self.e_name = QLineEdit()
        self.e_name.setPlaceholderText(tr("مثال: عيد العمال"))
        self.d_day = W.date_edit(date.today())
        form.addRow(tr("المناسبة"), self.e_name)
        form.addRow(tr("التاريخ"), self.d_day)
        layout.addWidget(card)
        layout.addLayout(W.button_row(W.button(tr("➕ إضافة"), "Accent", self._add), stretch=False))
        self.table = W.TablePanel(["#", tr("التاريخ"), tr("المناسبة"), tr("اليوم")])
        layout.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(W.button(tr("🗑 حذف المحدد"), "Warn", self._delete))
        row.addStretch()
        row.addWidget(self.close_button())
        layout.addLayout(row)
        self._refresh()

    def _refresh(self) -> None:
        self._data = self.ctx.db.list_holidays()
        rows = []
        for i, h in enumerate(self._data, 1):
            weekday = config.WEEKDAY_NAMES[h.day.weekday()] if h.day else ""
            rows.append([i, D.to_iso(h.day), h.name, weekday])
        self.table.set_rows(rows, empty_text=tr("لا توجد عطل مسجلة"))

    def _add(self) -> None:
        day = W.date_of(self.d_day)
        if not day:
            W.error(self, tr("تاريخ غير صالح."))
            return
        self.ctx.db.add_holiday(day, self.e_name.text().strip())
        self.ctx.db.log(self.ctx.user(), "إضافة", "holiday", D.to_iso(day), self.e_name.text())
        self._refresh()

    def _delete(self) -> None:
        idx = self.table.current_row()
        if idx < 0:
            W.warn(self, tr("حدد عطلة."))
            return
        item: Holiday = self._data[idx]
        self.ctx.db.delete_holiday(item.id)
        self._refresh()


# ---------------------------------------------------------------------------
# المستخدمون
# ---------------------------------------------------------------------------
class UserEditDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None, user: AppUser | None = None, on_save=None):
        super().__init__(parent, ctx, tr("تعديل مستخدم") if user else tr("إضافة مستخدم"))
        self.user = user
        self.on_save = on_save
        self.resize(460, 420)
        layout = QVBoxLayout(self)
        card = W.card()
        form = QFormLayout(card)
        user = user or AppUser(username="")
        self.e_username = QLineEdit(user.username)
        self.e_username.setEnabled(self.user is None)
        self.e_display = QLineEdit(user.display_name)
        self.cb_role = QComboBox()
        for key in config.ROLES:
            self.cb_role.addItem(config.ROLE_LABELS[key], key)
        index = self.cb_role.findData(user.role)
        self.cb_role.setCurrentIndex(max(0, index))
        self.e_institution = QLineEdit(user.institution)
        self.e_institution.setPlaceholderText(tr("اتركه فارغاً للوصول لكل المؤسسات"))
        self.chk_active = QCheckBox(tr("حساب مُفعَّل"))
        self.chk_active.setChecked(user.active if self.user else True)
        self.e_password = QLineEdit()
        self.e_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_password.setPlaceholderText(tr("اتركه فارغاً للإبقاء على الكلمة الحالية")
                                           if self.user else tr("كلمة المرور *"))
        self.e_password2 = QLineEdit()
        self.e_password2.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(tr("اسم المستخدم *"), self.e_username)
        form.addRow(tr("الاسم المعروض"), self.e_display)
        form.addRow(tr("الدور"), self.cb_role)
        form.addRow(tr("المؤسسة (تقييد)"), self.e_institution)
        form.addRow(tr("كلمة المرور"), self.e_password)
        form.addRow(tr("تأكيد كلمة المرور"), self.e_password2)
        form.addRow("", self.chk_active)
        layout.addWidget(card)
        layout.addWidget(W.muted_label("الأدوار: مدير النظام (كل الصلاحيات)، مدخل بيانات "
                                       "(إضافة وتعديل بلا حذف)، مطّلع فقط (قراءة وتصدير)."))
        layout.addStretch()
        layout.addLayout(self.buttons_row(W.button(tr("إلغاء"), "Ghost", self.reject, width=110),
                                          W.button(tr("💾 حفظ"), "Accent", self._save, width=140)))

    def _save(self) -> None:
        username = self.e_username.text().strip()
        if not username:
            W.error(self, tr("اسم المستخدم إلزامي."))
            return
        password = self.e_password.text()
        if password != self.e_password2.text():
            W.error(self, tr("كلمتا المرور غير متطابقتين."))
            return
        if not self.user and not password:
            W.error(self, tr("كلمة المرور إلزامية للمستخدم الجديد."))
            return
        if password:
            ok, message = security.password_strength(password)
            if not ok:
                W.error(self, message)
                return
        existing = self.ctx.db.get_user(username) if self.user is None else self.user
        if self.user is None and existing:
            W.error(self, tr("اسم المستخدم موجود مسبقاً."))
            return
        user = AppUser(
            username=username,
            display_name=self.e_display.text().strip() or username,
            role=self.cb_role.currentData(),
            institution=self.e_institution.text().strip(),
            password_hash=existing.password_hash if existing else "",
            salt=existing.salt if existing else "",
            iterations=existing.iterations if existing else security.ITERATIONS,
            active=self.chk_active.isChecked(),
            created_at=existing.created_at if existing else "",
            last_login=existing.last_login if existing else "",
        )
        if password:
            user.password_hash, user.salt, user.iterations = security.hash_password(password)
        self.ctx.db.save_user(user)
        self.ctx.db.log(self.ctx.user(), "تعديل", "user", username, f"الدور: {user.role}")
        if self.on_save:
            self.on_save()
        self.accept()


class UsersDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, tr("إدارة المستخدمين"))
        self.resize(820, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label(tr("المستخدمون والصلاحيات"), 15))
        layout.addWidget(W.muted_label(tr("تسجيل الدخول معطَّل افتراضياً من الإعدادات ← عام.")))
        self.table = W.TablePanel([tr("اسم المستخدم"), tr("الاسم"), tr("الدور"), tr("المؤسسة"), tr("مُفعَّل"),
                                   tr("آخر دخول"), tr("أُنشئ في")])
        layout.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(W.button(tr("➕ إضافة"), "Accent", self._add))
        row.addWidget(W.button(tr("✏ تعديل المحدد"), "Blue", self._edit))
        row.addWidget(W.button(tr("🔑 تغيير كلمة المرور"), "Gold", self._password))
        row.addWidget(W.button(tr("🗑 حذف المحدد"), "Warn", self._delete))
        row.addStretch()
        row.addWidget(self.close_button())
        layout.addLayout(row)
        self._refresh()

    def _refresh(self) -> None:
        self._data = self.ctx.db.list_users()
        rows = [[u.username, u.display_name, config.ROLE_LABELS.get(u.role, u.role),
                 u.institution or "الكل", "نعم" if u.active else "لا", u.last_login, u.created_at]
                for u in self._data]
        self.table.set_rows(rows, empty_text=tr("لا يوجد مستخدمون"),
                            footer=trf("عدد المستخدمين: {v0}", v0=len(rows)))

    def _guard(self) -> bool:
        if not self.ctx.can("manage_users"):
            W.error(self, tr("إدارة المستخدمين تتطلب صلاحية مدير النظام."))
            return False
        return True

    def _selected(self) -> AppUser | None:
        idx = self.table.current_row()
        if idx < 0:
            W.warn(self, tr("حدد مستخدماً."))
            return None
        return self._data[idx]

    def _add(self) -> None:
        if self._guard():
            UserEditDialog(self, self.ctx, None, on_save=self._refresh).exec()

    def _edit(self) -> None:
        user = self._selected()
        if user and self._guard():
            UserEditDialog(self, self.ctx, user, on_save=self._refresh).exec()

    def _password(self) -> None:
        user = self._selected()
        if not user or not self._guard():
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("تغيير كلمة المرور"))
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dialog.setStyleSheet(self.styleSheet())
        form = QFormLayout(dialog)
        p1 = QLineEdit()
        p1.setEchoMode(QLineEdit.EchoMode.Password)
        p2 = QLineEdit()
        p2.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(trf("كلمة المرور الجديدة لـ {v0}", v0=user.username), p1)
        form.addRow(tr("تأكيد"), p2)
        buttons = W.button_row(W.button(tr("إلغاء"), "Ghost", dialog.reject),
                               W.button(tr("حفظ"), "Accent", dialog.accept))
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if p1.text() != p2.text() or not p1.text():
            W.error(self, tr("كلمتا المرور غير متطابقتين أو فارغتان."))
            return
        ok, message = security.password_strength(p1.text())
        if not ok:
            W.error(self, message)
            return
        user.password_hash, user.salt, user.iterations = security.hash_password(p1.text())
        self.ctx.db.save_user(user)
        self.ctx.db.log(self.ctx.user(), "تعديل", "user", user.username, "تغيير كلمة المرور")
        W.info(self, tr("تم تغيير كلمة المرور."))
        self._refresh()

    def _delete(self) -> None:
        user = self._selected()
        if not user or not self._guard():
            return
        if user.username == self.ctx.user():
            W.error(self, tr("لا يمكنك حذف المستخدم الحالي."))
            return
        if self.ctx.db.get_user(user.username) and user.role == "admin" and \
                len([u for u in self._data if u.role == "admin"]) <= 1:
            W.error(self, tr("لا يمكن حذف آخر مدير نظام."))
            return
        if not W.confirm(self, trf("حذف المستخدم «{v0}»؟", v0=user.username)):
            return
        self.ctx.db.delete_user(user.username)
        self.ctx.db.log(self.ctx.user(), "حذف", "user", user.username, "")
        self._refresh()


# ---------------------------------------------------------------------------
# تسجيل الدخول
# ---------------------------------------------------------------------------
# سجل التدقيق
# ---------------------------------------------------------------------------
class AuditDialog(BaseDialog):
    def __init__(self, parent=None, ctx=None):
        super().__init__(parent, ctx, tr("سجل التدقيق"))
        self.resize(1000, 620)
        layout = QVBoxLayout(self)
        layout.addWidget(W.title_label(tr("سجل التدقيق (من فعل ماذا ومتى)"), 15))
        card = W.card()
        filters = QHBoxLayout(card)
        self.cb_user = QComboBox()
        self.cb_user.addItem("كل المستخدمين", "")
        for value in self.ctx.db.audit_values("username"):
            self.cb_user.addItem(value, value)
        self.cb_action = QComboBox()
        self.cb_action.addItem("كل الإجراءات", "")
        for value in self.ctx.db.audit_values("action"):
            self.cb_action.addItem(value, value)
        self.cb_entity = QComboBox()
        self.cb_entity.addItem("كل الكيانات", "")
        for value in self.ctx.db.audit_values("entity"):
            self.cb_entity.addItem(value, value)
        self.d_from = W.OptionalDate("من تاريخ", None)
        self.d_to = W.OptionalDate("إلى تاريخ", None)
        filters.addWidget(self.cb_user)
        filters.addWidget(self.cb_action)
        filters.addWidget(self.cb_entity)
        filters.addWidget(self.d_from)
        filters.addWidget(self.d_to)
        filters.addWidget(W.button(tr("🔍 تحديث"), "Blue", self._refresh))
        filters.addStretch()
        layout.addWidget(card)
        self.table = W.TablePanel(["#", tr("التاريخ والوقت"), tr("المستخدم"), tr("الإجراء"), tr("الكيان"),
                                   tr("المعرّف"), tr("التفاصيل")])
        layout.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(W.button(tr("📊 تصدير Excel"), "Ghost", self._export))
        row.addStretch()
        row.addWidget(self.close_button())
        layout.addLayout(row)
        self._refresh()

    def _refresh(self) -> None:
        entries = self.ctx.db.list_audit(
            username=self.cb_user.currentData() or "",
            action=self.cb_action.currentData() or "",
            entity=self.cb_entity.currentData() or "",
            date_from=D.to_iso(self.d_from.value()),
            date_to=D.to_iso(self.d_to.value()),
            limit=2000)
        self._data = entries
        rows = [[e.id, e.ts, e.username, e.action, e.entity, e.entity_id, e.details] for e in entries]
        self.table.set_rows(rows, numeric_columns={0}, empty_text=tr("لا توجد سجلات مطابقة"),
                            footer=trf("عدد السجلات المعروضة: {v0} (الأحدث أولاً، بحد أقصى 2000)", v0=len(rows)))

    def _export(self) -> None:
        if not self._data:
            W.warn(self, tr("لا توجد بيانات للتصدير."))
            return
        path, _ = QFileDialog.getSaveFileName(self, "حفظ سجل التدقيق", "audit_log.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            X.export_audit(path, self._data)
            W.info(self, trf("تم التصدير:\n{v0}", v0=path))
        except Exception as exc:
            W.error(self, trf("فشل التصدير: {v0}", v0=exc))
