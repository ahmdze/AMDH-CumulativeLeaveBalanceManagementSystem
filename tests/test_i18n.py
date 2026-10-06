"""اختبارات تعدد اللغات (i18n)."""

from __future__ import annotations

import json

import pytest

from amdh_leave import config, i18n


def teardown_function():
    i18n.set_language(config.DEFAULT_LANGUAGE)
    i18n.load_catalogs()


def test_language_registry():
    codes = [code for code, _label in i18n.available_languages()]
    assert codes == ["ar", "ku", "en"]
    assert i18n.language_info("ar")["dir"] == "rtl"
    assert i18n.language_info("ku")["dir"] == "rtl"
    assert i18n.language_info("en")["dir"] == "ltr"
    assert i18n.is_rtl("ar") is True and i18n.is_rtl("en") is False


def test_arabic_is_the_source_language():
    i18n.set_language("ar")
    for text in ("سجل الإجازات", "حفظ", "الرصيد"):
        assert i18n.tr(text) == text
    assert i18n.trd("اعتيادية") == "اعتيادية"


def test_unknown_language_falls_back_to_arabic():
    assert i18n.set_language("fr") == "ar"
    assert i18n.language() == "ar"


def test_translation_lookup_and_fallback(tmp_path):
    (tmp_path / "en.json").write_text(json.dumps({
        "ui": {"حفظ": "Save"},
        "domain": {"اعتيادية": "Ordinary"},
    }, ensure_ascii=False), encoding="utf-8")
    i18n.load_catalogs(tmp_path)
    i18n.set_language("en")
    assert i18n.tr("حفظ") == "Save"
    assert i18n.tr("نص غير مترجم") == "نص غير مترجم"       # تراجع للعربية
    assert i18n.trd("اعتيادية") == "Ordinary"
    assert i18n.trd("طويلة") == "طويلة"
    assert "نص غير مترجم" in i18n.missing_keys()


def test_trf_keeps_placeholders_safe(tmp_path):
    (tmp_path / "en.json").write_text(json.dumps({
        "ui": {"الرصيد: {v0} يوم": "Balance: {v0} days"},
    }, ensure_ascii=False), encoding="utf-8")
    i18n.load_catalogs(tmp_path)
    i18n.set_language("en")
    assert i18n.trf("الرصيد: {v0} يوم", v0=69) == "Balance: 69 days"
    # متغيّر غير معروف لا يُسقط البرنامج
    assert i18n.trf("{v0} و{v9}", v0="أ") == "أ و{v9}"


def test_trf_format_specs_and_conversion(tmp_path):
    i18n.load_catalogs(tmp_path)
    i18n.set_language("ar")
    assert i18n.trf("المبلغ {v0:,.2f}", v0=1234.5) == "المبلغ 1,234.50"


def test_trd_list_and_tr_list(tmp_path):
    (tmp_path / "en.json").write_text(json.dumps({
        "ui": {"حفظ": "Save"},
        "domain": {"يوم": "Day", "شهر": "Month"},
    }, ensure_ascii=False), encoding="utf-8")
    i18n.load_catalogs(tmp_path)
    i18n.set_language("en")
    assert i18n.trd_list(["يوم", "شهر", ""]) == ["Day", "Month", ""]
    assert i18n.tr_list(["حفظ"]) == ["Save"]


def test_catalog_size_and_dump(tmp_path):
    i18n.load_catalogs()
    ui_count, domain_count = i18n.catalog_size("en")
    assert ui_count >= 0 and domain_count >= 0

    target = tmp_path / "out.json"
    i18n.dump_extracted({"ب", "أ"}, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert list(data["ui"]) == ["أ", "ب"]


@pytest.mark.parametrize("code", ["en", "ku"])
def test_shipped_catalogs_are_valid_and_complete(code):
    """الكتالوجات المُسلَّمة يجب أن تكون صالحة وتغطي معظم نصوص الواجهة."""
    path = i18n.locales_dir() / f"{code}.json"
    if not path.exists():
        pytest.skip(f"لا يوجد كتالوج {code}")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "ui" in data and "domain" in data
    assert all(isinstance(v, str) and v.strip() for v in data["ui"].values()), "ترجمات فارغة"
    assert all(isinstance(v, str) and v.strip() for v in data["domain"].values())

    from tools.wrap_i18n import extract_strings
    strings = extract_strings()
    translated = [s for s in strings if data["ui"].get(s)]
    coverage = len(translated) / len(strings) if strings else 1
    assert coverage > 0.85, f"تغطية {code} منخفضة: {coverage:.0%}"


def test_shipped_catalogs_keep_placeholders():
    """لا يجوز أن تفقد الترجمة أي متغيّر من متغيّرات النص الأصلي."""
    import re
    pattern = re.compile(r"\{[a-zA-Z0-9_]+\}")
    for code in ("en", "ku"):
        path = i18n.locales_dir() / f"{code}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for source, translated in data["ui"].items():
            assert set(pattern.findall(source)) == set(pattern.findall(translated)), \
                f"متغيّرات ناقصة في {code}: {source!r} -> {translated!r}"
