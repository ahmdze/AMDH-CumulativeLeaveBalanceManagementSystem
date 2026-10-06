"""سياق التطبيق: يجمع المسارات وقاعدة البيانات والجلسة والإعدادات."""

from __future__ import annotations

from dataclasses import dataclass

from . import config
from .db import Database
from .models import Employee
from .rules import Policy
from .services.backup import BackupService
from .services.security import Session


@dataclass
class AppContext:
    paths: config.Paths
    db: Database
    backup: BackupService
    session: Session
    settings: object          # QSettings (لا نستورد PyQt6 هنا)

    # ------------------------------------------------------------------
    @property
    def policy(self) -> Policy:
        return self.db.policy()

    @property
    def read_only(self) -> bool:
        return self.session.read_only

    def can(self, permission: str) -> bool:
        return self.session.can(permission)

    def user(self) -> str:
        return self.session.username

    # ------------------------------------------------------------------
    def employees(self, q: str = "", workplace: str = "", institution: str = "",
                  include_deleted: bool = False) -> list[Employee]:
        scope = self.session.scoped_institution
        if scope:
            institution = scope
        return self.db.list_employees(q, workplace, institution,
                                      include_deleted=include_deleted, with_leaves=True)

    def institutions(self) -> list[str]:
        scope = self.session.scoped_institution
        return [scope] if scope else self.db.distinct_values("institution")

    def workplaces(self) -> list[str]:
        return self.db.distinct_values("workplace")

    def refresh_policy(self) -> Policy:
        self.db.invalidate_policy()
        return self.db.policy(refresh=True)

    # ------------------------------------------------------------------
    # إعدادات الواجهة
    # ------------------------------------------------------------------
    def ui_get(self, key: str, default=None, type_=None):
        try:
            if type_ is not None:
                return self.settings.value(key, default, type=type_)
            return self.settings.value(key, default)
        except (TypeError, AttributeError):
            return default

    def ui_set(self, key: str, value) -> None:
        try:
            self.settings.setValue(key, value)
        except AttributeError:
            pass
