"""أداة تغليف نصوص الواجهة بـ tr()/trf() واستخراجها للترجمة.

الاستخدام:
    python tools/wrap_i18n.py --wrap amdh_leave/ui amdh_leave/services   # تغليف آلي
    python tools/wrap_i18n.py --check amdh_leave                          # كشف النصوص غير المغلّفة
    python tools/wrap_i18n.py --extract                                   # استخراج كل النصوص المغلّفة
    python tools/wrap_i18n.py --coverage                                  # نسبة تغطية الترجمات

مبادئ الأمان:
  * لا يُلمس أي نص لا يحتوي حروفاً عربية.
  * لا تُغلَّف النصوص المخزّنة في قاعدة البيانات (addItem/addItems/currentText/...).
  * لا يُغلَّف ما هو مغلَّف مسبقاً بـ tr/trf.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")

# دوال تُعرض وسيطها الأول كنص
ARG0_FUNCS = {
    "QLabel", "QPushButton", "QCheckBox", "QRadioButton", "QGroupBox", "QAction",
    "title_label", "muted_label", "button", "KPICard", "LabeledValue", "ToolButton",
}
# دوال تُعرض وسيطها الأول (قائمة) كعناوين
ARG0_LIST_FUNCS = {"TablePanel", "setHorizontalHeaderLabels"}
# دوال: (موضع النص) — اسم الدالة -> فهارس الوسائط النصية
PLAIN_FUNCS = {
    "setWindowTitle": (0,), "setText": (0,), "setToolTip": (0,), "setStatusTip": (0,),
    "setPlaceholderText": (0,), "setTabText": (1,), "addTab": (1,), "setTitle": (0,),
    "addRow": (0,), "Issue": (1,), "Alert": (2,), "info": (1, 2), "warn": (1, 2),
    "error": (1, 2), "confirm": (1, 2), "setWindowFilePath": (0,), "QToolTip": (0,),
    # عناوين النوافذ: BaseDialog(parent, ctx, title) وكذلك super().__init__(...)
    "BaseDialog": (2,), "__init__": (2,), "PasswordDialog": (1, 2),
    "getItem": (1, 2), "QInputDialog": (1, 2), "information": (1, 2), "question": (1, 2),
}
# وسائط مسمّاة تُعدّ نصوصاً معروضة
TEXT_KWARGS = {"text", "title", "label", "empty_text", "footer", "tooltip", "placeholder",
               "message", "caption", "subject", "subtitle", "heading", "description",
               "policy_note"}


def quote(text: str) -> str:
    """يغلّف النص بعلامات اقتباس مزدوجة (أسلوب المشروع) مع تهريب آمن للأسطر والرموز."""
    escaped = (text.replace("\\", "\\\\").replace("\n", "\\n")
                   .replace("\r", "\\r").replace("\t", "\\t"))
    if '"' not in escaped:
        return '"' + escaped + '"'
    return repr(text)

# ملفات/مجلدات مستثناة: قيم مخزّنة أو منطق أعمال أو تقارير البيانات
EXCLUDE_PARTS = {"exporters", "locales", "i18n.py", "config.py", "models.py", "db.py"}
# نصوص مجال (تُخزَّن في القاعدة) — لا تُغلَّف أبداً حتى لو ظهرت في موضع عرض
DOMAIN_LITERALS = {
    "اعتيادية", "طويلة", "دراسات", "مرضية", "5 سنوات", "كارت الزمنية", "قبل الوضع",
    "بعد الوضع", "أمومة", "تسوية رصيد", "يوم", "شهر", "سنة", "ذكر", "أنثى",
    "داكن", "فاتح", "الكل", "active", "leave", "retired",
}


class FileRewriter(ast.NodeVisitor):
    def __init__(self, source: str, path: Path) -> None:
        self.source = source
        self.data = source.encode("utf-8")
        # مواقع بدايات الأسطر بالإبايت (col_offset في بايثون إزاحة إبايت لا حرف)
        self.line_starts = [0]
        for index, byte in enumerate(self.data):
            if byte == 0x0A:
                self.line_starts.append(index + 1)
        self.path = path
        self.edits: list[tuple[int, int, bytes]] = []
        self.used_tr = False
        self.used_trf = False
        self.found: list[str] = []

    # -- مساعدات -------------------------------------------------------
    def _byte_pos(self, lineno: int, col_offset: int) -> int:
        if lineno - 1 >= len(self.line_starts):
            return len(self.data)
        return min(len(self.data), self.line_starts[lineno - 1] + col_offset)

    def _segment(self, node: ast.AST) -> str:
        return ast.get_source_segment(self.source, node) or ""

    def _is_wrapped(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name in {"tr", "trf", "trd", "trd_list", "tr_list"}:
                return True
        return False

    @staticmethod
    def _has_arabic(text: str) -> bool:
        return bool(ARABIC_RE.search(text))

    def _literal_text(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def _build(self, node: ast.AST) -> str | None:
        """يبني نص الاستبدال لثابت نصي أو f-string يحتوي عربية."""
        if self._is_wrapped(node):
            return None
        text = self._literal_text(node)
        if text is not None:
            if not self._has_arabic(text) or text in DOMAIN_LITERALS:
                return None
            self.used_tr = True
            return f"tr({quote(text)})"

        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            kwargs: list[str] = []
            has_arabic = False
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    if self._has_arabic(value.value):
                        has_arabic = True
                    parts.append(value.value.replace("{", "{{").replace("}", "}}"))
                elif isinstance(value, ast.FormattedValue):
                    name = f"v{len(kwargs)}"
                    spec = ""
                    if value.format_spec is not None:
                        spec_text = self._format_spec(value.format_spec)
                        if spec_text is None:
                            return None
                        spec = ":" + spec_text
                    conv = "" if value.conversion in (-1, None) else "!" + chr(value.conversion)
                    parts.append("{" + name + conv + spec + "}")
                    kwargs.append(f"{name}={ast.unparse(value.value)}")
                else:
                    return None
            if not has_arabic:
                return None
            template = "".join(parts)
            if template in DOMAIN_LITERALS:
                return None
            self.used_trf = True
            args = ", ".join(kwargs)
            if args:
                return f"trf({quote(template)}, {args})"
            self.used_tr = True
            return f"tr({quote(template)})"
        return None

    def _format_spec(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.JoinedStr):
            values = node.values
            if len(values) == 1:
                return self._format_spec(values[0])
            return None
        if isinstance(node, ast.Constant):
            return str(node.value)
        if isinstance(node, ast.FormattedValue):
            return None
        return None

    def _record(self, node: ast.AST) -> None:
        if isinstance(node, ast.IfExp):        # مثل: "تعديل" if edit else "إضافة"
            self._record(node.body)
            self._record(node.orelse)
            return
        replacement = self._build(node)
        if replacement is None:
            return
        if node.lineno != node.end_lineno:
            return  # نص متعدد الأسطر: يُترك للمراجعة اليدوية
        abs_start = self._byte_pos(node.lineno, node.col_offset)
        abs_end = self._byte_pos(node.end_lineno, node.end_col_offset)
        if abs_start >= abs_end:
            return
        text = self._literal_text(node) or self._segment(node)
        self.found.append(text if isinstance(text, str) else "")
        self.edits.append((abs_start, abs_end, replacement.encode("utf-8")))

    # -- الزيارة -------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name in ARG0_FUNCS:
            for index, arg in enumerate(node.args):
                if index == 0:
                    self._record(arg)
        elif name in ARG0_LIST_FUNCS:
            if node.args and isinstance(node.args[0], (ast.List, ast.Tuple)):
                for element in node.args[0].elts:
                    self._record(element)
        elif name in PLAIN_FUNCS:
            for index in PLAIN_FUNCS[name]:
                if len(node.args) > index:
                    self._record(node.args[index])
        for keyword in node.keywords:
            if keyword.arg in TEXT_KWARGS:
                self._record(keyword.value)
        self.generic_visit(node)


def wrap_file(path: Path, apply: bool) -> dict:
    source = path.read_text(encoding="utf-8-sig")   # يتجاوز BOM إن وُجد
    tree = ast.parse(source)
    rewriter = FileRewriter(source, path)
    rewriter.visit(tree)

    result = {"path": str(path), "replacements": len(rewriter.edits),
              "tr": rewriter.used_tr, "trf": rewriter.used_trf}
    if not apply or not rewriter.edits:
        return result

    updated_bytes = source.encode("utf-8")
    for start, end, replacement in sorted(rewriter.edits, key=lambda item: item[0], reverse=True):
        updated_bytes = updated_bytes[:start] + replacement + updated_bytes[end:]
    updated = updated_bytes.decode("utf-8")

    if rewriter.used_tr or rewriter.used_trf:
        updated = add_import(updated, path, rewriter.used_tr, rewriter.used_trf)
    path.write_text(updated, encoding="utf-8")
    return result


def add_import(source: str, path: Path, need_tr: bool, need_trf: bool) -> str:
    names = []
    if need_tr:
        names.append("tr")
    if need_trf:
        names.append("trf")
    if not names:
        return source
    pkg_root = (ROOT / "amdh_leave").resolve()
    try:
        depth = len(path.resolve().relative_to(pkg_root).parts) - 1
        module = "." * (depth + 1) + "i18n"
    except ValueError:
        module = "amdh_leave.i18n"
    line = f"from {module} import {', '.join(names)}"
    if re.search(r"^from \.+i18n import", source, re.M):
        # تحديث سطر الاستيراد الموجود
        existing = re.search(r"^from \.+i18n import (.+)$", source, re.M)
        current = {part.strip() for part in existing.group(1).split(",")} if existing else set()
        merged = sorted(current | set(names))
        return source[: existing.start()] + f"from {module} import {', '.join(merged)}" + source[existing.end():]
    lines = source.splitlines(keepends=True)
    insert_at = 0
    for index, text in enumerate(lines[:80]):
        if text.startswith(("import ", "from ")) and "__future__" not in text:
            insert_at = index + 1
    lines.insert(insert_at, line + "\n")
    return "".join(lines)


def iter_py_files(targets: list[str]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        path = ROOT / target
        if path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
        elif path.suffix == ".py":
            files.append(path)
    return [f for f in files if not any(part in EXCLUDE_PARTS for part in f.parts)
            and "__pycache__" not in f.parts and not f.name.startswith("_")]


def extract_strings() -> set[str]:
    """يجمع كل النصوص المغلّفة بـ tr/trf في المشروع."""
    found: set[str] = set()
    for path in iter_py_files(["amdh_leave"]):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name in {"tr", "trf", "trd", "trd_list"} and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        found.add(first.value)
    return found


def check_unwrapped() -> list[str]:
    """يكشف نصوصاً عربية في مواضع عرض لم تُغلَّف بعد."""
    problems: list[str] = []
    for path in iter_py_files(["amdh_leave"]):
        source = path.read_text(encoding="utf-8")
        rewriter = FileRewriter(source, path)
        rewriter.visit(ast.parse(source))
        for text in rewriter.found:
            if text:
                problems.append(f"{path.relative_to(ROOT)}: {text[:60]}")
    return problems


def coverage() -> str:
    from amdh_leave import i18n
    i18n.load_catalogs()
    strings = extract_strings()
    lines = [f"نصوص الواجهة المستخرجة: {len(strings)}"]
    for code in i18n.LANGUAGES:
        if code == "ar":
            continue
        ui, domain = i18n.catalog_size(code)
        translated = len([s for s in strings if i18n._state["ui"].get(code, {}).get(s)])  # noqa: SLF001
        percent = (translated / len(strings) * 100) if strings else 0
        lines.append(f"  {code}: مترجم {translated}/{len(strings)} ({percent:.1f}%) | "
                     f"في الملف: {ui} نص واجهة + {domain} قيمة مجال")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="أداة تغليف النصوص للترجمة")
    parser.add_argument("--wrap", nargs="*", help="مسارات للتغليف الآلي")
    parser.add_argument("--check", action="store_true", help="كشف النصوص غير المغلّفة")
    parser.add_argument("--extract", action="store_true", help="استخراج النصوص المغلّفة")
    parser.add_argument("--out", default="amdh_leave/locales/_extracted.json")
    parser.add_argument("--coverage", action="store_true")
    args = parser.parse_args()

    if args.wrap is not None:
        targets = args.wrap or ["amdh_leave/ui"]
        for path in iter_py_files(targets):
            result = wrap_file(path, apply=True)
            if result["replacements"]:
                print(f"{path.relative_to(ROOT)}: {result['replacements']} استبدال")
    if args.check:
        problems = check_unwrapped()
        print("\n".join(problems[:80]) if problems else "لا نصوص غير مغلّفة")
        print(f"المجموع: {len(problems)}")
    if args.extract:
        strings = extract_strings()
        path = ROOT / args.out
        path.parent.mkdir(parents=True, exist_ok=True)
        from amdh_leave import i18n
        i18n.dump_extracted(strings, path)
        print(f"تم استخراج {len(strings)} نصاً إلى {path.relative_to(ROOT)}")
    if args.coverage:
        print(coverage())
    return 0


if __name__ == "__main__":
    sys.exit(main())
