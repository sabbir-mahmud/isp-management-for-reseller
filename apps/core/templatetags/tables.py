"""Sortable column headers."""

from django import template

from apps.core.utils import filtered_url

register = template.Library()


@register.inclusion_tag("partials/sort_header.html", takes_context=True)
def sort_header(context, key, label, numeric=False):
    """A column heading that sorts, toggling direction on the active column.

    Rebuilds the whole query string rather than replacing it, so sorting a
    filtered list keeps the filter — and drops back to page 1, because page 7
    of the old order is meaningless in the new one.
    """
    request = context["request"]
    current = context.get("sort") or ""
    is_active = current.lstrip("-") == key
    descending = is_active and current.startswith("-")

    params = request.GET.copy()
    # First click on a new column sorts ascending; clicking the active one flips.
    params["sort"] = key if (not is_active or descending) else f"-{key}"
    params.pop("page", None)

    return {
        "url": f"?{params.urlencode()}",
        "label": label,
        "numeric": numeric,
        "is_active": is_active,
        "descending": descending,
    }


@register.simple_tag(takes_context=True)
def has_active_filters(context, filterset):
    """Whether any of the filterset's own fields is currently applied.

    `page` and `sort` are in the query string too, but resetting is about the
    search — not about sending the reader back to page 1 of an unsorted list.
    """
    request = context["request"]
    return any(request.GET.get(name) for name in filterset.form.fields)


@register.inclusion_tag("partials/active_filters.html", takes_context=True)
def active_filters(context, filterset):
    """Pills naming each applied filter, each able to clear just itself.

    Without them a filtered list looks the same as an unfiltered one until you
    read the form — which is how people end up convinced records are missing.
    """
    request = context["request"]
    pills = []

    for name, field in filterset.form.fields.items():
        raw = request.GET.get(name)
        if not raw:
            continue

        label = field.label or name.replace("_", " ").title()
        shown = raw
        # Resolve the stored value to what the reader chose, so a pill reads
        # "POP: Main POP" rather than "POP: 3".
        choices = getattr(field, "choices", None)
        if choices:
            shown = next((str(text) for value, text in choices if str(value) == raw), raw)

        pills.append(
            {
                "label": label,
                "value": shown,
                "remove_url": filtered_url(request, **{name: None}),
            }
        )

    return {"pills": pills, "clear_url": request.path}
