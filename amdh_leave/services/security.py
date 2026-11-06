"""الأمان: تجزئة كلمات المرور، رموز الجلسة، الضغط التلقائي للمرفقات، والصلاحيات حسب الدور."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

ITERATIONS = 200_000
TOKEN_TTL_SECONDS = 8 * 3600  # 8 ساعات صلاحية رمز الـ API

# مفتاح توقيع رموز الجلسة للـ API (يُشتق من بيئة التشغيل أو يُولَّد)
_API_SECRET = os.environ.get("AMDH_API_SECRET", "") or secrets.token_hex(32)

# الصلاحيات:
# حُصرت صلاحيات الحذف النهائي (purge) وتعديل السياسة العامة (edit_policy) بمدير النظام (admin)
# لمنع المؤسسات الفرعية من تغيير معادلات الاحتساب أو إتلاف السجلات نهائياً.
PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "edit_employee",
        "delete_employee",
        "purge",
        "edit_leave",
        "delete_leave",
        "manage_users",
        "edit_policy",
        "edit_rules",
        "backup_restore",
        "import_db",
        "export",
        "view_audit",
        "view_holidays",
        "manage_holidays",
        "manage_attachments",
        "approve",
        "manage_institutions",
        "import_transfer",
        "export_transfer",
        "transfer_employee",
        "manage_encryption",
        "db_operations",
    },
    "editor": {
        "edit_employee",
        "delete_employee",
        "edit_leave",
        "delete_leave",
        "export",
        "manage_attachments",
        "approve",
        "export_transfer",
        "view_holidays",
        "manage_holidays",
        "transfer_employee",
        "backup_restore",
        "manage_encryption",
        "db_operations",
    },
    "viewer": {"export", "view_holidays"},
}

ROLE_ORDER = ("admin", "editor", "viewer")


def hash_password(
    password: str, salt: str | None = None, iterations: int = ITERATIONS
) -> tuple[str, str, int]:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
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


# ---------------------------------------------------------------------------
# رموز الجلسة الموقّعة (Signed Session Tokens لـ REST API)
# ---------------------------------------------------------------------------
def create_api_token(username: str, role: str = "viewer", institution: str = "", ttl: int = TOKEN_TTL_SECONDS) -> str:
    """ينشئ رمز مصادقة موقّع بـ HMAC-SHA256 مع وقت انتهاء الصلاحية."""
    payload = {
        "sub": username,
        "role": role,
        "inst": institution,
        "exp": int(time.time()) + int(ttl),
        "jti": secrets.token_hex(8),
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = hmac.new(_API_SECRET.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def verify_api_token(token: str) -> dict | None:
    """يتحقق من توقيع وصلاحية الرمز ويعيد حمولته (أو None عند الفشل/الانتهاء)."""
    if not token or "." not in token:
        return None
    b64, sig = token.rsplit(".", 1)
    expected = hmac.new(_API_SECRET.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    padding = "=" * (-len(b64) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(b64 + padding).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict) or not data.get("sub"):
        return None
    if int(data.get("exp") or 0) < int(time.time()):
        return None
    return data


# ---------------------------------------------------------------------------
# الضغط الذكي لصور المرفقات (Scanner & Image Compression)
# ---------------------------------------------------------------------------
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def copy_or_compress_attachment(
    source: str | Path, dest_dir: str | Path, *, max_dim: int = 1800, quality: int = 82
) -> Path:
    """ينسخ ملف المرفق مع ضغط تلقائي ذكي للصور الضخمة لتقليل حجم القاعدة وملفات النقل."""
    import shutil
    import uuid

    source = Path(source)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()

    if suffix in IMAGE_EXTENSIONS:
        try:
            from PIL import Image

            with Image.open(source) as img:
                width, height = img.size
                needs_resize = width > max_dim or height > max_dim
                is_heavy = source.stat().st_size > 350 * 1024  # أكبر من 350 كيلوبايت
                if needs_resize or is_heavy or suffix in {".bmp", ".tif", ".tiff"}:
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    if needs_resize:
                        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                    target = dest_dir / f"{uuid.uuid4().hex}.jpg"
                    img.save(target, format="JPEG", quality=quality, optimize=True)
                    return target
        except Exception:  # noqa: BLE001
            pass

    target = dest_dir / f"{uuid.uuid4().hex}{suffix}"
    shutil.copy2(source, target)
    return target


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
        return Session(
            username="—",
            display_name="مستخدم محلي",
            role="admin",
            auth_enabled=auth_enabled,
            permissions=set(PERMISSIONS["admin"]),
        )
    return Session(
        username=user.username,
        display_name=user.display_name or user.username,
        role=user.role if user.role in PERMISSIONS else "viewer",
        institution=user.institution or "",
        auth_enabled=auth_enabled,
        permissions=set(PERMISSIONS.get(user.role, PERMISSIONS["viewer"])),
    )
