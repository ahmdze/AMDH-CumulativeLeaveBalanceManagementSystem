"""حالة الثيم والألوان المتغيّرة (يحلّ مشكلة النص الأسود على خلفية داكنة)."""

from __future__ import annotations

from .. import config

_state = {"theme": "dark"}


def set_theme(name: str) -> str:
    if name in config.PALETTES:
        _state["theme"] = name
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
    return _state["theme"] == "dark"


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
