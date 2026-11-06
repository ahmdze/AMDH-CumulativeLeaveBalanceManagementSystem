"""قالب أنماط Qt (QSS) — مُعاد بناؤه من الصفر بحالات تفاعلية كاملة.

كل لون يُستبدل من لوحة الثيم (انظر ``config.PALETTES``) فلا يوجد أي لون ثابت هنا.
الحالات المغطّاة: hover / pressed / focus / checked / disabled / selected / alternate،
مع تدرّجات للعناصر الأساسية، وحلقة تركيز، وشريط جانبي بتفاعل، وتقويم منسّق.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

TEMPLATE = Template(
    """
/* ===================== الأساس ===================== */
QWidget {
    background-color: $bg;
    color: $text;
    font-family: 'Segoe UI', 'Noto Naskh Arabic', Tahoma, Arial;
    font-size: 10pt;
    selection-background-color: $sel_bg;
    selection-color: $sel_text;
}
QMainWindow, QDialog { background-color: $bg; }
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }
QSplitter::handle { background: $border; }
QSplitter::handle:hover { background: $accent; }

/* ===================== الإطارات ===================== */
QFrame#Card {
    background-color: $card;
    border: 1px solid $border;
    border-radius: 10px;
}
QFrame#Card[hovered="true"] {
    background-color: $card_hover;
    border: 1px solid $accent;
}
QFrame#Elevated {
    background-color: $elevated;
    border: 1px solid $border_strong;
    border-radius: 12px;
}
QFrame#Surface { background-color: $surface; }
QFrame#Header {
    background: $header_grad;
    border-bottom: 1px solid $border_strong;
}
QFrame#Sidebar {
    background: $sidebar_grad;
    border: 1px solid $border;
    border-radius: 10px;
}
QFrame#Separator, QFrame[frameShape="4"], QFrame[frameShape="5"] {
    background-color: $border;
    border: none;
    max-height: 1px;
}

/* ===================== النصوص ===================== */
QLabel { background: transparent; color: $text; }
QLabel#Muted { color: $muted; }
QLabel#Subtle { color: $subtle; }
QLabel#Title { color: $accent; font-weight: bold; }
QLabel#Badge {
    background-color: $accent_soft;
    color: $accent;
    border: 1px solid $accent_line;
    border-radius: 9px;
    padding: 2px 10px;
    font-weight: bold;
}

/* ===================== حقول الإدخال ===================== */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {
    background-color: $surface;
    color: $text;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 6px 9px;
    selection-background-color: $accent;
    selection-color: $on_accent;
}
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QSpinBox:hover,
QDoubleSpinBox:hover, QTextEdit:hover, QPlainTextEdit:hover {
    border: 1px solid $border_strong;
    background-color: $surface_alt;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 2px solid $accent;
    background-color: $elevated;
    padding: 5px 8px;
}
QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {
    padding-left: 27px;
    padding-right: 8px;
}
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled, QSpinBox:disabled,
QDoubleSpinBox:disabled, QTextEdit:disabled {
    background-color: $bg_alt;
    color: $disabled_text;
    border: 1px solid $border;
}
QLineEdit[readOnly="true"] { background-color: $bg_alt; color: $muted; }
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center left;
    width: 22px;
    border: none;
    background: transparent;
}
QComboBox::drop-down:hover { background-color: $accent_soft; border-radius: 6px; }
QComboBox QAbstractItemView {
    background-color: $elevated;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 8px;
    padding: 4px;
    outline: none;
    selection-background-color: $accent;
    selection-color: $on_accent;
}
QAbstractItemView::item { min-height: 24px; padding: 2px 4px; }

/* ===================== حقول الأرقام والتاريخ ===================== */
QSpinBox, QDoubleSpinBox, QDateEdit {
    padding-left: 28px;
    padding-right: 9px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top left;
    width: 24px;
    background-color: $surface_alt;
    border-left: 1px solid $border;
    border-top-left-radius: 7px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom left;
    width: 24px;
    background-color: $surface_alt;
    border-left: 1px solid $border;
    border-bottom-left-radius: 7px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: $accent_soft;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("$assets/chevron_up.png");
    width: 9px;
    height: 6px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("$assets/chevron_down.png");
    width: 9px;
    height: 6px;
}
QDateEdit::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center left;
    width: 24px;
    background-color: $surface_alt;
    border-left: 1px solid $border;
    border-top-left-radius: 7px;
    border-bottom-left-radius: 7px;
}
QDateEdit::drop-down:hover { background-color: $accent_soft; }
QDateEdit::down-arrow {
    image: url("$assets/chevron_down.png");
    width: 10px;
    height: 7px;
}
QComboBox::down-arrow {
    image: url("$assets/chevron_down.png");
    width: 10px;
    height: 7px;
}

