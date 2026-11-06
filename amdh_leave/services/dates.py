"""عمليات التواريخ: تحويل آمن، حساب مدى الإجازة، أيام العمل، شبكة التقويم.

كل حسابات الأشهر والسنوات تجري هنا بدقة تقويمية (بلا تقدير 30/365).
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

ISO = "%Y-%m-%d"


def parse_iso(value) -> date | None:
    """تحويل نص ISO (أو كائن تاريخ) إلى date، مع إرجاع None عند الفشل."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text[:19], text[:10]):
        try:
            return datetime.strptime(candidate, ISO).date()
        except ValueError:
            continue
    try:  # صيغ شائعة في ملفات Excel العربية
        for fmt in ("%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    except Exception:  # pragma: no cover - دفاع فقط
        pass
    return None


def to_iso(value) -> str:
    d = parse_iso(value)
    return d.strftime(ISO) if d else ""


def today_iso() -> str:
    return date.today().strftime(ISO)


def add_months(d: date, n: int) -> date:
    """إضافة أشهر مع تقييد اليوم لآخر يوم في الشهر الهدف (31 كانون الثاني + شهر = 28/29 شباط)."""
    total = d.month - 1 + int(n)
    year = d.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def add_years(d: date, n: int) -> date:
    return add_months(d, int(n) * 12)


def end_date_for(start: date, amount: int, unit: str) -> date:
    """تاريخ النهاية الشامل (inclusive) لمدى إجازة بمقدار ووحدة.

    المرجع هو «تاريخ العودة»: إجازة شهر من 15-01 تنتهي 14-02 (والعودة في 15-02).
    وإذا لم يوجد اليوم نفسه في الشهر الهدف (31-01 + شهر) يُقيَّد لآخر يوم فيه،
    فتصبح النهاية 27-02 والعودة في 28-02.
    """
    if unit == "شهر":
        return add_months(start, amount) - timedelta(days=1)
    if unit == "سنة":
        return add_years(start, amount) - timedelta(days=1)
    return start + timedelta(days=amount - 1)


def days_inclusive(start: date | None, end: date | None) -> int:
    if not start or not end:
        return 0
    return max(0, (end - start).days + 1)


def is_weekend(d: date, weekend: tuple[int, ...] | list[int] = ()) -> bool:
    return d.weekday() in set(weekend or ())


def count_working_days(
    start: date | None,
    end: date | None,
    weekend: tuple[int, ...] | list[int] = (),
    holidays: set[date] | None = None,
) -> int:
    """عدد أيام العمل الفعلية داخل المدى (باستثناء العطلة الأسبوعية والعطل الرسمية)."""
    if not start or not end or end < start:
        return 0
    holidays = holidays or set()
    count = 0
    day = start
    while day <= end:
        if not is_weekend(day, weekend) and day not in holidays:
            count += 1
        day += timedelta(days=1)
    return count


def days_count(
    start: date | None,
    end: date | None,
    mode: str,
    weekend: tuple[int, ...] | list[int] = (),
    holidays: set[date] | None = None,
) -> int:
    if mode == "working":
        return count_working_days(start, end, weekend, holidays)
    return days_inclusive(start, end)


def service_years_bounds(start: date, count: int) -> list[tuple[date, date]]:
    """فترات سنوات الخدمة (سنوات ذكرى المباشرة) بدءاً من تاريخ المباشرة."""
    spans: list[tuple[date, date]] = []
    for i in range(max(0, count)):
        lo = add_years(start, i)
        hi = add_years(start, i + 1) - timedelta(days=1)
        spans.append((lo, hi))
    return spans


def month_bounds(d: date) -> tuple[date, date]:
    first = d.replace(day=1)
    last = d.replace(day=calendar.monthrange(d.year, d.month)[1])
    return first, last


def month_grid(year: int, month: int, first_day_of_week: int = 5) -> list[list[date | None]]:
    """شبكة أسابيع الشهر (7 أعمدة)، مع None للخانات خارج الشهر.

    first_day_of_week بترقيم بايثون (السبت = 5).
    """
    first = date(year, month, 1)
    total_days = calendar.monthrange(year, month)[1]
    leading = (first.weekday() - first_day_of_week) % 7
    cells: list[date | None] = [None] * leading
    cells += [date(year, month, day) for day in range(1, total_days + 1)]
    while len(cells) % 7:
        cells.append(None)
    return [cells[i : i + 7] for i in range(0, len(cells), 7)]


def weekday_labels(first_day_of_week: int = 5) -> list[str]:
    from ..config import WEEKDAY_NAMES

    return [WEEKDAY_NAMES[(first_day_of_week + i) % 7] for i in range(7)]


def overlaps(a_start: date | None, a_end: date | None, b_start: date | None, b_end: date | None) -> bool:
    if not a_start or not a_end or not b_start or not b_end:
        return False
    return a_start <= b_end and b_start <= a_end


def human_period(start: date | None, end: date | None) -> str:
    if not start:
        return "—"
    if not end or end == start:
        return start.strftime(ISO)
    return f"{start.strftime(ISO)} → {end.strftime(ISO)}"
