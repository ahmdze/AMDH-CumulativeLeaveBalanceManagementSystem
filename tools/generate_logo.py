"""توليد شعار وأيقونة احترافية لنظام إدارة الرصيد التراكمي للإجازات.

الشعار: دائرة زرقاء متدرجة مع رمز تقويم/إجازة في المنتصف.
الأيقونة: نسخة مصغرة للشعار بصيغة ICO.
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QRectF, QSize, QPointF
from PyQt6.QtGui import (
    QColor, QFont, QIcon, QImage, QPainter,
    QPainterPath, QPen, QPolygonF, QRadialGradient, QPixmap,
)

OUTPUT_DIR = Path(__file__).parent.parent / "amdh_leave" / "assets"


def draw_logo(size: int = 512) -> QPixmap:
    """شعار احترافي: دائرة متدرجة مع رمز تقويم وعلامة صح."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    cx, cy = size / 2, size / 2

    # --- الخلفية الدائرية المتدرجة ---
    grad = QRadialGradient(cx, cy * 0.7, size * 0.6, cx, cy)
    grad.setColorAt(0, QColor("#4A90D9"))
    grad.setColorAt(0.6, QColor("#2B6CB0"))
    grad.setColorAt(1, QColor("#1E3A5F"))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(grad)
    painter.drawEllipse(QRectF(0, 0, size, size))

    # --- إطار داخلي ---
    inner_margin = size * 0.06
    painter.setPen(QPen(QColor("rgba(255,255,255,0.25)"), size * 0.015))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(inner_margin, inner_margin, size - inner_margin * 2, size - inner_margin * 2))

    # --- رمز التقويم ---
    cal_w = size * 0.42
    cal_h = size * 0.38
    cal_x = (size - cal_w) / 2
    cal_y = size * 0.22

    # جسم التقويم
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawRoundedRect(QRectF(cal_x, cal_y, cal_w, cal_h), size * 0.03, size * 0.03)

    # رأس التقويم (الشريط العلوي)
    header_h = cal_h * 0.28
    painter.setBrush(QColor("#1E3A5F"))
    painter.drawRoundedRect(QRectF(cal_x, cal_y, cal_w, header_h), size * 0.03, size * 0.03)

    # ثقوب الدبابيس (الشريط العلوي)
    painter.setBrush(QColor("#FFFFFF"))
    hole_r = size * 0.012
    for offset in (0.25, 0.75):
        hx = cal_x + cal_w * offset
        hy = cal_y + header_h * 0.5
        painter.drawEllipse(QPointF(hx, hy), hole_r, hole_r)

    # خطوط الأيام في التقويم
    painter.setPen(QPen(QColor("#1E3A5F"), size * 0.012))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    body_y = cal_y + header_h + size * 0.02
    line_count = 3
    for i in range(line_count):
        y = body_y + i * (cal_h - header_h - size * 0.02) / (line_count - 1)
        painter.drawLine(QPointF(cal_x + size * 0.03, y),
                         QPointF(cal_x + cal_w - size * 0.03, y))

    # --- علامة الصح الكبيرة ---
    check_size = size * 0.22
    check_x = cal_x + cal_w - check_size * 0.3
    check_y = cal_y + cal_h - check_size * 0.3
    check_path = QPainterPath()
    check_path.moveTo(check_x - check_size * 0.35, check_y)
    check_path.lineTo(check_x - check_size * 0.05, check_y + check_size * 0.3)
    check_path.lineTo(check_x + check_size * 0.4, check_y - check_size * 0.35)
    check_pen = QPen(QColor("#22C55E"), size * 0.025)
    check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    check_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(check_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(check_path)

    painter.end()
    return pixmap


def draw_department_logo(size: int = 512) -> QPixmap:
    """شعار الدائرة: مبنى حكومي مع علم العراق."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    cx, cy = size / 2, size / 2

    # --- الخلفية الدائرية ---
    grad = QRadialGradient(cx, cy * 0.6, size * 0.55, cx, cy)
    grad.setColorAt(0, QColor("#3B82F6"))
    grad.setColorAt(1, QColor("#1E40AF"))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(grad)
    painter.drawEllipse(QRectF(0, 0, size, size))

    # --- إطار داخلي ---
    inner_margin = size * 0.06
    painter.setPen(QPen(QColor("rgba(255,255,255,0.2)"), size * 0.012))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(inner_margin, inner_margin, size - inner_margin * 2, size - inner_margin * 2))

    # --- المبنى ---
    bldg_w = size * 0.45
    bldg_h = size * 0.3
    bldg_x = (size - bldg_w) / 2
    bldg_y = size * 0.35

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawRoundedRect(QRectF(bldg_x, bldg_y, bldg_w, bldg_h), size * 0.02, size * 0.02)

    # السقف (مثلث)
    roof = QPolygonF([
        QPointF(bldg_x - size * 0.03, bldg_y),
        QPointF(bldg_x + bldg_w + size * 0.03, bldg_y),
        QPointF(cx, bldg_y - size * 0.12),
    ])
    painter.setBrush(QColor("#1E40AF"))
    painter.drawConvexPolygon(roof)

    # النوافذ
    painter.setBrush(QColor("#1E40AF"))
    win_w = size * 0.06
    win_h = size * 0.05
    for row in range(2):
        for col in range(4):
            wx = bldg_x + size * 0.04 + col * (win_w + size * 0.03)
            wy = bldg_y + size * 0.04 + row * (win_h + size * 0.04)
            painter.drawRect(QRectF(wx, wy, win_w, win_h))

    # الباب
    door_w = size * 0.08
    door_h = size * 0.1
    painter.setBrush(QColor("#1E40AF"))
    painter.drawRect(QRectF(cx - door_w / 2, bldg_y + bldg_h - door_h, door_w, door_h))

    # --- العلم العراقي (أحمر-أبيض-أسود) ---
    flag_y = size * 0.68
    flag_h = size * 0.04
    flag_w = size * 0.35
    flag_x = (size - flag_w) / 2

    colors = [QColor("#CE1126"), QColor("#FFFFFF"), QColor("#000000")]
    for i, c in enumerate(colors):
        painter.setBrush(c)
        painter.drawRect(QRectF(flag_x, flag_y + i * flag_h, flag_w, flag_h))

    painter.end()
    return pixmap


def save_image(pixmap: QPixmap, path: Path) -> None:
    """حفظ الصورة كـ PNG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(path), "PNG")
    print(f"  ✓ {path.name} → {path}")


def create_icon(logo_pixmap: QPixmap, path: Path) -> None:
    """إنشاء ملف ICO من الشعار."""
    path.parent.mkdir(parents=True, exist_ok=True)
    main_pixmap = logo_pixmap.scaled(
        QSize(256, 256), Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation
    )
    main_pixmap.save(str(path), "ICO", -1)
    print(f"  ✓ {path.name} → {path}")


def main():
    print("توليد الشعارات والأيقونات...")
    app = QApplication(sys.argv)
    
    logo = draw_logo(512)
    save_image(logo, OUTPUT_DIR / "logo.png")

    dept = draw_department_logo(512)
    save_image(dept, OUTPUT_DIR / "department_logo.png")

    create_icon(logo, OUTPUT_DIR / "icon.ico")

    print("تم التوليد بنجاح!")


if __name__ == "__main__":
    main()
