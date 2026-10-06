"""الثوابت العامة، المسارات، لوحات الألوان، والضوابط الافتراضية."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from string import Template

APP_NAME = "نظام إدارة الإجازات التراكمية"
APP_VERSION = "3.0.0"
APP_ORGANIZATION = "AMDH"
APP_DEVELOPER = "تقني طبي - أحمد زياد رحيمه"
APP_PHONE = "07723064622"
APP_EMAIL = "ahmdze@gmail.com"

# مفاتيح QSettings تُبقى كما هي للتوافق مع الإصدارات السابقة (لا تُغيَّر)
SETTINGS_ORG = "MyCompany"
SETTINGS_APP = "LeaveSystem"

DB_FILENAME = "employees_leave.db"

# ----------------------------------------------------------------------------
# الثوابت النظامية
# ----------------------------------------------------------------------------
DAYS_PER_LEAVE = 10        # يوم إجازة واحد لكل 10 أيام دوام
MAX_ANNUAL = 36            # المعدل السنوي (يوم)
UNITS = ("يوم", "شهر", "سنة")
LEGACY_UNIT_DAYS = {"يوم": 1, "شهر": 30, "سنة": 365}   # للتوافق مع البيانات القديمة فقط

# أيام العطلة الأسبوعية (بترقيم بايثون: الاثنين=0 ... الجمعة=4، السبت=5، الأحد=6)
WEEKDAY_NAMES = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
DEFAULT_WEEKEND = (4, 5)   # الجمعة والسبت

# طرق الاحتساب
BASIS_CONTINUOUS = "continuous"   # من تاريخ المباشرة حتى اليوم (السلوك الحالي)
BASIS_ANNUAL = "annual"           # ترصيد سنوي (سنة خدمة) مع ترحيل وصلاحية

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
    """مجلد المشروع (المجلد الذي يحتوي حزمة amdh_leave)."""
    return Path(__file__).resolve().parent.parent


def _default_data_dir() -> Path:
    """مجلد البيانات: بجانب البرنامج، وإن لم يكن قابلاً للكتابة فمجلد بيانات المستخدم."""
    env = os.environ.get("AMDH_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    root = _app_root()
    if os.access(root, os.W_OK):
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

    def ensure(self) -> "Paths":
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
PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#0F172A",
        "surface": "#1E293B",
        "card": "#334155",
        "accent": "#14B8A6",
        "accent_hover": "#0D9488",
        "blue": "#38BDF8",
        "blue_hover": "#0284C7",
        "warn": "#F87171",
        "warn_hover": "#DC2626",
        "gold": "#FBBF24",
        "gold_hover": "#D97706",
        "text": "#F8FAFC",
        "muted": "#94A3B8",
        "border": "#475569",
        "neg": "#F87171",
        "pos": "#4ADE80",
        "on_accent": "#0F172A",
        "on_solid": "#FFFFFF",
        "alt": "#334155",
    },
    "light": {
        "bg": "#F1F5F9",
        "surface": "#FFFFFF",
        "card": "#FFFFFF",
        "accent": "#0D9488",
        "accent_hover": "#0F766E",
        "blue": "#3B82F6",
        "blue_hover": "#2563EB",
        "warn": "#EF4444",
        "warn_hover": "#DC2626",
        "gold": "#F59E0B",
        "gold_hover": "#D97706",
        "text": "#0F172A",
        "muted": "#475569",
        "border": "#CBD5E1",
        "neg": "#DC2626",
        "pos": "#15803D",
        "on_accent": "#FFFFFF",
        "on_solid": "#FFFFFF",
        "alt": "#F8FAFC",
    },
}

THEME_LABELS = {"dark": "داكن", "light": "فاتح"}
THEME_KEYS = {"داكن": "dark", "فاتح": "light"}

_STYLE_TEMPLATE = Template(
    """
