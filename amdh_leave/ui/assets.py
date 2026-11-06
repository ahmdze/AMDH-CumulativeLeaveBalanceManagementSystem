"""إدارة صور البرنامج (الشعارات وصورة المطوّر) مع بدائل مرسومة داخلياً.

ترتيب البحث عن الصورة:
    1) مجلد بيانات المستخدم:  <data_dir>/assets/<name>
    2) مجلد الحزمة:            amdh_leave/assets/<name>
وإن لم توجد (أو كانت فارغة/شفافة) يُرسم بديل داخلي حتى لا تبدو الواجهة ناقصة.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap

from . import theme

PACKAGE_ASSETS = Path(__file__).resolve().parent.parent / "assets"

LOGO = "logo.png"
DEPARTMENT_LOGO = "department_logo.png"
DEVELOPER_PHOTO = "developer.png"
APP_ICON = "icon.ico"

PLACEHOLDER_MAX_BYTES = 1500  # أي ملف أصغر من هذا يُعدّ فارغاً
_user_assets_dir: Path | None = None
_cache: dict[tuple[str, int, int, bool], QPixmap | None] = {}


def set_user_assets_dir(path: Path | None) -> None:
    """مجلد صور المستخدم (عادةً مجلد البيانات) — يُقدَّم على صور الحزمة."""
    global _user_assets_dir
    _user_assets_dir = Path(path) if path else None
    _cache.clear()


def user_assets_dir() -> Path | None:
    return _user_assets_dir


def asset_path(name: str) -> Path | None:
    """يعيد مسار الصورة الصالحة (غير الفارغة) أو None."""
    candidates: list[Path] = []
    if _user_assets_dir:
        candidates.append(_user_assets_dir / name)
    candidates.append(PACKAGE_ASSETS / name)
    for path in candidates:
        try:
            if path.exists() and path.stat().st_size >= PLACEHOLDER_MAX_BYTES:
                return path
        except OSError:
            continue
    return None


def package_asset_path(name: str) -> Path | None:
    """مسار الصورة من الحزمة فقط (لتثبيت صورة المطوّر مثلاً)."""
    path = PACKAGE_ASSETS / name
    try:
        if path.exists() and path.stat().st_size >= PLACEHOLDER_MAX_BYTES:
            return path
    except OSError:
        pass
    return None


def is_placeholder(name: str) -> bool:
    return asset_path(name) is None


def load_pixmap(
    name: str, width: int = 0, height: int = 0, keep_aspect: bool = True, allow_user: bool = True
) -> QPixmap | None:
    path = asset_path(name) if allow_user else package_asset_path(name)
    if path is None:
        return None
    key = (name, width, height, allow_user)
    if key in _cache:
        return _cache[key]
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        _cache[key] = None
        return None
    if width or height:
        mode = Qt.AspectRatioMode.KeepAspectRatio if keep_aspect else Qt.AspectRatioMode.IgnoreAspectRatio
        pixmap = pixmap.scaled(
            width or height, height or width, mode, Qt.TransformationMode.SmoothTransformation
        )
    _cache[key] = pixmap
    return pixmap


# ---------------------------------------------------------------------------
# بدائل مرسومة (تُستخدم عندما تكون الصور فارغة)
# ---------------------------------------------------------------------------
def _canvas(size: int) -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pixmap, painter


def _rounded(painter: QPainter, color: str, size: int, radius_ratio: float = 0.22) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(theme.resolve(color)))
    radius = size * radius_ratio
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)


def draw_logo(pixmap_size: int = 256) -> QPixmap:
    """شعار بديل: مربع بلون التمييز + أعمدة إحصائية + علامة صح."""
    pixmap, painter = _canvas(pixmap_size)
    _rounded(painter, theme.color("accent"), pixmap_size)

    white = QColor(theme.color("on_accent"))
    bar_w = pixmap_size * 0.12
    gap = pixmap_size * 0.06
    bottom = pixmap_size * 0.74
    heights = (0.22, 0.34, 0.46)
    start_x = pixmap_size * 0.22
    painter.setBrush(white)
    painter.setPen(Qt.PenStyle.NoPen)
    for index, ratio in enumerate(heights):
        height = pixmap_size * ratio
        painter.drawRoundedRect(
            QRectF(start_x + index * (bar_w + gap), bottom - height, bar_w, height), bar_w * 0.3, bar_w * 0.3
        )

    pen = QPen(white, max(2.0, pixmap_size * 0.055))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(
        int(pixmap_size * 0.58), int(pixmap_size * 0.36), int(pixmap_size * 0.68), int(pixmap_size * 0.48)
    )
    painter.drawLine(
        int(pixmap_size * 0.68), int(pixmap_size * 0.48), int(pixmap_size * 0.84), int(pixmap_size * 0.26)
    )
    painter.end()
    return pixmap


def draw_department_logo(pixmap_size: int = 256) -> QPixmap:
    """شعار بديل للدائرة: مبنى + علامة صحة."""
    pixmap, painter = _canvas(pixmap_size)
    _rounded(painter, theme.color("blue"), pixmap_size)
    white = QColor(theme.color("on_solid"))
    painter.setBrush(white)
    painter.setPen(Qt.PenStyle.NoPen)
    body = QRectF(pixmap_size * 0.24, pixmap_size * 0.34, pixmap_size * 0.52, pixmap_size * 0.42)
    painter.drawRoundedRect(body, pixmap_size * 0.03, pixmap_size * 0.03)
    painter.setBrush(QColor(theme.color("blue")))
    for row in range(2):
        for col in range(3):
            painter.drawRect(
                QRectF(
                    pixmap_size * (0.3 + col * 0.15),
                    pixmap_size * (0.42 + row * 0.14),
                    pixmap_size * 0.08,
                    pixmap_size * 0.08,
                )
            )
    pen = QPen(white, max(2.0, pixmap_size * 0.05))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(
        int(pixmap_size * 0.5), int(pixmap_size * 0.18), int(pixmap_size * 0.5), int(pixmap_size * 0.3)
    )
    painter.drawLine(
        int(pixmap_size * 0.44), int(pixmap_size * 0.24), int(pixmap_size * 0.56), int(pixmap_size * 0.24)
    )
    painter.end()
    return pixmap


def draw_developer_photo(width: int = 320, height: int = 400) -> QPixmap:
    """صورة بديلة للمطوّر: صورة رمزية (رأس + كتفان)."""
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(theme.color("card")))
    painter.drawRoundedRect(QRectF(0, 0, width, height), width * 0.06, width * 0.06)

    painter.setBrush(QColor(theme.color("muted")))
    head = width * 0.30
    painter.drawEllipse(QRectF((width - head) / 2, height * 0.16, head, head))
    body = QRectF(width * 0.16, height * 0.52, width * 0.68, height * 0.52)
    painter.drawRoundedRect(body, width * 0.34, width * 0.34)

    painter.setPen(QPen(QColor(theme.color("text"))))
    font = QFont("Segoe UI", max(8, int(width * 0.045)))
    painter.setFont(font)
    painter.drawText(
        QRectF(0, height * 0.92, width, height * 0.08), int(Qt.AlignmentFlag.AlignCenter), "ضع صورتك هنا"
    )
    painter.end()
    return pixmap


# ---------------------------------------------------------------------------
# واجهات جاهزة للاستخدام
# ---------------------------------------------------------------------------
def logo(size: int = 64, fallback: bool = True) -> QPixmap | None:
    pixmap = load_pixmap(LOGO, size, size)
    if pixmap is None and fallback:
        return draw_logo(size)
    return pixmap


def department_logo(size: int = 64, fallback: bool = True) -> QPixmap | None:
    pixmap = load_pixmap(DEPARTMENT_LOGO, size, size)
    if pixmap is None and fallback:
        return draw_department_logo(size)
    return pixmap


def developer_photo(width: int = 320, height: int = 400, fallback: bool = True) -> QPixmap | None:
    """صورة المطوّر ثابتة من الحزمة (لا يستبدلها مجلد بيانات المستخدم)."""
    pixmap = load_pixmap(DEVELOPER_PHOTO, width, height, allow_user=False)
    if pixmap is None and fallback:
        return draw_developer_photo(width, height)
    return pixmap


def app_icon() -> QIcon:
    """أيقونة التطبيق: icon.ico ثم logo.png ثم الشعار المرسوم."""
    icon = QIcon()
    path = asset_path(APP_ICON)
    if path is not None:
        icon.addFile(str(path))
    if icon.isNull():
        path = asset_path(LOGO)
        if path is not None:
            icon.addFile(str(path))
    if icon.isNull():
        for size in (16, 24, 32, 48, 64, 128, 256):
            icon.addPixmap(draw_logo(size))
    return icon


def apply_app_icon(app) -> None:
    """يضبط أيقونة التطبيق والنافذة (شريط المهام)."""
    try:
        icon = app_icon()
        app.setWindowIcon(icon)
    except Exception:  # pragma: no cover - لا نُفشل التشغيل بسبب أيقونة
        pass
