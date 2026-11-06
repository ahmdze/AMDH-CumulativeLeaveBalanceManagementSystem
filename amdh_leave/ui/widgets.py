"""مكوّنات واجهة مشتركة: بطاقات، جداول، رسوم بيانية، أدوات مساعدة."""

from __future__ import annotations

import math

from PyQt6.QtCore import QDate, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..services import dates as D
from . import theme


# ---------------------------------------------------------------------------
# أدوات مساعدة
# ---------------------------------------------------------------------------
def card(parent=None, hoverable: bool = False, shadow: bool = False) -> QFrame:
    """إطار بطاقة. ``hoverable`` يفعّل تفاعل المرور، و``shadow`` يضيف ظلاً ناعماً."""
    frame = QFrame(parent)
    frame.setObjectName("Card")
    if hoverable:
        enable_hover(frame)
    if shadow:
        apply_shadow(frame)
    return frame


def enable_hover(widget, property_name: str = "hovered"):
    """يجعل المرور بالماوس يغيّر مظهر الودجت (عبر خاصية ديناميكية في الأنماط)."""
    widget.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    widget.setProperty(property_name, False)

    def set_state(state: bool) -> None:
        if widget.property(property_name) == state:
            return
        widget.setProperty(property_name, state)
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    original_enter = widget.enterEvent
    original_leave = widget.leaveEvent

    def enter(event):
        set_state(True)
        original_enter(event)

    def leave(event):
        set_state(False)
        original_leave(event)

    widget.enterEvent = enter  # type: ignore[method-assign]
    widget.leaveEvent = leave  # type: ignore[method-assign]


def apply_shadow(widget, blur: int = 12, offset: int = 2, spread: int = 0):
    """ظل ناعم حول البطاقات الصغيرة (يعطي عمقاً بصرياً بلا تلطّخ)."""
    from PyQt6.QtWidgets import QGraphicsDropShadowEffect

    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, offset)
    color = QColor(theme.color("shadow"))
    color.setAlpha(max(30, min(85, color.alpha() if color.alpha() else 70)))
    effect.setColor(color)
    widget.setGraphicsEffect(effect)
    return effect


def nav_button(text: str, slot=None, parent=None, tooltip: str = "") -> QPushButton:
    """زر تنقّل في الشريط الجانبي (خلفية شفافة وشريط تمييز عند المرور)."""
    btn = QPushButton(text, parent)
    btn.setObjectName("Nav")
    if slot:
        btn.clicked.connect(slot)
    if tooltip:
        btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setMinimumHeight(34)
    return btn


def title_label(text: str, size: int = 14) -> QLabel:
    label = QLabel(text)
    label.setFont(QFont("Segoe UI", size, QFont.Weight.Bold))
    label.setStyleSheet(theme.label_style("accent", size))
    return label


def muted_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setStyleSheet(theme.label_style("muted"))
    return label


def separator() -> QFrame:
    line = QFrame()
    line.setObjectName("Separator")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    return line


def info(parent, text: str, title: str = "معلومات") -> None:
    QMessageBox.information(parent, title, text)


def warn(parent, text: str, title: str = "تنبيه") -> None:
    QMessageBox.warning(parent, title, text)


def error(parent, text: str, title: str = "خطأ") -> None:
    QMessageBox.critical(parent, title, text)