/* ===================== الأزرار ===================== */
QPushButton {
    background-color: $surface;
    color: $text;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: $hover_bg;
    border: 1px solid $accent;
    color: $accent;
}
QPushButton:pressed {
    background-color: $accent_soft;
    border: 1px solid $accent_pressed;
    padding-top: 9px;
    padding-bottom: 7px;
}
QPushButton:checked {
    background-color: $accent_soft;
    border: 1px solid $accent;
    color: $accent;
}
QPushButton:disabled {
    background-color: $bg_alt;
    color: $disabled_text;
    border: 1px solid $border;
}
QPushButton:focus { border: 2px solid $focus; }

QPushButton#Accent {
    background: $accent_grad;
    color: $on_accent;
    border: 1px solid $accent_pressed;
}
QPushButton#Accent:hover { background: $accent_hover; border: 1px solid $accent_hover; }
QPushButton#Accent:pressed { background: $accent_pressed; border: 1px solid $accent_pressed; }

QPushButton#Blue {
    background: $blue_grad;
    color: $on_blue;
    border: 1px solid $blue_pressed;
}
QPushButton#Blue:hover { background: $blue_hover; border: 1px solid $blue_hover; }
QPushButton#Blue:pressed { background: $blue_pressed; }

QPushButton#Warn {
    background-color: $warn;
    color: $on_warn;
    border: 1px solid $warn_pressed;
}
QPushButton#Warn:hover { background-color: $warn_hover; border: 1px solid $warn_hover; }
QPushButton#Warn:pressed { background-color: $warn_pressed; }

QPushButton#Gold {
    background-color: $gold;
    color: $on_gold;
    border: 1px solid $gold_pressed;
}
QPushButton#Gold:hover { background-color: $gold_hover; border: 1px solid $gold_hover; }
QPushButton#Gold:pressed { background-color: $gold_pressed; }

QPushButton#Ghost {
    background-color: transparent;
    border: 1px solid $border;
    color: $text;
}
QPushButton#Ghost:hover {
    background-color: $hover_bg;
    border: 1px solid $accent;
    color: $accent;
}
QPushButton#Ghost:pressed { background-color: $accent_soft; }

/* عنصر تنقّل في الشريط الجانبي */
QPushButton#Nav {
    background-color: transparent;
    border: 1px solid transparent;
    border-right: 3px solid transparent;
    border-radius: 8px;
    padding: 8px 12px;
    text-align: center;
    font-weight: normal;
    color: $text;
}
QPushButton#Nav:hover {
    background-color: $hover_bg;
    border-right: 3px solid $accent;
    color: $accent;
    font-weight: bold;
}
QPushButton#Nav:pressed { background-color: $accent_soft; }
QPushButton#Nav:disabled { color: $disabled_text; border-right: 3px solid transparent; }

QToolButton {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 4px 8px;
    color: $text;
}
QToolButton:hover { background-color: $hover_bg; border: 1px solid $accent; color: $accent; }
QToolButton:pressed { background-color: $accent_soft; }

/* ===================== الجداول ===================== */
QTableWidget, QTableView {
    background-color: $surface;
    alternate-background-color: $bg_alt;
    border: 1px solid $border;
    border-radius: 10px;
    gridline-color: $grid;
    selection-background-color: $sel_bg;
    selection-color: $sel_text;
    outline: none;
}
QTableView::item { padding: 4px 6px; border: none; }
QTableView::item:hover { background-color: $hover_bg; color: $text; }
QTableView::item:selected {
    background-color: $sel_bg;
    color: $sel_text;
    border: 1px solid $accent_pressed;
}
QTableView::item:selected:hover { background-color: $accent_hover; }
QTableCornerButton::section { background-color: $surface_alt; border: none; }
QHeaderView { background-color: transparent; }
QHeaderView::section {
    background-color: $surface_alt;
    color: $muted;
    font-weight: bold;
    padding: 8px 6px;
    border: none;
    border-left: 1px solid $border;
    border-bottom: 2px solid $border_strong;
}
QHeaderView::section:hover { background-color: $hover_bg; color: $accent; }
QHeaderView::section:pressed { background-color: $accent_soft; color: $accent; }
QHeaderView::up-arrow, QHeaderView::down-arrow { width: 12px; height: 12px; }

/* ===================== التبويبات ===================== */
QTabWidget::pane {
    border: 1px solid $border;
    border-radius: 10px;
    background-color: $surface;
    top: -1px;
}
QTabBar { background: transparent; qproperty-drawBase: 0; }
QTabBar::tab {
    background-color: $bg_alt;
    color: $muted;
    border: 1px solid $border;
    border-bottom: none;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    padding: 9px 18px;
    margin-left: 3px;
}
QTabBar::tab:hover {
    background-color: $hover_bg;
    color: $accent;
    border: 1px solid $accent;
    border-bottom: none;
}
QTabBar::tab:selected {
    background-color: $accent_grad;
    color: $on_accent;
    border: 1px solid $accent_pressed;
    border-bottom: none;
    font-weight: bold;
}
QTabBar::tab:disabled { color: $disabled_text; background-color: $bg_alt; }

