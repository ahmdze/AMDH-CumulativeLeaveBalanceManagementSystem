"""حالة الثيم: الألوان المتغيّرة، اللون المميز المخصّص، وأيقونات المعاينة."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap

from .. import colors, config, style

_state: dict[str, object] = {"theme": "light", "accent": None}
_accent_cache: dict[str, dict[str, str]] = {}


# ---------------------------------------------------------------------------
# الثيم الحالي
# ---------------------------------------------------------------------------
def set_theme(name: str) -> str:
    """يقبل مفاتيح الثيمات وأسماءها العربية والأسماء البديلة القديمة."""
    resolved = config.THEME_ALIASES.get(name, name)
    if resolved in config.PALETTES:
        _state["theme"] = resolved
    return _state["theme"]


def current() -> str:
    return str(_state["theme"])


def current_label() -> str:
    return config.THEME_LABELS.get(current(), current())


def theme_choices() -> list[tuple[str, str]]:
    """[(المفتاح، الاسم العربي)] لكل الثيمات بترتيب العرض."""
    return [(key, label) for key, label, _mode in config.THEMES]


def next_theme() -> str:
    keys = [key for key, _label, _mode in config.THEMES]
    try:
        index = keys.index(current())
    except ValueError:
        return keys[0]
    return keys[(index + 1) % len(keys)]


def is_dark(name: str | None = None) -> bool:
    key = config.THEME_ALIASES.get(name or current(), name or current())
    return config.THEME_MODES.get(key, "dark") == "dark"


# ---------------------------------------------------------------------------
# اللون المميز المخصّص (تفاعلي: يشتق كل الحالات من لون واحد)
# ---------------------------------------------------------------------------
def set_accent(accent: str | None) -> str | None:
    """يضبط لوناً مميزاً مخصّصاً (أو None للعودة إلى لون الثيم)."""
    if accent is None:
        _state["accent"] = None
        return None
    try:
        colors.parse(accent)
    except ValueError:
        return accent_override()
    _state["accent"] = accent
    return accent


def accent_override() -> str | None:
    value = _state["accent"]
    return str(value) if value else None


def palette(name: str | None = None) -> dict[str, str]:
    """لوحة الألوان الفعّالة (مع تطبيق اللون المميز المخصّص إن وُجد)."""
    key = config.THEME_ALIASES.get(name or current(), name or current())
    if key not in config.PALETTES:
        key = "dark"
    base = config.PALETTES[key]
    accent = accent_override()
    if not accent:
        return base
    if key in _accent_cache and _accent_cache[key].get("accent") == accent:
        return _accent_cache[key]
    palette_with_accent = dict(base)
    palette_with_accent.update(_accent_derivatives(accent, is_dark(key)))
    _accent_cache[key] = palette_with_accent
    return palette_with_accent


def _accent_derivatives(accent: str, dark: bool) -> dict[str, str]:
    hover = colors.lighten(accent, 0.14) if dark else colors.darken(accent, 0.10)
    pressed = colors.darken(accent, 0.18) if dark else colors.darken(accent, 0.24)
    on_accent = colors.readable_on(accent)
    return {
        "accent": accent,
        "accent_hover": hover,
        "accent_pressed": pressed,
        "accent_soft": colors.alpha(accent, 0.16 if dark else 0.11),
        "accent_line": colors.alpha(accent, 0.45),
        "accent_grad": colors.gradient(colors.lighten(accent, 0.05 if dark else 0.10),
                                       colors.darken(accent, 0.12 if dark else 0.06)),
        "on_accent": on_accent,
        "sel_bg": accent,
        "sel_text": on_accent,
        "hover_bg": colors.alpha(accent, 0.12 if dark else 0.08),
        "focus": accent,
    }


# ---------------------------------------------------------------------------
# الألوان والأنماط
# ---------------------------------------------------------------------------
def color(key: str, default: str = "#000000") -> str:
    return resolve(key, default)


def resolve(color_or_key: str, default: str = "#000000") -> str:
    """يقبل مفتاح لوحة (text/neg/...) أو لوناً جاهزاً (#RRGGBB) ويعيد اللون."""
    if not color_or_key:
        return default
    text = str(color_or_key)
    if text.startswith("#") or text.startswith("rgba") or text.startswith("qlinear"):
        return text
    return palette().get(text, default)


def stylesheet(name: str | None = None) -> str:
    return style.build(palette(name))


def apply(app) -> None:
    """يطبّق الثيم الحالي على التطبيق."""
    if app is not None:
        app.setStyleSheet(stylesheet())


def balance_color(balance: int, low: int = 0) -> str:
    """ألوان العرض: الرصيد السالب معلومة نظامية وليس خطأً."""
    if balance < 0:
        return color("neg")
    if low and balance <= low:
        return color("gold")
    return color("pos")


def label_style(key: str = "text", size: int | None = None, bold: bool = False,
                italic: bool = False) -> str:
    parts = [f"color: {resolve(key)}"]
    if size:
        parts.append(f"font-size: {size}px")
    if bold:
        parts.append("font-weight: bold")
    if italic:
        parts.append("font-style: italic")
    return "; ".join(parts) + ";"


# ---------------------------------------------------------------------------
# معاينة الثيم (شرائط ألوان في القوائم)
# ---------------------------------------------------------------------------
def swatch_icon(name: str, width: int = 46, height: int = 18) -> QIcon:
    """أيقونة معاينة صغيرة تُظهر خلفية الثيم وسطحه ولونه المميز."""
    key = config.THEME_ALIASES.get(name, name)
    palette_data = palette(key)
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)

    painter.setBrush(QColor(palette_data.get("bg", "#000000")))
    painter.drawRoundedRect(QRectF(0, 0, width, height), 4, 4)
    painter.setBrush(QColor(palette_data.get("card", "#000000")))
    painter.drawRoundedRect(QRectF(width * 0.10, height * 0.18, width * 0.42, height * 0.64), 3, 3)
    painter.setBrush(QColor(palette_data.get("accent", "#000000")))
    painter.drawRoundedRect(QRectF(width * 0.58, height * 0.18, width * 0.32, height * 0.28), 3, 3)
    painter.setBrush(QColor(palette_data.get("text", "#000000")))
    painter.drawRoundedRect(QRectF(width * 0.58, height * 0.56, width * 0.24, height * 0.24), 3, 3)
    painter.end()
    return QIcon(pixmap)


def accent_preview_icon(accent: str | None = None, size: int = 18) -> QIcon:
    """مربّع بلون اللون المميز الحالي (أو لون مخصّص)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(accent or color("accent")))
    painter.drawRoundedRect(QRectF(0, 0, size, size), 4, 4)
    painter.end()
    return QIcon(pixmap)
