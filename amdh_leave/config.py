"""الثوابت العامة، المسارات، لوحات الألوان، والضوابط الافتراضية."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .colors import alpha, darken, ensure_contrast, gradient, lighten, mix, readable_on

APP_NAME = "نظام إدارة الرصيد التراكمي للإجازات"
APP_VERSION = "1.0.0"
APP_RELEASE = "2026-10"
APP_ORGANIZATION = "AMDH"
APP_DEVELOPER = "احمد زياد رحيمه"
APP_PHONE = "07723064622"
APP_EMAIL = "ahmdze@gmail.com"

# مفاتيح QSettings تُبقى كما هي للتوافق مع الإصدارات السابقة (لا تُغيَّر)
SETTINGS_ORG = "MyCompany"
SETTINGS_APP = "LeaveSystem"


def settings_app_name() -> str:
    """اسم تطبيق الإعدادات، مع إمكانية العزل عبر AMDH_SETTINGS_SUFFIX (للاختبار وتعدد الملفات)."""
    suffix = os.environ.get("AMDH_SETTINGS_SUFFIX", "")
    return SETTINGS_APP + suffix


DB_FILENAME = "employees_leave.db"

# ----------------------------------------------------------------------------
# الثوابت النظامية
# ----------------------------------------------------------------------------
DAYS_PER_LEAVE = 10  # يوم إجازة واحد لكل 10 أيام دوام
MAX_ANNUAL = 36  # المعدل السنوي (يوم)
UNITS = ("يوم", "شهر", "سنة")
LEGACY_UNIT_DAYS = {"يوم": 1, "شهر": 30, "سنة": 365}  # للتوافق مع البيانات القديمة فقط

# أيام العطلة الأسبوعية (بترقيم بايثون: الاثنين=0 ... الجمعة=4، السبت=5، الأحد=6)
WEEKDAY_NAMES = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
DEFAULT_WEEKEND = (4, 5)  # الجمعة والسبت

# طرق الاحتساب
BASIS_CONTINUOUS = "continuous"  # من تاريخ المباشرة حتى اليوم (السلوك الحالي)
BASIS_ANNUAL = "annual"  # ترصيد سنوي (سنة خدمة) مع ترحيل وصلاحية

COUNT_MODES = ("calendar", "working")
COUNT_MODE_LABELS = {"calendar": "أيام تقويمية", "working": "أيام عمل"}

QUOTA_PERIODS = ("none", "year", "service")
QUOTA_PERIOD_LABELS = {"none": "بلا سقف", "year": "لكل سنة", "service": "طوال الخدمة"}

LEAVE_STATUSES = ("approved", "pending", "rejected")
LEAVE_STATUS_LABELS = {"approved": "معتمدة", "pending": "قيد الانتظار", "rejected": "مرفوضة"}

ROLES = ("admin", "editor", "viewer")
ROLE_LABELS = {"admin": "مدير النظام", "editor": "مدخل بيانات", "viewer": "مطّلع فقط"}


# ----------------------------------------------------------------------------
# المسارات
# ----------------------------------------------------------------------------
def _app_root() -> Path:
    """مجلد البرنامج: مجلد الـ EXE في النسخة المغلّفة، أو جذر المشروع في المصدر."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".amdh_write_test"
        probe.write_bytes(b"1")
        probe.unlink()
        return True
    except OSError:
        return False


def _default_data_dir() -> Path:
    """مجلد البيانات: ``data`` بجانب الـ EXE، ثم ProgramData، ثم AppData."""
    env = os.environ.get("AMDH_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    root = _app_root()
    if getattr(sys, "frozen", False):
        # النسخة المغلّفة: بيانات منفصلة عن ملفات البرنامج حتى لا يمسحها التحديث
        candidate = root / "data"
        if _writable_dir(candidate):
            return candidate
        common = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "AMDH" / "LeaveSystem"
        if _writable_dir(common):
            return common
        base = Path(os.environ.get("APPDATA", Path.home())) / "AMDH"
        return base / "LeaveSystem"
    if _writable_dir(root):
        return root
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home())) / "AMDH"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "AMDH"
    return base / "LeaveSystem"


