"""Date/period helpers.

Billing is monthly, so a "period" here is always the first day of a month.
Storing it as a real `DateField` (rather than the old free-text Month/Year
lookup tables) makes ordering, ranges and grouping the database's job.
"""

import calendar
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone


def month_start(value: dt.date | None = None) -> dt.date:
    """Normalise any date to the first of its month (today when omitted)."""
    value = value or timezone.localdate()
    return value.replace(day=1)


def month_end(value: dt.date | None = None) -> dt.date:
    value = month_start(value)
    return value.replace(day=calendar.monthrange(value.year, value.month)[1])


def add_months(value: dt.date, months: int) -> dt.date:
    """Shift a month-start by `months`, clamping the day to a valid one."""
    total = (value.year * 12 + value.month - 1) + months
    year, month = divmod(total, 12)
    day = min(value.day, calendar.monthrange(year, month + 1)[1])
    return dt.date(year, month + 1, day)


def previous_month(value: dt.date | None = None) -> dt.date:
    return add_months(month_start(value), -1)


def next_month(value: dt.date | None = None) -> dt.date:
    return add_months(month_start(value), 1)


def month_range(end: dt.date | None = None, months: int = 12) -> list[dt.date]:
    """The last `months` month-starts, oldest first, ending at `end`'s month."""
    end = month_start(end)
    return [add_months(end, -offset) for offset in range(months - 1, -1, -1)]


def clamp_day(year: int, month: int, day: int) -> dt.date:
    """Build a date, pulling day 31 back to the 28th/30th where needed."""
    return dt.date(year, month, min(day, calendar.monthrange(year, month)[1]))


def percentage(part, whole) -> float:
    """Safe percentage — returns 0.0 rather than exploding on an empty base."""
    whole = float(whole or 0)
    if not whole:
        return 0.0
    return round(float(part or 0) / whole * 100, 1)


def split_commission(amount, percent) -> tuple[Decimal, Decimal]:
    """Split `amount` into (commission, upstream share).

    The remainder is subtracted rather than calculated, so the two parts
    always add back to exactly `amount`. Rounding each half independently
    leaks a paisa on roughly half of all invoices, and those pennies end up
    as a permanent unexplained gap between the reseller's books and the
    upstream operator's.
    """
    amount = Decimal(amount or 0)
    commission = (amount * Decimal(percent or 0) / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return commission, amount - commission
