"""اختبارات الثيم: الألوان المتغيّرة ومنع الخطأ الشائع (لون أسود ثابت)."""

from __future__ import annotations

import pytest

from amdh_leave import config
from amdh_leave.ui import theme


def teardown_function():
    theme.set_theme("dark")


def test_set_theme_accepts_keys_and_legacy_arabic():
    assert theme.set_theme("light") == "light"
    assert theme.set_theme("فاتح") == "light"      # توافق مع الإعدادات القديمة
    assert theme.set_theme("داكن") == "dark"
    assert theme.set_theme("غير معروف") == "dark"  # لا يتغير عند قيمة غير معروفة


def test_palette_differs_between_themes():
    theme.set_theme("dark")
    dark_text = theme.color("text")
    theme.set_theme("light")
    light_text = theme.color("text")
    assert dark_text != light_text
    assert dark_text == config.PALETTES["dark"]["text"]


def test_resolve_accepts_key_or_literal_color():
    theme.set_theme("dark")
    assert theme.resolve("neg") == config.PALETTES["dark"]["neg"]
    assert theme.resolve("#123456") == "#123456"
    assert theme.resolve("") == "#000000"
    assert theme.resolve("مفتاح غير موجود", "#abcdef") == "#abcdef"


def test_label_style_never_returns_black_for_known_content():
    """الخطأ القديم: تمرير لون جاهز إلى دالة تنتظر مفتاحاً ⇒ نص أسود غير مقروء."""
    theme.set_theme("dark")
    style = theme.label_style(theme.color("pos"), 13, bold=True)
    assert "#000000" not in style
    assert config.PALETTES["dark"]["pos"] in style
    assert "font-weight: bold" in style


def test_balance_color_semantics():
    theme.set_theme("dark")
    # الرصيد السالب معلومة نظامية لا خطأ — يُلوَّن لكن لا يُمنع
    assert theme.balance_color(-1) == config.PALETTES["dark"]["neg"]
    assert theme.balance_color(0, low=5) == config.PALETTES["dark"]["gold"]
    assert theme.balance_color(3, low=5) == config.PALETTES["dark"]["gold"]
    assert theme.balance_color(50, low=5) == config.PALETTES["dark"]["pos"]


def test_stylesheet_contains_palette_values_and_no_placeholders():
    for name in ("dark", "light"):
        sheet = config.stylesheet(name)
        assert "$" not in sheet, "بقيت علامات قوالب غير مُستبدلة"
        assert config.PALETTES[name]["accent"] in sheet
        assert "QTableWidget" in sheet and "QPushButton#Accent" in sheet
        assert config.PALETTES[name]["neg"] in sheet


def test_is_dark_flag():
    theme.set_theme("dark")
    assert theme.is_dark() is True
    theme.set_theme("light")
    assert theme.is_dark() is False
    with pytest.raises(KeyError):
        config.PALETTES["غير موجود"]
