"""فحص سريع للثيمات: اكتمال المفاتيح، بناء الأنماط، التباين، والاختصارات."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amdh_leave import colors, config, style                     # noqa: E402


def main() -> int:
    print("الثيمات:", [(key, label, mode) for key, label, mode in config.THEMES])
    problems: list[str] = []
    for key, label, mode in config.THEMES:
        palette = config.PALETTES[key]
        missing = [name for name in style.REQUIRED_KEYS if name not in palette]
        sheet = config.stylesheet(key)
        text_contrast = colors.contrast(palette["text"], palette["surface"])
        muted_contrast = colors.contrast(palette["muted"], palette["surface"])
        accent_contrast = colors.contrast(palette["text"], palette["bg"])
        print(f"\n[{key}] {label} ({mode}) — {len(palette)} مفتاحاً")
        print(f"   ناقص: {missing or 'لا شيء'} | طول الأنماط: {len(sheet)} | $ متبقٍ: {'$' in sheet}")
        print(f"   تباين النص/السطح: {text_contrast:.1f} | الثانوي: {muted_contrast:.1f} | "
              f"النص/الخلفية: {accent_contrast:.1f}")
        print(f"   accent={palette['accent']} on_accent={palette['on_accent']} "
              f"(تباين {colors.contrast(palette['accent'], palette['on_accent']):.1f})")
        print(f"   sel={palette['sel_bg']}/{palette['sel_text']} hover={palette['hover_bg']}")
        if missing:
            problems.append(f"{key}: مفاتيح ناقصة {missing}")
        if "$" in sheet:
            problems.append(f"{key}: علامات قوالب متبقية في الأنماط")
        if text_contrast < 7:
            problems.append(f"{key}: تباين النص منخفض ({text_contrast:.1f})")
        if muted_contrast < 3.0:
            problems.append(f"{key}: تباين النص الثانوي منخفض ({muted_contrast:.1f})")
        if colors.contrast(palette["accent"], palette["on_accent"]) < 3.0:
            problems.append(f"{key}: نص الزر المميز غير مقروء")
        if not sheet.count(":hover"):
            problems.append(f"{key}: لا حالات hover")

    print("\nاختصارات الأسماء القديمة:")
    for alias in ("ocean", "sunset", "زمردي", "داكن", "forest"):
        print(f"   {alias} -> {config.palette(alias)['accent']}")

    print("\nالنتيجة:", "سليم" if not problems else "مشاكل:")
    for item in problems:
        print("   -", item)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