/* ===================== القوائم ===================== */
QMenuBar { background-color: $surface; color: $text; }
QMenuBar::item { padding: 6px 12px; background: transparent; border-radius: 6px; }
QMenuBar::item:selected { background-color: $hover_bg; color: $accent; }
QMenu {
    background-color: $elevated;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 7px 26px 7px 14px;
    border-radius: 6px;
    margin: 1px 2px;
}
QMenu::item:selected { background-color: $accent; color: $on_accent; }
QMenu::item:disabled { color: $disabled_text; }
QMenu::item:checked { font-weight: bold; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }
QMenu::icon { padding-right: 6px; }

/* ===================== أشرطة التمرير ===================== */
QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: $border_strong;
    border-radius: 6px;
    min-height: 32px;
}
QScrollBar::handle:vertical:hover { background: $accent; }
QScrollBar:horizontal {
    background: transparent;
    height: 12px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: $border_strong;
    border-radius: 6px;
    min-width: 32px;
}
QScrollBar::handle:horizontal:hover { background: $accent; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ===================== خانات الاختيار ===================== */
QCheckBox, QRadioButton { background: transparent; color: $text; spacing: 8px; padding: 3px; }
QCheckBox:hover, QRadioButton:hover { color: $accent; }
QCheckBox:disabled, QRadioButton:disabled { color: $disabled_text; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 17px;
    height: 17px;
    border: 1px solid $border_strong;
    background-color: $surface;
}
QCheckBox::indicator { border-radius: 5px; }
QRadioButton::indicator { border-radius: 9px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border: 1px solid $accent; }
QCheckBox::indicator:checked {
    background-color: $accent;
    border: 1px solid $accent_pressed;
}
QRadioButton::indicator:checked {
    background-color: $accent;
    border: 4px solid $surface;
    outline: 2px solid $accent;
}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
    background-color: $bg_alt;
    border: 1px solid $border;
}

/* ===================== المجموعات ===================== */
QGroupBox {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 10px;
    margin-top: 14px;
    padding: 12px 10px 10px 10px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top right;
    right: 14px;
    padding: 2px 8px;
    color: $accent;
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 6px;
}

/* ===================== القوائم والشجر ===================== */
QListWidget, QTreeWidget {
    background-color: $surface;
    color: $text;
    border: 1px solid $border;
    border-radius: 10px;
    outline: none;
}
QListWidget::item, QTreeWidget::item { padding: 6px 8px; border-radius: 6px; margin: 2px 3px; }
QListWidget::item:hover, QTreeWidget::item:hover { background-color: $hover_bg; color: $accent; }
QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: $sel_bg;
    color: $sel_text;
}

/* ===================== التقويم المنبثق ===================== */
QCalendarWidget QWidget { background-color: $surface; color: $text; }
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background: $header_grad;
    border-bottom: 1px solid $border_strong;
}
QCalendarWidget QToolButton {
    background: transparent;
    border: none;
    border-radius: 6px;
    color: $text;
    font-weight: bold;
    padding: 4px 10px;
}
QCalendarWidget QToolButton:hover { background-color: $hover_bg; color: $accent; }
QCalendarWidget QAbstractItemView:enabled {
    background-color: $surface;
    color: $text;
    selection-background-color: $accent;
    selection-color: $on_accent;
    outline: none;
}
QCalendarWidget QAbstractItemView:disabled { color: $disabled_text; }
QCalendarWidget QSpinBox { background-color: $surface; }

/* ===================== متفرقات ===================== */
QToolTip {
    background-color: $tooltip_bg;
    color: $text;
    border: 1px solid $accent;
    border-radius: 6px;
    padding: 5px 8px;
}
QStatusBar { background-color: $surface; color: $muted; border-top: 1px solid $border; }
QStatusBar::item { border: none; }
QProgressBar {
    background-color: $bg_alt;
    border: 1px solid $border;
    border-radius: 8px;
    text-align: center;
    color: $text;
    height: 18px;
}
QProgressBar::chunk { background: $accent_grad; border-radius: 7px; }
QSizeGrip { background: transparent; width: 12px; height: 12px; }
"""
)


def build(palette: dict[str, str]) -> str:
    """يبني نص الأنماط من لوحة ألوان كاملة."""
    values = dict(palette)
    values["assets"] = ASSETS_DIR.as_posix()
    return TEMPLATE.substitute(values)


REQUIRED_KEYS = tuple(sorted(name for name in TEMPLATE.get_identifiers() if name != "assets"))
