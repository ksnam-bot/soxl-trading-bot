"""NYSE trading-day calendar and Excel-style WORKDAY helpers.

We don't rely on the finite holiday list embedded in the original spreadsheets
(it only covers the years the author manually typed in). Instead we compute
NYSE holidays algorithmically so the bot keeps working indefinitely.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """weekday: Monday=0..Sunday=6. n=1 -> first occurrence, n=-1 -> last occurrence."""
    if n > 0:
        d = dt.date(year, month, 1)
        offset = (weekday - d.weekday()) % 7
        d += dt.timedelta(days=offset + 7 * (n - 1))
        return d
    # last occurrence in month
    if month == 12:
        d = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
    else:
        d = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    offset = (d.weekday() - weekday) % 7
    return d - dt.timedelta(days=offset)


def _easter_sunday(year: int) -> dt.date:
    """Anonymous Gregorian algorithm (Meeus/Jones/Butcher)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def _observed(d: dt.date) -> dt.date:
    """NYSE weekend-observance rule for fixed-date holidays."""
    if d.weekday() == 5:  # Saturday -> observed Friday before
        return d - dt.timedelta(days=1)
    if d.weekday() == 6:  # Sunday -> observed Monday after
        return d + dt.timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def nyse_holidays(year: int) -> frozenset[dt.date]:
    holidays = set()
    holidays.add(_observed(dt.date(year, 1, 1)))  # New Year's Day
    holidays.add(_nth_weekday(year, 1, 0, 3))  # MLK Day: 3rd Monday of Jan
    holidays.add(_nth_weekday(year, 2, 0, 3))  # Washington's Birthday: 3rd Monday of Feb
    holidays.add(_easter_sunday(year) - dt.timedelta(days=2))  # Good Friday
    holidays.add(_nth_weekday(year, 5, 0, -1))  # Memorial Day: last Monday of May
    if year >= 2022:
        holidays.add(_observed(dt.date(year, 6, 19)))  # Juneteenth
    holidays.add(_observed(dt.date(year, 7, 4)))  # Independence Day
    holidays.add(_nth_weekday(year, 9, 0, 1))  # Labor Day: 1st Monday of Sep
    holidays.add(_nth_weekday(year, 11, 3, 4))  # Thanksgiving: 4th Thursday of Nov
    holidays.add(_observed(dt.date(year, 12, 25)))  # Christmas
    return frozenset(holidays)


def is_trading_day(d: dt.date) -> bool:
    if d.weekday() >= 5:
        return False
    return d not in nyse_holidays(d.year)


def workday(start: dt.date, offset: int) -> dt.date:
    """Excel WORKDAY(start, offset) equivalent, NYSE calendar. offset may be 0."""
    d = start
    step = 1 if offset >= 0 else -1
    remaining = abs(offset)
    while remaining > 0:
        d += dt.timedelta(days=step)
        if is_trading_day(d):
            remaining -= 1
    return d


def next_trading_day(d: dt.date) -> dt.date:
    return workday(d, 1)


def previous_trading_day(d: dt.date) -> dt.date:
    return workday(d, -1)


def most_recent_trading_day(reference: dt.date) -> dt.date:
    """The most recent date <= reference that is a trading day."""
    d = reference
    while not is_trading_day(d):
        d -= dt.timedelta(days=1)
    return d