def confirm(parent, text: str, title: str = "تأكيد") -> bool:
    return (
        QMessageBox.question(
            parent,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def open_path(parent, path, title: str = "فتح الملف") -> bool:
    """يفتح ملفاً/مجلداً بالبرنامج الافتراضي في النظام."""
    from pathlib import Path as _Path

    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices

    target = _Path(path)
    if not target.exists():
        warn(parent, f"الملف غير موجود:\n{target}", title)
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


def search_line(placeholder: str = "") -> QLineEdit:
    """مربع بحث بسيط مع نص توضيحي."""
    line = QLineEdit()
    if placeholder:
        line.setPlaceholderText(placeholder)
    return line


def button(
    text: str, style: str = "Ghost", slot=None, width: int | None = None, parent=None, tooltip: str = ""
) -> QPushButton:
    btn = QPushButton(text, parent)
    btn.setObjectName(style)
    if slot:
        btn.clicked.connect(slot)
    if width:
        btn.setFixedWidth(width)
    if tooltip:
        btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def button_row(*widgets, stretch: bool = True) -> QHBoxLayout:
    row = QHBoxLayout()
    if stretch:
        row.addStretch()
    for widget in widgets:
        if widget is not None:
            row.addWidget(widget)
    return row


# ---------------------------------------------------------------------------
# حقول التواريخ
# ---------------------------------------------------------------------------
def date_edit(value=None) -> QDateEdit:
    edit = QDateEdit()
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("yyyy-MM-dd")
    edit.setDate(QDate.currentDate() if value is None else QDate(value.year, value.month, value.day))
    return edit


def date_of(edit: QDateEdit):
    qdate = edit.date()
    return qdate.toPyDate() if qdate.isValid() else None


def set_date(edit: QDateEdit, value) -> None:
    parsed = D.parse_iso(value)
    if parsed:
        edit.setDate(QDate(parsed.year, parsed.month, parsed.day))


class OptionalDate(QWidget):
    """تاريخ اختياري: مربع تفعيل + منتقي تاريخ."""

    def __init__(self, text: str = "تحديد", value=None, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.check = QCheckBox(text)
        self.edit = date_edit(value)
        self.edit.setEnabled(value is not None)
        self.check.setChecked(value is not None)
        self.check.toggled.connect(self.edit.setEnabled)
        layout.addWidget(self.check)
        layout.addWidget(self.edit)
        layout.addStretch()

    def value(self):
        return date_of(self.edit) if self.check.isChecked() else None

    def set_value(self, value) -> None:
        parsed = D.parse_iso(value)
        self.check.setChecked(parsed is not None)
        self.edit.setEnabled(parsed is not None)
        if parsed:
            set_date(self.edit, parsed)


class LabeledValue(QWidget):
    """عنوان صغير + قيمة كبيرة (للوحات الملخص)."""

    def __init__(self, title: str, value: str = "—", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(0)
        self.title = muted_label(title)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value = QLabel(value)
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        layout.addWidget(self.title)
        layout.addWidget(self.value)

    def set_value(self, value, color_key: str = "text", suffix: str = "") -> None:
        self.value.setText(f"{value}{suffix}")
        self.value.setStyleSheet(theme.label_style(color_key, 13, bold=True))


# ---------------------------------------------------------------------------
# عناصر الجداول
# ---------------------------------------------------------------------------
class NumericItem(QTableWidgetItem):
    """عنصر جدول يقارن رقمياً (لترتيب صحيح بدل الترتيب النصي)."""

    def __init__(self, value, text: str | None = None):
        super().__init__(text if text is not None else str(value))
        try:
            self._value = float(value)
        except (TypeError, ValueError):
            self._value = 0.0

    def __lt__(self, other):
        if isinstance(other, NumericItem):
            return self._value < other._value
        return super().__lt__(other)


def setup_table(table: QTableWidget, sortable: bool = True, multi: bool = False) -> QTableWidget:
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(
        QAbstractItemView.SelectionMode.ExtendedSelection
        if multi
        else QAbstractItemView.SelectionMode.SingleSelection
    )
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setMouseTracking(True)  # لتفعيل تفاعل المرور على الصفوف
    table.setShowGrid(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(False)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
    header.setHighlightSections(False)
    header.setMouseTracking(True)
    table.verticalHeader().setVisible(False)
    table.setSortingEnabled(sortable)
    return table


class TablePanel(QWidget):
    """جدول + رسالة حالة فارغة + شريط إجماليات."""

    def __init__(self, headers: list[str], parent=None, sortable: bool = True):
        super().__init__(parent)
        self.headers = headers
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.table = QTableWidget()
        setup_table(self.table, sortable=sortable)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        layout.addWidget(self.table)
        self.empty_label = muted_label("")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)
        self.footer = muted_label("")
        layout.addWidget(self.footer)

    def set_rows(
        self,
        rows: list[list],
        numeric_columns: set[int] | None = None,
        colors: dict[tuple[int, int], str] | None = None,
        empty_text: str = "لا توجد بيانات للعرض",
        footer: str = "",
        headers: list[str] | None = None,
    ) -> None:
        numeric_columns = numeric_columns or set()
        colors = colors or {}
        # تحديث الـ headers ديناميكياً إذا وُفرت
        if headers is not None:
            self.headers = headers
            self.table.setColumnCount(len(headers))
            self.table.setHorizontalHeaderLabels(headers)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                if c in numeric_columns:
                    item = NumericItem(value, str(value))
                else:
                    item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                color = colors.get((r, c))
                if color:
                    item.setForeground(QColor(color))
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        self.empty_label.setText(empty_text)
        self.empty_label.setVisible(not rows)
        self.footer.setText(footer)
        self.footer.setVisible(bool(footer))

    def selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.table.selectedIndexes()})

    def current_row(self) -> int:
        return self.table.currentRow()


# ---------------------------------------------------------------------------
# بطاقات المؤشرات والرسوم البيانية
# ---------------------------------------------------------------------------
class KPICard(QFrame):
    def __init__(self, title: str, value: str = "—", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setProperty("hovered", False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        self.title = muted_label(title)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value = QLabel(value)
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.value.setStyleSheet(theme.label_style("accent"))
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        self.setMinimumHeight(88)
        enable_hover(self)
        apply_shadow(self, blur=10, offset=2)

    def set_value(self, value, color_key: str | None = None, suffix: str = "") -> None:
        self.value.setText(f"{value}{suffix}")
        self.value.setStyleSheet(theme.label_style(color_key or "accent", 18, bold=True))


class BarChart(QWidget):
    """رسم أعمدة أفقي بسيط (بلا اعتماد على مكتبات خارجية) مع دعم RTL."""

    def __init__(self, parent=None, label_width: float = 0.38, max_rows: int = 12, value_suffix: str = ""):
        super().__init__(parent)
        self._items: list[tuple[str, float]] = []
        self._title = ""
        self._label_width = label_width
        self._max_rows = max_rows
        self._suffix = value_suffix
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, items: list[tuple[str, float]], title: str = "") -> None:
        self._items = [(str(k), float(v)) for k, v in items][: self._max_rows]
        self._title = title
        self.update()

    def paintEvent(self, event):  # noqa: N802 (اسم Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(theme.color("surface")))

        rows = self._items
        top = 8
        if self._title:
            painter.setPen(QPen(QColor(theme.color("accent"))))
            font = QFont("Segoe UI", 10, QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(
                QRectF(8, 2, self.width() - 16, 20),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                self._title,
            )
            top = 28

        if not rows:
            painter.setPen(QPen(QColor(theme.color("muted"))))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "لا توجد بيانات")
            painter.end()
            return

        available = max(40, self.height() - top - 8)
        row_h = max(16.0, min(30.0, available / len(rows)))
        label_w = self.width() * self._label_width
        plot_left = 8.0
        plot_right = self.width() - label_w - 12.0
        plot_width = max(40.0, plot_right - plot_left)
        max_abs = max(abs(v) for _k, v in rows) or 1.0

        painter.setFont(QFont("Segoe UI", 9))
        for i, (label, value) in enumerate(rows):
            y = top + i * row_h
            bar_h = row_h * 0.55
            bar_y = y + (row_h - bar_h) / 2
            text_rect = QRectF(plot_right + 6, y, label_w - 6, row_h)
            painter.setPen(QPen(QColor(theme.color("text"))))
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                label if len(label) <= 34 else label[:32] + "…",
            )
            width = plot_width * abs(value) / max_abs
            color = theme.color("pos") if value >= 0 else theme.color("neg")
            rect = QRectF(plot_right - width, bar_y, width, bar_h)
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(QPen(QColor(theme.color("muted"))))
            value_rect = QRectF(plot_left, y, plot_width, row_h)
            painter.drawText(
                value_rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                f"{value:,.0f}{self._suffix}",
            )
        painter.end()


class PieChart(QWidget):
    """رسم دائري بسيط (بلا اعتماد على مكتبات خارجية) مع دعم RTL."""

    def __init__(self, parent=None, max_slices: int = 8):
        super().__init__(parent)
        self._items: list[tuple[str, float]] = []
        self._title = ""
        self._max_slices = max_slices
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, items: list[tuple[str, float]], title: str = "") -> None:
        self._items = [(str(k), float(v)) for k, v in items if v > 0][: self._max_slices]
        self._title = title
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(theme.color("surface")))

        rows = self._items
        top = 8
        if self._title:
            painter.setPen(QPen(QColor(theme.color("accent"))))
            font = QFont("Segoe UI", 10, QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(
                QRectF(8, 2, self.width() - 16, 20),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                self._title,
            )
            top = 28

        if not rows:
            painter.setPen(QPen(QColor(theme.color("muted"))))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "لا توجد بيانات")
            painter.end()
            return

        total = sum(v for _, v in rows) or 1.0
        colors = [
            "#3b82f6",
            "#ef4444",
            "#10b981",
            "#f59e0b",
            "#8b5cf6",
            "#ec4899",
            "#06b6d4",
            "#f97316",
            "#6366f1",
            "#14b8a6",
        ]

        # منطقة الرسم الدائري
        chart_size = min(self.width() - 160, self.height() - top - 16)
        chart_size = max(80, chart_size)
        cx = (self.width() - 120) / 2
        cy = top + (self.height() - top) / 2
        radius = chart_size / 2

        start_angle = 0
        for i, (_label, value) in enumerate(rows):
            slice_angle = int(360 * value / total * 16)
            painter.setBrush(QColor(colors[i % len(colors)]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPie(
                int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2), start_angle, slice_angle
            )
            start_angle += slice_angle

            # التسمية
            mid_angle = start_angle - slice_angle / 2
            mid_rad = math.radians(mid_angle / 16 - 90)
            label_r = radius * 0.65
            lx = cx + label_r * math.cos(mid_rad)
            ly = cy + label_r * math.sin(mid_rad)
            pct = f"{value / total * 100:.0f}%"
            if value / total > 0.05:
                painter.setPen(QPen(QColor("#ffffff")))
                painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                painter.drawText(int(lx - 20), int(ly + 4), 40, 16, int(Qt.AlignmentFlag.AlignCenter), pct)

        # المفتاح
        legend_x = self.width() - 110
        legend_y = top + 4
        painter.setFont(QFont("Segoe UI", 9))
        for i, (label, _value) in enumerate(rows):
            y = legend_y + i * 20
            painter.setBrush(QColor(colors[i % len(colors)]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(legend_x, y, 12, 12, 2, 2)
            painter.setPen(QPen(QColor(theme.color("text"))))
            short = label if len(label) <= 20 else label[:18] + "…"
            painter.drawText(legend_x + 16, y - 2, 90, 16, int(Qt.AlignmentFlag.AlignRight), short)
        painter.end()


class LineChart(QWidget):
    """رسم خطي بسيط (بلا اعتماد على مكتبات خارجية) مع دعم RTL."""

    def __init__(self, parent=None, max_points: int = 12):
        super().__init__(parent)
        self._items: list[tuple[str, float]] = []
        self._title = ""
        self._max_points = max_points
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, items: list[tuple[str, float]], title: str = "") -> None:
        self._items = [(str(k), float(v)) for k, v in items][: self._max_points]
        self._title = title
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(theme.color("surface")))

        rows = self._items
        top = 8
        if self._title:
            painter.setPen(QPen(QColor(theme.color("accent"))))
            font = QFont("Segoe UI", 10, QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(
                QRectF(8, 2, self.width() - 16, 20),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                self._title,
            )
            top = 28

        if not rows:
            painter.setPen(QPen(QColor(theme.color("muted"))))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "لا توجد بيانات")
            painter.end()
            return

        plot_left = 40.0
        plot_right = self.width() - 16.0
        plot_top = top + 4.0
        plot_bottom = self.height() - 30.0
        plot_height = max(40.0, plot_bottom - plot_top)
        plot_width = max(40.0, plot_right - plot_left)

        max_val = max(v for _, v in rows) or 1.0
        n = len(rows)

        # المحور Y
        painter.setPen(QPen(QColor(theme.color("muted")), 0.5))
        painter.setFont(QFont("Segoe UI", 8))
        for i in range(5):
            y = plot_top + plot_height * i / 4
            val = max_val * (1 - i / 4)
            painter.drawLine(int(plot_left), int(y), int(plot_right), int(y))
            painter.drawText(2, int(y) + 4, 36, 14, int(Qt.AlignmentFlag.AlignRight), f"{val:,.0f}")

        # الخط
        points = []
        for i, (label, value) in enumerate(rows):
            x = plot_left + plot_width * i / max(1, n - 1) if n > 1 else plot_left + plot_width / 2
            y = plot_top + plot_height * (1 - value / max_val)
            points.append((x, y))

            # التسمية X
            if n <= 12:
                painter.setPen(QPen(QColor(theme.color("muted"))))
                painter.save()
                painter.translate(int(x), int(plot_bottom + 14))
                painter.rotate(-45)
                painter.drawText(0, 0, 60, 14, int(Qt.AlignmentFlag.AlignRight), label)
                painter.restore()

        # رسم الخط
        if len(points) > 1:
            painter.setPen(QPen(QColor(theme.color("accent")), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(points[0][0], points[0][1])
            for px, py in points[1:]:
                path.lineTo(px, py)
            painter.drawPath(path)

        # النقاط
        for px, py in points:
            painter.setBrush(QColor(theme.color("accent")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(px - 3), int(py - 3), 6, 6)
        painter.end()
