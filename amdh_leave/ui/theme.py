"""حالة الثيم والألوان المتغيّرة (يحلّ مشكلة النص الأسود على خلفية داكنة)."""

from __future__ import annotations

from .. import config

_state = {"theme": "dark"}


def set_theme(name: str) -> str:
    """يقبل dark/light وكذلك القيم العربية القديمة (داكن/فاتح) للتوافق مع الإعدادات السابقة."""
    if name in config.PALETTES:
        _state["theme"] = name
    elif name in config.THEME_KEYS:
        _state["theme"] = config.THEME_KEYS[name]
    return _state["theme"]


def current() -> str:
    return _state["theme"]


def palette() -> dict[str, str]:
    return config.palette(_state["theme"])


def color(key: str, default: str = "#000000") -> str:
    return resolve(key, default)


def resolve(color_or_key: str, default: str = "#000000") -> str:
    """يقبل مفتاح لوحة ألوان (text/neg/...) أو لوناً جاهزاً (#RRGGBB) ويعيد اللون.

    هذا يمنع الخطأ الشائع: تمرير لون جاهز إلى دالة تنتظر مفتاحاً فيُستبدل بالأسود.
    """
    if not color_or_key:
        return default
    text = str(color_or_key)
    if text.startswith("#"):
        return text
    return palette().get(text, default)


def stylesheet() -> str:
    return config.stylesheet(_state["theme"])


def is_dark() -> bool:
    return config.THEME_MODES.get(_state["theme"], "dark") == "dark"


def theme_choices() -> list[tuple[str, str]]:
    """[(المفتاح، الاسم العربي)] لكل الثيمات الخمسة."""
    return [(key, label) for key, label, _mode in config.THEMES]


def next_theme() -> str:
    """الثيم التالي في الدورة (لزر تبديل سريع)."""
    keys = [key for key, _label, _mode in config.THEMES]
    try:
        index = keys.index(_state["theme"])
    except ValueError:
        return keys[0]
    return keys[(index + 1) % len(keys)]


def balance_color(balance: int, low: int = 0) -> str:
    """الألوان مخصّصة للعرض فقط: الرصيد السالب معلومة نظامية وليس خطأً."""
    if balance < 0:
        return color("neg")
    if low and balance <= low:
        return color("gold")
    return color("pos")


def label_style(key: str = "text", size: int | None = None, bold: bool = False) -> str:
    parts = [f"color: {resolve(key)}"]
    if size:
        parts.append(f"font-size: {size}px")
    if bold:
        parts.append("font-weight: bold")
    return "; ".join(parts) + ";"
