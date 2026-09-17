"""Aggregation helpers for money columns.

`Coalesce(Sum("total"), 0)` looks harmless and raises `FieldError: Expression
contains mixed types` the moment the default is a float or plain int next to a
DecimalField. Declaring the zero once, with its output field, keeps every
money aggregate consistent.
"""

from decimal import Decimal

from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce

MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)
MONEY_ZERO = Value(Decimal("0.00"), output_field=MONEY_FIELD)


def money_sum(expression):
    """Sum a money column, yielding Decimal("0.00") instead of None."""
    return Coalesce(Sum(expression, output_field=MONEY_FIELD), MONEY_ZERO)
