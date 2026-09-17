"""Chart geometry.

The maths happens here rather than in the template: `{% widthratio %}` can
scale a bar, but it cannot pick round axis ticks, cap a bar's thickness or
decide where a gridline goes, and a chart whose scale is invented in the
markup is a chart nobody can check.

Marks follow one spec across every chart on the site: columns capped at 24px
with a 4px rounded cap and a square baseline, hairline solid gridlines a step
off the surface, and a legend whenever two series share a plot.
"""

from decimal import Decimal
from math import floor, log10

from django import template

register = template.Library()

# Series colours. Validated with the data-viz palette checker against the card
# surface: chroma floor, CVD separation (worst adjacent dE 13.8 protan) and 3:1
# contrast all pass. The brand teal used for UI chrome (#0f766e) deliberately is
# NOT used here — it sits below the chroma floor and reads gray as a fill.
SERIES_COLORS = {
    "revenue": "#0d9488",
    "expenses": "#ea580c",
    "income": "#059669",
}

# Rounded step sizes, in units of the leading power of ten.
NICE_STEPS = (1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10)


def nice_ceiling(value) -> Decimal:
    """Round a maximum up to a value an axis can be labelled with.

    A raw maximum like 13,935.75 gives ticks nobody can read; this lifts it to
    15,000 so the gridlines land on round numbers.
    """
    value = float(value or 0)
    if value <= 0:
        return Decimal("1")
    power = 10 ** floor(log10(value))
    for step in NICE_STEPS:
        if value <= step * power:
            return Decimal(str(step * power))
    return Decimal(str(10 * power))


def compact(value) -> str:
    """Axis-tick formatting: 0, 7.5K, 1.2M."""
    number = float(value or 0)
    for limit, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if abs(number) >= limit:
            trimmed = f"{number / limit:.1f}".rstrip("0").rstrip(".")
            return f"{trimmed}{suffix}"
    return f"{number:,.0f}"


@register.filter(name="compact")
def compact_filter(value):
    return compact(value)


@register.inclusion_tag("charts/column_chart.html")
def column_chart(rows, series, label_key="label", ticks=4, height=180, chart_id="chart"):
    """A grouped column chart, laid out as HTML rather than a scaled SVG.

    HTML keeps the axis and tick text at its natural size at every width; an
    SVG `viewBox` would shrink the labels along with the plot on a phone.

    `series` is a list of (key, label) pairs; every series shares one axis —
    a second y-scale would invent a correlation that is not in the data.
    """
    rows = list(rows or [])
    keys = [key for key, _ in series]

    peak = max((float(row.get(key) or 0) for row in rows for key in keys), default=0)
    ceiling = nice_ceiling(peak)

    scale = [
        {
            "value": ceiling / ticks * index,
            "label": compact(ceiling / ticks * index),
            "offset": 100 - (100 / ticks * index),
        }
        for index in range(ticks, -1, -1)
    ]

    bands = []
    for row in rows:
        bars = []
        for key, label in series:
            value = Decimal(str(row.get(key) or 0))
            bars.append(
                {
                    "key": key,
                    "label": label,
                    "value": value,
                    "color": SERIES_COLORS.get(key, "#64748b"),
                    # A floor of 1% keeps a real-but-tiny value visible instead
                    # of rendering as nothing, which reads as missing data.
                    "height": max(float(value) / float(ceiling) * 100, 1) if value > 0 else 0,
                }
            )
        bands.append({"label": row.get(label_key, ""), "bars": bars, "row": row})

    return {
        "bands": bands,
        "scale": scale,
        "series": [
            {"key": key, "label": label, "color": SERIES_COLORS.get(key, "#64748b")}
            for key, label in series
        ],
        "height": height,
        "chart_id": chart_id,
        "has_data": peak > 0,
    }


@register.inclusion_tag("charts/sparkline.html")
def sparkline(rows, key, width=180, height=40, chart_id="spark"):
    """A 12-point trend line for a stat tile.

    SVG here rather than HTML: it is a polyline with no text to scale, and the
    last point is marked so "where we are now" reads without a label.
    """
    values = [float(row.get(key) or 0) for row in (rows or [])]
    if len(values) < 2:
        return {"points": "", "has_data": False, "width": width, "height": height}

    peak = max(values)
    floor_value = min(values)
    span = peak - floor_value or 1
    step = width / (len(values) - 1)
    pad = 3

    points = [
        (index * step, height - pad - ((value - floor_value) / span) * (height - 2 * pad))
        for index, value in enumerate(values)
    ]

    return {
        "points": " ".join(f"{x:.1f},{y:.1f}" for x, y in points),
        "area": (
            f"{points[0][0]:.1f},{height} "
            + " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
            + f" {points[-1][0]:.1f},{height}"
        ),
        "last": {"x": f"{points[-1][0]:.1f}", "y": f"{points[-1][1]:.1f}"},
        "color": SERIES_COLORS["revenue"],
        "has_data": peak > 0,
        "width": width,
        "height": height,
        "chart_id": chart_id,
    }
