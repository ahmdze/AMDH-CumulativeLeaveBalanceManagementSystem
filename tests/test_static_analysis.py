"""فحص ساكن: أسماء عامة غير معرّفة (يمنع أخطاء NameError مثل نسيان استيراد وحدة).

الخطأ الذي دفع لهذا الفحص: استخدام ``i18n.language()`` في النافذة الرئيسية بلا
``from .. import i18n`` — لا يظهر إلا عند فتح قائمة اللغة.
"""

from __future__ import annotations

import builtins
import symtable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "amdh_leave"
IMPLICIT_GLOBALS = {
    "__name__", "__file__", "__doc__", "__package__", "__spec__", "__loader__",
    "__builtins__", "__debug__", "__annotations__", "__class__", "__dict__",
    "__conditional_annotations__",   # اسم داخلي في بايثون 3.14 (PEP 649)
}


def module_files() -> list[Path]:
    return sorted(path for path in PACKAGE.rglob("*.py") if "__pycache__" not in path.parts)


def undefined_globals(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8-sig")
    table = symtable.symtable(source, str(path), "exec")
    defined = {symbol.get_name() for symbol in table.get_symbols()
               if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()}

    problems: list[str] = []

    def walk(current: symtable.SymbolTable) -> None:
        for symbol in current.get_symbols():
            name = symbol.get_name()
            if not symbol.is_referenced():
                continue
            if (symbol.is_assigned() or symbol.is_imported() or symbol.is_parameter()
                    or symbol.is_free() or symbol.is_declared_global() and name in defined):
                continue
            if symbol.is_local() and not symbol.is_global():
                continue
            if name in defined or name in IMPLICIT_GLOBALS or hasattr(builtins, name):
                continue
            problems.append(f"{name} (في نطاق يبدأ بسطر {current.get_lineno()})")
        for child in current.get_children():
            walk(child)

    walk(table)
    return sorted(set(problems))


@pytest.mark.parametrize("path", module_files(), ids=lambda p: p.name)
def test_no_undefined_global_names(path):
    """كل اسم مستخدَم في الوحدة يجب أن يكون معرّفاً أو مستورداً أو من الأسماء المدمجة."""
    problems = undefined_globals(path)
    assert not problems, (
        f"{path.relative_to(ROOT)} يستخدم أسماء غير معرّفة: {', '.join(problems)}")


def test_the_checker_detects_a_missing_import(tmp_path):
    """التحقق من أن الفحص نفسه يعمل (اختبار على كود مصاب)."""
    broken = tmp_path / "broken.py"
    broken.write_text(
        "def f():\n    return missing_module.thing()\n", encoding="utf-8")
    assert undefined_globals(broken)

    healthy = tmp_path / "healthy.py"
    healthy.write_text(
        "import os\n\ndef f():\n    return os.getcwd()\n", encoding="utf-8")
    assert undefined_globals(healthy) == []


def test_all_modules_import_without_side_effects_on_databases():
    """استيراد كل الوحدات لا يجب أن ينشئ أو يعدّل أي قاعدة بيانات."""
    import importlib
    before = sorted(path.name for path in ROOT.glob("*.db"))
    for path in module_files():
        if path.name == "__init__.py":
            continue
        module_name = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        importlib.import_module(module_name)
    after = sorted(path.name for path in ROOT.glob("*.db"))
    assert before == after
