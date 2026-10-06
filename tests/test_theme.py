"""اختبارات نظام الثيمات: الاكتمال، التباين، الحالات التفاعلية، واللون المخصّص."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from amdh_leave import colors, config, style                     # noqa: E402
from amdh_leave.ui import theme                                   # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def teardown_function():
    theme.set_theme("dark")
    theme.set_accent(None)


# ---------------------------------------------------------------------------
# الألوان وحساباتها
# ---------------------------------------------------------------------------
def test_color_math_helpers():
    assert colors.parse("#2DD4BF") == (45, 212, 191)
    assert colors.parse("#FFF") == (255, 255, 255)
    assert colors.to_hex((45, 212, 191)) == "#2DD4BF"
    assert colors.mix("#000000", "#FFFFFF", 0.5) == "#808080"
    assert colors.lighten("#000000", 1.0) == "#FFFFFF"
    assert colors.darken("#FFFFFF", 1.0) == "#000000"
    assert colors.alpha("#2DD4BF", 0.5).startswith("rgba(45, 212, 191")
    assert "qlineargradient" in colors.gradient("#000000", "#FFFFFF")
    with pytest.raises(ValueError):
        colors.parse("ليس-لوناً")


def test_wcag_contrast_and_readable_text():
    assert colors.contrast("#000000", "#FFFFFF") == pytest.approx(21, abs=0.1)
    assert colors.contrast("#FFFFFF", "#FFFFFF") == pytest.approx(1, abs=0.01)
    assert colors.readable_on("#FFFFFF") == "#0B1220"       # خلفية فاتحة ⇒ نص غامق
    assert colors.readable_on("#111111") == "#FFFFFF"       # خلفية غامقة ⇒ نص فاتح
    boosted = colors.ensure_contrast("#7A7A7A", "#FFFFFF", 4.5)
    assert colors.contrast(boosted, "#FFFFFF") >= 4.5


# ---------------------------------------------------------------------------
# اكتمال اللوحات وجودتها
# ---------------------------------------------------------------------------
def test_five_themes_are_defined():
    keys = [key for key, _label, _mode in config.THEMES]
    assert keys == ["dark", "light", "midnight", "emerald", "warm"]
    labels = [label for _key, label, _mode in config.THEMES]
    assert len(set(labels)) == 5
    assert theme.theme_choices()[0][0] == "dark"


@pytest.mark.parametrize("key", [key for key, _l, _m in config.THEMES])
def test_every_theme_has_all_required_keys(key):
    palette = config.PALETTES[key]
    missing = [name for name in style.REQUIRED_KEYS if name not in palette]
    assert not missing, f"الثيم {key} ناقص: {missing}"


@pytest.mark.parametrize("key", [key for key, _l, _m in config.THEMES])
def test_every_theme_is_readable(key):
    """تباين كافٍ للنص الأساسي والثانوي ونص الأزرار المميزة."""
    palette = config.PALETTES[key]
    assert colors.contrast(palette["text"], palette["surface"]) >= 7.0, "نص أساسي ضعيف"
    assert colors.contrast(palette["muted"], palette["surface"]) >= 3.0, "نص ثانوي ضعيف"
    assert colors.contrast(palette["text"], palette["bg"]) >= 7.0
    for button in ("accent", "blue", "warn", "gold"):
        assert colors.contrast(palette[button], palette[f"on_{button}"]) >= 3.0, \
            f"نص زر {button} غير مقروء في {key}"


@pytest.mark.parametrize("key", [key for key, _l, _m in config.THEMES])
def test_stylesheet_builds_without_placeholders(key):
    sheet = config.stylesheet(key)
    assert "$" not in sheet
    assert len(sheet) > 8000
    palette = config.PALETTES[key]
    for token in (palette["accent"], palette["bg"], palette["text"]):
        assert token in sheet


@pytest.mark.parametrize("key", [key for key, _l, _m in config.THEMES])
def test_stylesheet_covers_interactive_states(key):
    sheet = config.stylesheet(key)
    for selector in (":hover", ":pressed", ":focus", ":checked", ":disabled",
                     ":selected", "QTableView::item:hover", "QPushButton#Nav:hover",
                     "QTabBar::tab:selected", "QGroupBox::title", "QToolTip",
                     "QScrollBar::handle:vertical:hover", "QCalendarWidget"):
        assert selector in sheet, f"الحالة {selector} غير منسّقة في {key}"


def test_theme_modes_and_dark_flag():
    assert config.THEME_MODES["light"] == "light"
    assert config.THEME_MODES["warm"] == "light"
    for key in ("dark", "midnight", "emerald"):
        assert config.THEME_MODES[key] == "dark"
    theme.set_theme("midnight")
    assert theme.is_dark() is True
    theme.set_theme("warm")
    assert theme.is_dark() is False


def test_aliases_and_legacy_names():
    for alias, expected in (("ocean", "midnight"), ("sunset", "warm"),
                            ("forest", "emerald"), ("زمردي", "emerald"),
                            ("داكن", "dark"), ("فاتح", "light"),
                            ("أزرق ليلي", "midnight")):
        assert theme.set_theme(alias) == expected
    theme.set_theme("warm")
    assert theme.set_theme("غير موجود") == "warm"     # قيمة غير معروفة ⇒ يبقى على الحالي


def test_palette_helper_and_resolve():
    theme.set_theme("emerald")
    assert theme.color("accent") == config.PALETTES["emerald"]["accent"]
    assert theme.resolve("#123456") == "#123456"
    assert theme.resolve("rgba(1, 2, 3, 0.5)") == "rgba(1, 2, 3, 0.5)"
    assert theme.resolve("qlineargradient(x)") == "qlineargradient(x)"
    assert theme.resolve("مفتاح غير موجود", "#abcdef") == "#abcdef"
    assert "#000000" not in theme.label_style(theme.color("pos"), 13, bold=True)


def test_balance_color_semantics():
    theme.set_theme("dark")
    assert theme.balance_color(-1) == config.PALETTES["dark"]["neg"]
    assert theme.balance_color(3, low=5) == config.PALETTES["dark"]["gold"]
    assert theme.balance_color(50, low=5) == config.PALETTES["dark"]["pos"]


# ---------------------------------------------------------------------------
# اللون المميز المخصّص
# ---------------------------------------------------------------------------
def test_custom_accent_derives_all_states():
    theme.set_theme("dark")
    base = dict(theme.palette())
    assert theme.set_accent("#7C3AED") == "#7C3AED"
    custom = theme.palette()
    assert custom["accent"] == "#7C3AED"
    assert custom["accent"] != base["accent"]
    assert custom["sel_bg"] == "#7C3AED"
    assert custom["hover_bg"].startswith("rgba(")
    assert custom["accent_hover"] != custom["accent"]
    assert custom["accent_pressed"] != custom["accent_hover"]
    assert "qlineargradient" in custom["accent_grad"]
    assert colors.contrast(custom["accent"], custom["on_accent"]) >= 3.0
    # بقية المفاتيح تبقى من الثيم
    assert custom["bg"] == base["bg"]
    assert custom["card"] == base["card"]
    assert custom["blue"] == base["blue"]


def test_custom_accent_survives_theme_switch_and_resets():
    theme.set_theme("dark")
    theme.set_accent("#0EA5E9")
    theme.set_theme("warm")
    assert theme.palette()["accent"] == "#0EA5E9"
    theme.set_accent(None)
    assert theme.palette()["accent"] == config.PALETTES["warm"]["accent"]
    assert theme.accent_override() is None


def test_custom_accent_rejects_invalid_value():
    theme.set_accent("#123456")
    assert theme.set_accent("ليس-لوناً") is not None
    theme.set_accent(None)


def test_accent_override_keeps_stylesheet_valid():
    theme.set_accent("#DB2777")
    sheet = theme.stylesheet()
    assert "$" not in sheet and "#DB2777" in sheet
    theme.set_accent(None)


# ---------------------------------------------------------------------------
# المعاينة والتطبيق
# ---------------------------------------------------------------------------
def test_swatch_icon_uses_theme_colors(qapp):
    theme.set_accent(None)
    icon = theme.swatch_icon("emerald")
    assert not icon.isNull()
    image = icon.pixmap(46, 18).toImage()
    seen = {image.pixelColor(x, y).name() for x in range(image.width())
            for y in range(image.height())}
    palette = config.PALETTES["emerald"]
    assert palette["accent"].lower() in seen
    assert palette["bg"].lower() in seen


def test_accent_preview_icon_reflects_override(qapp):
    theme.set_accent("#F59E0B")
    image = theme.accent_preview_icon().pixmap(18, 18).toImage()
    assert image.pixelColor(9, 9).name().lower() == "#f59e0b"
    theme.set_accent(None)
    image = theme.accent_preview_icon().pixmap(18, 18).toImage()
    assert image.pixelColor(9, 9).name().lower() == theme.color("accent").lower()


def test_apply_sets_app_stylesheet(qapp):
    theme.set_theme("midnight")
    theme.apply(qapp)
    assert "QPushButton#Accent" in qapp.styleSheet()
    assert config.PALETTES["midnight"]["accent"] in qapp.styleSheet()
    theme.set_theme("dark")
    theme.apply(qapp)


def test_next_theme_cycles():
    theme.set_theme("dark")
    assert theme.next_theme() == "light"
    theme.set_theme("warm")
    assert theme.next_theme() == "dark"
