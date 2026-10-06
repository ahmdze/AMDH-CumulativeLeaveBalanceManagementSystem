"""حسابات الألوان: مزج، تفتيح، تعتيم، تدرّجات، شفافية، وتباين WCAG.

لا اعتماديات خارجية. تُستخدم لبناء لوحات الثيمات اشتقاقاً من بضعة ألوان أساسية،
فتبقى الثيمات متناسقة ويقلّ الخطأ اليدوي.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# تحويلات أساسية
# ---------------------------------------------------------------------------
def parse(color: str) -> tuple[int, int, int]:
    """يحوّل #RGB أو #RRGGBB إلى (r, g, b)."""
    text = str(color).strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        raise ValueError(f"لون غير صالح: {color!r}")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(channel))):02X}" for channel in rgb)


def mix(first: str, second: str, ratio: float) -> str:
    """يمزج لونين: ratio=0 يعيد الأول، ratio=1 يعيد الثاني."""
    ratio = max(0.0, min(1.0, float(ratio)))
    a = parse(first)
    b = parse(second)
    return to_hex(tuple(a[i] + (b[i] - a[i]) * ratio for i in range(3)))


def lighten(color: str, amount: float) -> str:
    return mix(color, "#FFFFFF", amount)


def darken(color: str, amount: float) -> str:
    return mix(color, "#000000", amount)


def alpha(color: str, value: float) -> str:
    """لون شبه شفاف بصيغة rgba (تدعمها أنماط Qt)."""
    red, green, blue = parse(color)
    return f"rgba({red}, {green}, {blue}, {max(0.0, min(1.0, value)):.3f})"


def gradient(first: str, second: str, vertical: bool = True) -> str:
    """تدرّج qlineargradient جاهز للاستخدام في أنماط Qt."""
    direction = "x1:0, y1:0, x2:0, y2:1" if vertical else "x1:0, y1:0, x2:1, y2:0"
    return f"qlineargradient({direction}, stop:0 {first}, stop:1 {second})"


# ---------------------------------------------------------------------------
# الإدراك البصري (WCAG)
# ---------------------------------------------------------------------------
def _channel_luminance(value: int) -> float:
    channel = value / 255
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def luminance(color: str) -> float:
    """الإضاءة النسبية (0 أسود، 1 أبيض) حسب WCAG."""
    red, green, blue = parse(color)
    return (0.2126 * _channel_luminance(red)
            + 0.7152 * _channel_luminance(green)
            + 0.0722 * _channel_luminance(blue))


def contrast(first: str, second: str) -> float:
    """نسبة التباين بين لونين (1 = لا تباين، 21 = أقصى تباين)."""
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def readable_on(background: str, light: str = "#FFFFFF", dark: str = "#0B1220") -> str:
    """يعيد اللون الأكثر قراءة (فاتح أو غامق) فوق خلفية معيّنة."""
    return light if contrast(background, light) >= contrast(background, dark) else dark


def ensure_contrast(foreground: str, background: str, target: float = 4.5,
                    light: str = "#FFFFFF", dark: str = "#0B1220") -> str:
    """يعدّل اللون تدريجياً حتى يبلغ التباين المطلوب مع الخلفية (للقراءة المريحة).

    الاتجاه صحيح دائماً: إن كان اللون أفتح من الخلفية نُفتّحه أكثر، وإن كان أغمق نُغمّقه.
    """
    if contrast(foreground, background) >= target:
        return foreground
    towards = light if luminance(foreground) > luminance(background) else dark
    best = foreground
    for step in range(1, 21):
        candidate = mix(foreground, towards, step / 20)
        if contrast(candidate, background) > contrast(best, background):
            best = candidate
        if contrast(candidate, background) >= target:
            return candidate
    return best


def soften(color: str, background: str, minimum: float = 3.0) -> str:
    """لون هادئ (نصوص ثانوية) مع ضمان حد أدنى من التباين."""
    return ensure_contrast(color, background, minimum)
