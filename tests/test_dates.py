"""اختبارات عمليات التواريخ (دقة تقويمية، لا تقدير 30/365)."""

from __future__ import annotations

from datetime import date

import pytest

from amdh_leave.services import dates as D


def test_parse_iso_formats():
    assert D.parse_iso("2026-04-30") == date(2026, 4, 30)
    assert D.parse_iso("2026-04-30 12:30:00") == date(2026, 4, 30)
    assert D.parse_iso(date(2025, 1, 2)) == date(2025, 1, 2)
    assert D.parse_iso("30/04/2026") == date(2026, 4, 30)   # صيغة شائعة في Excel
    assert D.parse_iso("2026/04/30") == date(2026, 4, 30)
    assert D.parse_iso("") is None
    assert D.parse_iso(None) is None
    assert D.parse_iso("غير صالح") is None
    assert D.to_iso(None) == ""


def test_add_months_clamps_to_last_day():
    assert D.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert D.add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert D.add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert D.add_months(date(2026, 1, 15), 12) == date(2027, 1, 15)
    assert D.add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert D.add_months(date(2026, 1, 15), -13) == date(2024, 12, 15)


def test_add_years_handles_leap_day():
    assert D.add_years(date(2024, 2, 29), 1) == date(2025, 2, 28)
    assert D.add_years(date(2020, 4, 30), 5) == date(2025, 4, 30)


@pytest.mark.parametrize("start,amount,unit,expected", [
    (date(2026, 1, 1), 10, "يوم", date(2026, 1, 10)),
    (date(2026, 1, 1), 1, "يوم", date(2026, 1, 1)),
    (date(2026, 2, 1), 1, "شهر", date(2026, 2, 28)),
    (date(2026, 1, 15), 1, "شهر", date(2026, 2, 14)),
    (date(2026, 1, 31), 1, "شهر", date(2026, 2, 27)),   # العودة 28-02
    (date(2024, 1, 31), 1, "شهر", date(2024, 2, 28)),
    (date(2020, 4, 30), 5, "سنة", date(2025, 4, 29)),
])
def test_end_date_for(start, amount, unit, expected):
    assert D.end_date_for(start, amount, unit) == expected


def test_days_inclusive_matches_legacy_off_by_one_fix():
    """إجازة 10 أيام من 01-01 تنتهي 10-01 (وكان الإصدار السابق يعرض 11-01)."""
    start = date(2026, 1, 1)
    end = D.end_date_for(start, 10, "يوم")
    assert end == date(2026, 1, 10)
    assert D.days_inclusive(start, end) == 10


def test_working_days_skip_weekend_and_holidays():
    # الجمعة والسبت عطلة افتراضياً: 1-10 كانون الثاني 2026 فيه جمعتان وسبتان
    start, end = date(2026, 1, 1), date(2026, 1, 10)   # 2026-01-02/03 و 09/10 عطلة
    assert D.days_inclusive(start, end) == 10
    assert D.count_working_days(start, end, (4, 5)) == 6
    assert D.count_working_days(start, end, (4, 5), {date(2026, 1, 5)}) == 5
    assert D.count_working_days(start, end, ()) == 10


def test_days_count_modes():
    start, end = date(2026, 1, 1), date(2026, 1, 10)
    assert D.days_count(start, end, "calendar") == 10
    assert D.days_count(start, end, "working", (4, 5)) == 6


def test_service_years_bounds():
    spans = D.service_years_bounds(date(2019, 4, 30), 3)
    assert spans[0] == (date(2019, 4, 30), date(2020, 4, 29))
    assert spans[1] == (date(2020, 4, 30), date(2021, 4, 29))
    assert spans[2][0] == date(2021, 4, 30)
    assert D.days_inclusive(*spans[1]) == 365


def test_month_grid_and_labels():
    grid = D.month_grid(2026, 1, 5)          # الأسبوع يبدأ بالسبت
    assert grid[0][5] == date(2026, 1, 1)    # 2026-01-01 خميس ⇒ العمود السادس
    assert grid[0][0] is None
    assert all(len(week) == 7 for week in grid)
    labels = D.weekday_labels(5)
    assert labels[0] == "السبت"
    assert len(labels) == 7


def test_weekend_and_overlaps():
    assert D.is_weekend(date(2026, 1, 2), (4, 5))       # جمعة
    assert not D.is_weekend(date(2026, 1, 4), (4, 5))   # أحد
    assert D.overlaps(date(2026, 1, 1), date(2026, 1, 5), date(2026, 1, 5), date(2026, 1, 9))
    assert not D.overlaps(date(2026, 1, 1), date(2026, 1, 4), date(2026, 1, 5), date(2026, 1, 9))


def test_month_bounds_and_human_period():
    assert D.month_bounds(date(2024, 2, 10)) == (date(2024, 2, 1), date(2024, 2, 29))
    assert D.human_period(None, None) == "—"
    assert D.human_period(date(2026, 1, 1), date(2026, 1, 1)) == "2026-01-01"
    assert "→" in D.human_period(date(2026, 1, 1), date(2026, 1, 3))