QWidget {
    background-color: $bg;
    color: $text;
    font-family: 'Segoe UI', Arial;
    font-size: 10pt;
}
QLabel { background: transparent; color: $text; }
QLabel#Muted { color: $muted; }
QLabel#Title { color: $accent; font-weight: bold; }
QFrame#Card {
    background-color: $card;
    border-radius: 8px;
    border: 1px solid $border;
}
QFrame#Surface { background-color: $surface; }
QFrame#Card QWidget { background: transparent; }
QLineEdit, QComboBox, QDateEdit, QSpinBox, QTextEdit, QPlainTextEdit {
    background-color: $surface;
    color: $text;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 6px;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {
    color: $muted;
    background-color: $bg;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QTextEdit:focus {
    border: 1px solid $accent;
}
QComboBox QAbstractItemView {
    background-color: $surface;
    color: $text;
    border: 1px solid $border;
    selection-background-color: $accent;
    selection-color: $on_accent;
}
QPushButton {
    font-weight: bold;
    padding: 8px 14px;
    border-radius: 6px;
    border: none;
    background-color: $card;
    color: $text;
}
QPushButton#Accent { background-color: $accent; color: $on_accent; }
QPushButton#Accent:hover { background-color: $accent_hover; }
QPushButton#Blue { background-color: $blue; color: $on_solid; }
QPushButton#Blue:hover { background-color: $blue_hover; }
QPushButton#Warn { background-color: $warn; color: $on_solid; }
QPushButton#Warn:hover { background-color: $warn_hover; }
QPushButton#Gold { background-color: $gold; color: $on_accent; }
QPushButton#Gold:hover { background-color: $gold_hover; }
QPushButton#Ghost { background-color: transparent; border: 1px solid $border; color: $text; }
QPushButton#Ghost:hover { background-color: $surface; }
QPushButton:disabled { background-color: $surface; color: $muted; }
QTableWidget, QTableView {
    background-color: $surface;
    alternate-background-color: $alt;
    border: 1px solid $border;
    gridline-color: $border;
    selection-background-color: $accent;
    selection-color: $on_accent;
}
QHeaderView::section {
    background-color: $surface;
    color: $muted;
    font-weight: bold;
    padding: 8px;
    border: none;
    border-right: 1px solid $border;
    border-bottom: 2px solid $border;
}
QScrollBar:vertical { background: $surface; width: 12px; }
QScrollBar::handle:vertical { background: $border; border-radius: 6px; }
QScrollBar:horizontal { background: $surface; height: 12px; }
QScrollBar::handle:horizontal { background: $border; border-radius: 6px; }
QMenu { background-color: $surface; color: $text; border: 1px solid $border; border-radius: 6px; }
QMenu::item { padding: 6px 24px; }
QMenu::item:selected { background-color: $accent; color: $on_accent; }
QTabWidget::pane { border: 1px solid $border; border-radius: 6px; }
QTabBar::tab {
    background: $surface; color: $muted; padding: 8px 16px;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}
QTabBar::tab:selected { background: $accent; color: $on_accent; }
QCheckBox, QRadioButton { background: transparent; color: $text; }
QGroupBox {
    border: 1px solid $border; border-radius: 6px; margin-top: 12px; padding-top: 8px;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: $accent; }
QToolTip { background-color: $card; color: $text; border: 1px solid $border; }
QStatusBar { background: $surface; color: $muted; }
QListWidget, QTreeWidget { background-color: $surface; color: $text; border: 1px solid $border; }
"""
)


def palette(theme: str = "dark") -> dict[str, str]:
    return PALETTES.get(theme, PALETTES["dark"])


def stylesheet(theme: str = "dark") -> str:
    return _STYLE_TEMPLATE.substitute(palette(theme))


# ----------------------------------------------------------------------------
# الضوابط الافتراضية لأنواع الإجازات
# (قابلة للتعديل كاملاً من الواجهة — تُخزَّن في قاعدة البيانات)
# ----------------------------------------------------------------------------
# المفاتيح: النوع -> (يخصم من الرصيد، يُستبعد من أيام الخدمة، طريقة العد،
#                     سقف الأيام، فترة السقف، يتطلب أمراً، نوع خاص، الجنس، الترتيب)
DEFAULT_RULES: list[dict] = [
    {"type": "اعتيادية",   "consumes_balance": 1, "service_exclusion": 0, "count_mode": "calendar",
     "quota_days": 0, "quota_period": "none", "requires_order": 0, "is_adjustment": 0,
     "gender": "", "order_index": 1},
    {"type": "طويلة",      "consumes_balance": 1, "service_exclusion": 0, "count_mode": "calendar",
     "quota_days": 0, "quota_period": "none", "requires_order": 1, "is_adjustment": 0,
     "gender": "", "order_index": 2},
    {"type": "دراسات",     "consumes_balance": 1, "service_exclusion": 0, "count_mode": "calendar",
     "quota_days": 0, "quota_period": "none", "requires_order": 1, "is_adjustment": 0,
     "gender": "", "order_index": 3},
    {"type": "مرضية",      "consumes_balance": 1, "service_exclusion": 0, "count_mode": "calendar",
     "quota_days": 0, "quota_period": "none", "requires_order": 1, "is_adjustment": 0,
     "gender": "", "order_index": 4},
    {"type": "5 سنوات",    "consumes_balance": 0, "service_exclusion": 1, "count_mode": "calendar",
     "quota_days": 0, "quota_period": "none", "requires_order": 1, "is_adjustment": 0,
     "gender": "", "order_index": 5},
    {"type": "كارت الزمنية", "consumes_balance": 1, "service_exclusion": 0, "count_mode": "calendar",
     "quota_days": 0, "quota_period": "none", "requires_order": 0, "is_adjustment": 0,
     "gender": "", "order_index": 6},
    {"type": "قبل الوضع",  "consumes_balance": 1, "service_exclusion": 0, "count_mode": "calendar",
     "quota_days": 0, "quota_period": "none", "requires_order": 1, "is_adjustment": 0,
     "gender": "أنثى", "order_index": 7},
    {"type": "بعد الوضع",  "consumes_balance": 1, "service_exclusion": 0, "count_mode": "calendar",
     "quota_days": 0, "quota_period": "none", "requires_order": 1, "is_adjustment": 0,
     "gender": "أنثى", "order_index": 8},
    {"type": "أمومة",      "consumes_balance": 1, "service_exclusion": 0, "count_mode": "calendar",
     "quota_days": 0, "quota_period": "none", "requires_order": 1, "is_adjustment": 0,
     "gender": "أنثى", "order_index": 9},
    {"type": "تسوية رصيد", "consumes_balance": 1, "service_exclusion": 0, "count_mode": "calendar",
     "quota_days": 0, "quota_period": "none", "requires_order": 0, "is_adjustment": 1,
     "gender": "", "order_index": 99},
]

ADJUSTMENT_TYPE = "تسوية رصيد"

# ----------------------------------------------------------------------------
# إعدادات افتراضية (تُخزَّن في قاعدة البيانات داخل جدول app_meta)
# ----------------------------------------------------------------------------
DEFAULT_POLICY: dict[str, object] = {
    "days_per_leave": DAYS_PER_LEAVE,
    "max_annual": MAX_ANNUAL,
    "enforce_annual_cap": False,   # لا يُفرض سقف المعدل السنوي إلا بتفعيل صريح
    "basis": BASIS_CONTINUOUS,
    "expiry_years": 0,        # 0 = بلا صلاحية
    "carryover_cap": 0,       # 0 = بلا سقف للترحيل
    "allow_negative_balance": True,   # الرصيد السالب مشروع حسب الضوابط الإدارية
    "warn_negative_balance": False,   # تنبيه اختياري فقط، وغير مُفعَّل افتراضياً
    "warn_leaving_soon_days": 5,
    "low_balance_days": 5,
    "first_day_of_week": 5,   # السبت
    "auth_enabled": False,
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