class Paths:
    """يحلّ كل مسارات البيانات مرة واحدة وبشكل مطلق (لا يعتمد على مجلد التشغيل)."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.app_root = _app_root()
        self.data_dir = Path(data_dir) if data_dir else _default_data_dir()
        self.backups_dir = self.data_dir / "backups"
        self.attachments_dir = self.data_dir / "attachments"
        self.logs_dir = self.data_dir / "logs"
        self.reports_dir = self.data_dir / "reports"

    @property
    def db_path(self) -> Path:
        return self.data_dir / DB_FILENAME

    def ensure(self) -> Paths:
        for d in (self.data_dir, self.backups_dir, self.attachments_dir, self.logs_dir, self.reports_dir):
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        return self

    def legacy_db_candidates(self) -> list[Path]:
        """أماكن محتملة لقاعدة بيانات قديمة نُقلت أو شُغّل البرنامج من مجلد آخر."""
        cands = [Path.cwd() / DB_FILENAME, self.app_root / DB_FILENAME]
        return [c for c in cands if c.exists() and c.resolve() != self.db_path.resolve()]


# ----------------------------------------------------------------------------
# لوحات الألوان
# ----------------------------------------------------------------------------
# الثيمات: 5 لوحات مشتقّة من بضعة ألوان أساسية (حساباتها في colors.py)
# ----------------------------------------------------------------------------
# mode: dark/light | تُكتب الألوان الأساسية فقط، ويُشتق الباقي تلقائياً
# (تدرّجات، حالات hover/pressed/focus، لون نص مقروء، ظلال...) فتبقى اللوحة متناسقة.
_THEME_ANCHORS: dict[str, dict[str, str]] = {
    # 1) داكن — أردوازي هادئ بلمسة فيروزية
    "dark": {
        "label": "داكن",
        "mode": "dark",
        "bg": "#0B1220",
        "surface": "#121C2E",
        "card": "#1A2740",
        "text": "#EEF3F9",
        "muted": "#94A6BE",
        "border": "#26344C",
        "accent": "#2DD4BF",
        "blue": "#60A5FA",
        "warn": "#FB7185",
        "gold": "#FBBF24",
        "pos": "#34D399",
        "neg": "#FB7185",
    },
    # 2) فاتح — نهاري نظيف بأزرق مخضرّ
    "light": {
        "label": "فاتح",
        "mode": "light",
        "bg": "#F3F6FB",
        "surface": "#FFFFFF",
        "card": "#FFFFFF",
        "text": "#121A28",
        "muted": "#5C6C85",
        "border": "#D8E0EC",
        "accent": "#0D9488",
        "blue": "#2563EB",
        "warn": "#DC2626",
        "gold": "#D97706",
        "pos": "#15803D",
        "neg": "#DC2626",
    },
    # 3) أزرق ليلي — أعماق المحيط بسماوي مشرق
    "midnight": {
        "label": "أزرق ليلي",
        "mode": "dark",
        "bg": "#050C1C",
        "surface": "#0C1930",
        "card": "#122545",
        "text": "#E7EFFA",
        "muted": "#8BA5CA",
        "border": "#1D3860",
        "accent": "#38BDF8",
        "blue": "#818CF8",
        "warn": "#FB7185",
        "gold": "#FCD34D",
        "pos": "#2DD4BF",
        "neg": "#FB7185",
    },
    # 4) زمردي — غابة زمردية بنعنع مشرق
    "emerald": {
        "label": "زمردي",
        "mode": "dark",
        "bg": "#061A15",
        "surface": "#0C2A21",
        "card": "#123A2C",
        "text": "#E9F7F1",
        "muted": "#7FB39E",
        "border": "#1B4F3D",
        "accent": "#34D399",
        "blue": "#38BDF8",
        "warn": "#F87171",
        "gold": "#FCD34D",
        "pos": "#6EE7B7",
        "neg": "#F87171",
    },
    # 5) رملي دافئ — نهاري بحبّر برتقالي محروق
    "warm": {
        "label": "رملي دافئ",
        "mode": "light",
        "bg": "#FBF6EF",
        "surface": "#FFFFFF",
        "card": "#FFFCF7",
        "text": "#3E2C18",
        "muted": "#8A7255",
        "border": "#E7D8C1",
        "accent": "#C2410C",
        "blue": "#0E7490",
        "warn": "#DC2626",
        "gold": "#B45309",
        "pos": "#15803D",
        "neg": "#DC2626",
    },
}


def build_palette(anchors: dict[str, str]) -> dict[str, str]:
    """يشتق لوحة ألوان كاملة (40 مفتاحاً) من الألوان الأساسية للثيم."""
    dark = anchors.get("mode", "dark") == "dark"
    bg, surface, card = anchors["bg"], anchors["surface"], anchors["card"]
    text, muted, border = anchors["text"], anchors["muted"], anchors["border"]
    accent, blue = anchors["accent"], anchors["blue"]
    warn, gold = anchors["warn"], anchors["gold"]
    pos, neg = anchors["pos"], anchors["neg"]
    lift = 0.07 if dark else 0.04

    def ramp(color: str) -> dict[str, str]:
        """مشتقّات لون إجراء: hover / pressed / تدرّج / لون نص مقروء فوقه."""
        hover = lighten(color, 0.14) if dark else darken(color, 0.10)
        pressed = darken(color, 0.18) if dark else darken(color, 0.24)
        start = lighten(color, 0.05 if dark else 0.10)
        end = darken(color, 0.12 if dark else 0.06)
        return {"hover": hover, "pressed": pressed, "grad": gradient(start, end), "on": readable_on(color)}

    accent_ramp, blue_ramp = ramp(accent), ramp(blue)
    warn_ramp, gold_ramp = ramp(warn), ramp(gold)
    muted_readable = ensure_contrast(muted, surface, 3.4)

    return {
        # الخلفيات والأسطح
        "bg": bg,
        "bg_alt": lighten(bg, lift * 0.6) if dark else darken(bg, 0.015),
        "surface": surface,
        "surface_alt": mix(surface, card, 0.65),
        "elevated": lighten(card, lift) if dark else "#FFFFFF",
        "card": card,
        "card_hover": lighten(card, lift) if dark else mix(card, accent, 0.07),
        # الخطوط والفصل
        "border": border,
        "border_strong": lighten(border, 0.12) if dark else darken(border, 0.10),
        "grid": mix(border, surface, 0.45),
        # النصوص
        "text": text,
        "muted": muted_readable,
        "subtle": mix(muted_readable, text, 0.45),
        "disabled_text": mix(muted_readable, bg, 0.45),
        # اللون المميز
        "accent": accent,
        "accent_hover": accent_ramp["hover"],
        "accent_pressed": accent_ramp["pressed"],
        "accent_soft": alpha(accent, 0.16 if dark else 0.11),
        "accent_line": alpha(accent, 0.45),
        "accent_grad": accent_ramp["grad"],
        "on_accent": accent_ramp["on"],
        # اللون الثانوي
        "blue": blue,
        "blue_hover": blue_ramp["hover"],
        "blue_pressed": blue_ramp["pressed"],
        "blue_grad": blue_ramp["grad"],
        "on_blue": blue_ramp["on"],
        # التحذير
        "warn": warn,
        "warn_hover": warn_ramp["hover"],
        "warn_pressed": warn_ramp["pressed"],
        "on_warn": warn_ramp["on"],
        # الذهبي
        "gold": gold,
        "gold_hover": gold_ramp["hover"],
        "gold_pressed": gold_ramp["pressed"],
        "on_gold": gold_ramp["on"],
        # الدلالات
        "pos": ensure_contrast(pos, surface, 3.2),
        "neg": ensure_contrast(neg, surface, 3.2),
        "pos_soft": alpha(pos, 0.16),
        "neg_soft": alpha(neg, 0.16),
        # التحديد والتفاعل
        "sel_bg": accent,
        "sel_text": accent_ramp["on"],
        "hover_bg": alpha(accent, 0.12 if dark else 0.08),
        "focus": accent,
        # أسطح خاصة
        "header_grad": gradient(lighten(surface, 0.04) if dark else surface, bg),
        "sidebar_grad": gradient(surface, mix(surface, bg, 0.75 if dark else 0.30)),
        "tooltip_bg": "#1F2937" if dark else lighten(card, 0.06),
        "shadow": alpha("#000000", 0.50) if dark else alpha(text, 0.18),
    }


PALETTES: dict[str, dict[str, str]] = {key: build_palette(anchors) for key, anchors in _THEME_ANCHORS.items()}

# (المفتاح، الاسم العربي، الوضع) — الترتيب هو ترتيب العرض في الواجهة
THEMES: list[tuple[str, str, str]] = [
    (key, anchors["label"], anchors["mode"]) for key, anchors in _THEME_ANCHORS.items()
]
THEME_LABELS = {key: label for key, label, _mode in THEMES}
THEME_MODES = {key: mode for key, _label, mode in THEMES}
# توافق مع القيم المحفوظة سابقاً (العربية أو مفاتيح بديلة)
THEME_ALIASES: dict[str, str] = {label: key for key, label, _mode in THEMES}
THEME_ALIASES.update(
    {
        "midnight-blue": "midnight",
        "ocean": "midnight",
        "deep": "midnight",
        "forest": "emerald",
        "green": "emerald",
        "sand": "warm",
        "sunset": "warm",
        "sun": "warm",
        "dark-blue": "midnight",
        "day": "light",
        "night": "dark",
    }
)


def palette(theme: str = "dark") -> dict[str, str]:
    return PALETTES.get(THEME_ALIASES.get(theme, theme), PALETTES["dark"])


def stylesheet(theme: str = "dark", palette_override: dict[str, str] | None = None) -> str:
    """أنماط Qt جاهزة للثيم المطلوب (مع إمكانية تمرير لوحة معدّلة/مخصّصة)."""
    from . import style

    return style.build(palette_override or palette(theme))


# الضوابط الافتراضية لأنواع الإجازات
# (قابلة للتعديل كاملاً من الواجهة — تُخزَّن في قاعدة البيانات)
# ----------------------------------------------------------------------------
# المفاتيح: النوع -> (يخصم من الرصيد، يُستبعد من أيام الخدمة، طريقة العد،
#                     سقف الأيام، فترة السقف، يتطلب أمراً، نوع خاص، الجنس، الترتيب)
DEFAULT_RULES: list[dict] = [
    {
        "type": "اعتيادية",
        "consumes_balance": 1,
        "service_exclusion": 0,
        "count_mode": "calendar",
        "quota_days": 0,
        "quota_period": "none",
        "requires_order": 0,
        "is_adjustment": 0,
        "gender": "",
        "order_index": 1,
    },
    {
        "type": "طويلة",
        "consumes_balance": 1,
        "service_exclusion": 0,
        "count_mode": "calendar",
        "quota_days": 0,
        "quota_period": "none",
        "requires_order": 1,
        "is_adjustment": 0,
        "gender": "",
        "order_index": 2,
    },
    {
        "type": "دراسات",
        "consumes_balance": 1,
        "service_exclusion": 0,
        "count_mode": "calendar",
        "quota_days": 0,
        "quota_period": "none",
        "requires_order": 1,
        "is_adjustment": 0,
        "gender": "",
        "order_index": 3,
    },
    {
        "type": "مرضية",
        "consumes_balance": 1,
        "service_exclusion": 0,
        "count_mode": "calendar",
        "quota_days": 0,
        "quota_period": "none",
        "requires_order": 1,
        "is_adjustment": 0,
        "gender": "",
        "order_index": 4,
    },
    {
        "type": "5 سنوات",
        "consumes_balance": 0,
        "service_exclusion": 1,
        "count_mode": "calendar",
        "quota_days": 0,
        "quota_period": "none",
        "requires_order": 1,
        "is_adjustment": 0,
        "gender": "",
        "order_index": 5,
    },
    {
        "type": "كارت الزمنية",
        "consumes_balance": 1,
        "service_exclusion": 0,
        "count_mode": "calendar",
        "quota_days": 0,
        "quota_period": "none",
        "requires_order": 0,
        "is_adjustment": 0,
        "gender": "",
        "order_index": 6,
    },
    {
        "type": "قبل الوضع",
        "consumes_balance": 1,
        "service_exclusion": 0,
        "count_mode": "calendar",
        "quota_days": 0,
        "quota_period": "none",
        "requires_order": 1,
        "is_adjustment": 0,
        "gender": "أنثى",
        "order_index": 7,
    },
    {
        "type": "بعد الوضع",
        "consumes_balance": 1,
        "service_exclusion": 0,
        "count_mode": "calendar",
        "quota_days": 0,
        "quota_period": "none",
        "requires_order": 1,
        "is_adjustment": 0,
        "gender": "أنثى",
        "order_index": 8,
    },
    {
        "type": "أمومة",
        "consumes_balance": 0,
        "service_exclusion": 1,
        "count_mode": "calendar",
        "quota_days": 0,
        "quota_period": "none",
        "requires_order": 1,
        "is_adjustment": 0,
        "gender": "أنثى",
        "order_index": 9,
    },
]

# للتوافق مع البيانات القديمة فقط — لم يعد يُنشأ من الواجهة
ADJUSTMENT_TYPE = "تسوية رصيد"

# ----------------------------------------------------------------------------
# إعدادات افتراضية (تُخزَّن في قاعدة البيانات داخل جدول app_meta)
# ----------------------------------------------------------------------------
DEFAULT_POLICY: dict[str, object] = {
    "days_per_leave": DAYS_PER_LEAVE,
    "max_annual": MAX_ANNUAL,
    "enforce_annual_cap": False,  # لا يُفرض سقف المعدل السنوي إلا بتفعيل صريح
    "basis": BASIS_CONTINUOUS,
    "expiry_years": 0,  # 0 = بلا صلاحية
    "carryover_cap": 0,  # 0 = بلا سقف للترحيل
    "allow_negative_balance": True,  # الرصيد السالب مشروع حسب الضوابط الإدارية
    "warn_negative_balance": False,  # تنبيه اختياري فقط، وغير مُفعَّل افتراضياً
    "warn_leaving_soon_days": 5,
    "low_balance_days": 5,
    "first_day_of_week": 5,  # السبت
    "auth_enabled": True,
    "session_timeout_minutes": 0,
    "backup_on_start": True,
    "backup_on_exit": True,
    "backup_keep": 30,
    "backup_before_import": True,
}

# إعدادات الواجهة الافتراضية (QSettings)
DEFAULT_UI_SETTINGS: dict[str, object] = {
    "notifications": True,
    "auto_backup": True,
    "theme": "dark",
    "last_institution": "",
    "window_geometry": None,
    "hidden_columns": "",
}
