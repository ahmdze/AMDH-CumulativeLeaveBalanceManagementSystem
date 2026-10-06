"""تعدد اللغات: العربية (المصدر) والكردية والإنجليزية.

طريقة العمل:
  * كل نص واجهة يُكتب بالعربية داخل ``tr()`` — وهي **المصدر** — وتُقرأ الترجمات من
    ``locales/<lang>.json`` بقسمين:
        {"ui": {"نص عربي": "translation", ...},
         "domain": {"اعتيادية": "Ordinary", ...}}
  * قيم قاعدة البيانات (أنواع الإجازات، الوحدات، الجنس، الحالات، الأدوار) **لا تُترجم
    أبداً** — تبقى بالعربية كما هي مخزّنة — ويُستخدم ``trd()`` لعرضها مترجمة فقط.
  * ``trf()`` للجمل التي تحتوي متغيّرات: ``trf("الرصيد {value} يوم", value=69)``.
  * أي نص غير مترجم يظهر بالعربية (لا يتعطّل البرنامج)، ويُسجَّل في ``missing_keys()``.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import config

DEFAULT_LANGUAGE = config.DEFAULT_LANGUAGE
FALLBACK_LANGUAGE = config.DEFAULT_LANGUAGE

# code -> (الاسم بالعربية، الاسم الأصلي، الاتجاه)
LANGUAGES: dict[str, dict[str, str]] = {
    "ar": {"label": "العربية", "native": "العربية", "dir": "rtl"},
    "ku": {"label": "الكردية", "native": "کوردی", "dir": "rtl"},
    "en": {"label": "الإنجليزية", "native": "English", "dir": "ltr"},
}

_state: dict[str, object] = {
    "lang": DEFAULT_LANGUAGE,
    "ui": {},          # lang -> {source: translation}
    "domain": {},      # lang -> {source: translation}
    "missing": set(),  # نصوص لم تُترجم في اللغة الحالية
    "loaded": False,
}


# ---------------------------------------------------------------------------
# تحميل الكتالوجات
# ---------------------------------------------------------------------------
def locales_dir() -> Path:
    return Path(__file__).resolve().parent / "locales"


def load_catalogs(directory: Path | None = None) -> dict[str, list[str]]:
    """يقرأ ملفات الترجمة. يعيد تقريراً بعدد النصوص لكل لغة."""
    directory = Path(directory) if directory else locales_dir()
    report: dict[str, list[str]] = {}
    ui: dict[str, dict[str, str]] = {}
    domain: dict[str, dict[str, str]] = {}
    for code in LANGUAGES:
        if code == FALLBACK_LANGUAGE:
            continue
        path = directory / f"{code}.json"
        keys: list[str] = []
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
            # دعم البنية المتداخلة {"ui": {...}, "domain": {...}} وبنية مسطّحة
            if isinstance(data, dict) and ("ui" in data or "domain" in data):
                ui[code] = {str(k): str(v) for k, v in (data.get("ui") or {}).items()}
                domain[code] = {str(k): str(v) for k, v in (data.get("domain") or {}).items()}
            elif isinstance(data, dict):
                ui[code] = {str(k): str(v) for k, v in data.items()}
                domain[code] = {}
            keys = sorted(set(ui.get(code, {})) | set(domain.get(code, {})))
        else:
            ui[code] = {}
            domain[code] = {}
        report[code] = keys
    _state["ui"] = ui
    _state["domain"] = domain
    _state["loaded"] = True
    return report


def _ensure_loaded() -> None:
    if not _state["loaded"]:
        load_catalogs()


# ---------------------------------------------------------------------------
# اللغة الحالية
# ---------------------------------------------------------------------------
def set_language(code: str) -> str:
    _ensure_loaded()
    if code in LANGUAGES:
        _state["lang"] = code
    else:
        _state["lang"] = DEFAULT_LANGUAGE
    _state["missing"] = set()
    return _state["lang"]


def language() -> str:
    return str(_state["lang"])


def language_info(code: str | None = None) -> dict[str, str]:
    return LANGUAGES.get(code or language(), LANGUAGES[DEFAULT_LANGUAGE])


def language_label(code: str | None = None, native: bool = True) -> str:
    info = language_info(code)
    return info["native"] if native else info["label"]


def direction(code: str | None = None) -> str:
    return language_info(code).get("dir", "rtl")


def is_rtl(code: str | None = None) -> bool:
    return direction(code) == "rtl"


def available_languages() -> list[tuple[str, str]]:
    """[(code, الاسم الأصلي)] بترتيب ثابت يبدأ بالعربية."""
    return [(code, info["native"]) for code, info in LANGUAGES.items()]


# ---------------------------------------------------------------------------
# الترجمة
# ---------------------------------------------------------------------------
class _SafeDict(dict):
    """يترك المتغيّرات غير المعروفة كما هي بدل رفع KeyError."""

    def __missing__(self, key):  # noqa: D105
        return "{" + str(key) + "}"


def tr(text: str) -> str:
    """ترجمة نص واجهة (المصدر عربي). يعيد المصدر إن لم توجد ترجمة."""
    if not text:
        return text
    _ensure_loaded()
    lang = language()
    if lang == FALLBACK_LANGUAGE:
        return text
    catalog = _state["ui"].get(lang, {})  # type: ignore[union-attr]
    translated = catalog.get(text)
    if translated:
        return translated
    _state["missing"].add(text)  # type: ignore[union-attr]
    return text


def trf(template: str, **kwargs) -> str:
    """مثل tr لكن مع تعبئة المتغيّرات بأمان."""
    return tr(template).format_map(_SafeDict(kwargs))


def trd(value) -> str:
    """ترجمة **عرض** قيمة مخزّنة في قاعدة البيانات (النوع، الوحدة، الجنس، الحالة...).

    القيمة المخزّنة تبقى عربية دائماً؛ هذه الدالة تُستخدم للعرض فقط.
    """
    if value is None or value == "":
        return ""
    text = str(value)
    _ensure_loaded()
    lang = language()
    if lang == FALLBACK_LANGUAGE:
        return text
    catalog = _state["domain"].get(lang, {})  # type: ignore[union-attr]
    translated = catalog.get(text)
    if translated:
        return translated
    _state["missing"].add(text)  # type: ignore[union-attr]
    return text


def trd_list(values) -> list[str]:
    return [trd(v) for v in values]


def tr_list(values) -> list[str]:
    return [tr(v) for v in values]


# ---------------------------------------------------------------------------
# أدوات التطوير والاختبار
# ---------------------------------------------------------------------------
def missing_keys() -> set[str]:
    """النصوص التي ظهرت في هذه الجلسة ولم تُترجم للغة الحالية."""
    return set(_state["missing"])  # type: ignore[arg-type]


def catalog_size(code: str) -> tuple[int, int]:
    _ensure_loaded()
    return (len(_state["ui"].get(code, {})), len(_state["domain"].get(code, {})))


def dump_extracted(strings: set[str], path: Path) -> Path:
    """يكتب قائمة النصوص المستخرجة (لتحريرها أو ترجمتها)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ui": {s: "" for s in sorted(strings)}}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
