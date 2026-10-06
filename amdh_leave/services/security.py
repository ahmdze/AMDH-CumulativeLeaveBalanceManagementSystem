"""الأمان: تجزئة كلمات المرور، الجلسة، والصلاحيات حسب الدور."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass, field

ITERATIONS = 200_000

# الصلاحيات
PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "edit_employee", "delete_employee", "purge", "edit_leave", "delete_leave",
        "manage_users", "edit_policy", "edit_rules", "backup_restore", "import_db",
        "export", "view_audit", "manage_holidays", "manage_attachments", "approve",
    },
    "editor": {
        "edit_employee", "edit_leave", "export", "manage_attachments", "approve",
    },
    "viewer": {"export"},
}

ROLE_ORDER = ("admin", "editor", "viewer")


def hash_password(password: str, salt: str | None = None,
                  iterations: int = ITERATIONS) -> tuple[str, str, int]:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt), iterations)
    return digest.hex(), salt, iterations


def verify_password(password: str, stored_hash: str, salt: str, iterations: int = ITERATIONS) -> bool:
    if not stored_hash or not salt:
        return False
    try:
        candidate, _salt, _it = hash_password(password, salt, iterations)
    except ValueError:
        return False
    return hmac.compare_digest(candidate, stored_hash)


def password_strength(password: str) -> tuple[bool, str]:
    if len(password) < 4:
        return False, "كلمة المرور قصيرة جداً (4 أحرف على الأقل)"
    if password.isdigit():
        return False, "لا تستخدم أرقاماً فقط"
    return True, ""


@dataclass
class Session:
    """هوية المستخدم الحالي وصلاحياته."""
    username: str = "—"
    display_name: str = ""
    role: str = "admin"
    institution: str = ""
    auth_enabled: bool = False
    permissions: set[str] = field(default_factory=lambda: set(PERMISSIONS["admin"]))

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def read_only(self) -> bool:
        return self.role == "viewer"

    @property
    def scoped_institution(self) -> str:
        """المؤسسة المقيَّد بها المستخدم (فارغ = كل المؤسسات)."""
        return "" if self.is_admin else (self.institution or "")


def make_session(user=None, auth_enabled: bool = False) -> Session:
    if user is None:
        return Session(username="—", display_name="مستخدم محلي", role="admin",
                       auth_enabled=auth_enabled,
                       permissions=set(PERMISSIONS["admin"]))
    return Session(username=user.username, display_name=user.display_name or user.username,
                   role=user.role if user.role in PERMISSIONS else "viewer",
                   institution=user.institution or "", auth_enabled=auth_enabled,
                   permissions=set(PERMISSIONS.get(user.role, PERMISSIONS["viewer"])))
