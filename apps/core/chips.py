"""Summary chips.

The counts above an index page are also its coarse filter — clicking
"Suspended" should show the suspended rows rather than sending the reader to a
dropdown. One helper builds them so the three customer pages cannot drift into
three slightly different components.
"""

from dataclasses import dataclass

from apps.core.utils import filtered_url


@dataclass(frozen=True)
class Chip:
    label: str
    value: int | str
    url: str
    is_active: bool
    tone: str = ""


def build_chips(request, param: str, rows: list[dict]) -> list[Chip]:
    """Turn `[{label, value, match, tone}]` into linked chips.

    `match` is the value this chip sets `param` to; `None` means "clear it",
    which is how the leading All chip is expressed.
    """
    current = request.GET.get(param, "")
    return [
        Chip(
            label=row["label"],
            value=row["value"],
            url=filtered_url(request, **{param: row.get("match")}),
            is_active=current == (row.get("match") or ""),
            tone=row.get("tone", ""),
        )
        for row in rows
    ]
