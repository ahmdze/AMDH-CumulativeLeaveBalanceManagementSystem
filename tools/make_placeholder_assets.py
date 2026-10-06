"""توليد ملفات الصور الفارغة (Placeholders) لاستبدالها لاحقاً بشعاراتك.

الاستخدام:
    python tools/make_placeholder_assets.py            # ينشئ الملفات الناقصة فقط
    python tools/make_placeholder_assets.py --force     # يعيد إنشاءها (يمسح ما وضعته!)

الملفات الناتجة (شفافة تماماً = فارغة):
    amdh_leave/assets/logo.png              256×256  شعار البرنامج
    amdh_leave/assets/department_logo.png   256×256  شعار الدائرة/المؤسسة
    amdh_leave/assets/developer.png         320×400  صورة المطوّر
    amdh_leave/assets/icon.ico              أيقونة التطبيق (متعددة المقاسات)

ملاحظة: ما دامت الملفات فارغة (شفافة) يعرض البرنامج شكلاً بديلاً مرسوماً داخلياً،
وبمجرد أن تضع صورتك الخاصة (بحجم أكبر من 1.5KB) سيستخدمها البرنامج تلقائياً.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "amdh_leave" / "assets"

FILES = {
    "logo.png": (256, 256),
    "department_logo.png": (256, 256),
    "developer.png": (320, 400),
}

README = """# ملفات الصور (استبدلها بصورك)

هذه الملفات **فارغة (شفافة)** ويستخدم البرنامج شكلاً بديلاً مرسوماً داخلياً حتى تضع صورك.

| الملف | المقاس المقترح | الاستخدام |
|---|---|---|
| `logo.png` | 256×256 (أو 512×512) | شعار البرنامج: الترويسة، نافذة الدخول، نافذة «حول»، أيقونة التطبيق |
| `department_logo.png` | 256×256 | شعار الدائرة/المؤسسة: نافذة الدخول وترويسة التقارير |
| `developer.png` | 320×400 (نسبة 4:5) | صورة المطوّر في نافذة «حول» |
| `icon.ico` | 16→256 متعدد | أيقونة الملف التنفيذي وشريط المهام (Windows) |

## كيف تستبدلها؟

**الطريقة الأولى (بلا لمس البرنامج):** ضع الملفات في مجلد البيانات:
```
<مجلد البيانات>\\assets\\logo.png
<مجلد البيانات>\\assets\\department_logo.png
<مجلد البيانات>\\assets\\developer.png
<مجلد البيانات>\\assets\\icon.ico
```
مجلد البيانات هو مجلد البرنامج نفسه (أو ما تحدده بـ `--data-dir`)، ويظهر مساره في
«الإعدادات ← البيانات والصيانة».

**الطريقة الثانية:** استبدل الملفات مباشرة في `amdh_leave/assets/`.

## ملاحظات
- الشفافية مدعومة: استخدم PNG بخلفية شفافة لأفضل نتيجة.
- أي ملف أصغر من 1.5KB يُعدّ «فارغاً» ويُستخدم البديل المرسوم بدلاً منه.
- `icon.ico` للأيقونة فقط؛ إن لم تضعها سيُستخدم `logo.png` كأيقونة.
"""


def make_transparent(path: Path, size: tuple[int, int]) -> None:
    from PIL import Image
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    image.save(path, "PNG", optimize=True)


def make_icon(path: Path) -> None:
    from PIL import Image
    sizes = [16, 24, 32, 48, 64, 128, 256]
    base = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    base.save(path, format="ICO", sizes=[(s, s) for s in sizes])


def main() -> int:
    parser = argparse.ArgumentParser(description="توليد صور فارغة قابلة للاستبدال")
    parser.add_argument("--force", action="store_true", help="إعادة الإنشاء حتى لو وُجدت")
    args = parser.parse_args()

    ASSETS.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    skipped: list[str] = []

    for name, size in FILES.items():
        target = ASSETS / name
        if target.exists() and not args.force:
            skipped.append(name)
            continue
        make_transparent(target, size)
        created.append(f"{name} ({size[0]}×{size[1]}, {target.stat().st_size} بايت)")

    icon = ASSETS / "icon.ico"
    if not icon.exists() or args.force:
        make_icon(icon)
        created.append(f"icon.ico ({icon.stat().st_size} بايت)")
    else:
        skipped.append("icon.ico")

    readme = ASSETS / "README.md"
    readme.write_text(README, encoding="utf-8")

    print("أُنشئت:")
    for item in created or ["(لا شيء)"]:
        print("  +", item)
    if skipped:
        print("تُركت كما هي (موجودة):", ", ".join(skipped))
    print(f"المجلد: {ASSETS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
