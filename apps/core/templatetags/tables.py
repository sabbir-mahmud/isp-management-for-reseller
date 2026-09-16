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


def _query_keys(name, field):
    """The query-string keys one filter field reads.

    Usually just its name; a two-part widget such as a date range posts one
    key per part (`received_on_after`, `received_on_before`) and none under
    the name itself, so looking only at the name missed it entirely.
    """
    widget = field.widget
    suffixes = getattr(widget, "suffixes", None)
    if suffixes and hasattr(widget, "suffixed"):
        # django-filter's range widgets: `_min`/`_max`, `_after`/`_before`.
        return [widget.suffixed(name, suffix) for suffix in suffixes]
    names = getattr(widget, "widgets_names", None)
    return [f"{name}{suffix}" for suffix in names] if names else [name]


#: The `when` value that hands over to a filterset's date range.
CUSTOM_RANGE = "custom"


@register.simple_tag(takes_context=True)
def toolbar_fields(context, filterset):
    """The filterset's fields, each tagged with how the toolbar draws it.

    * `search` — the first field, always: the wide box with the icon.
    * `range` — a two-part date range, drawn as one "from → to" control
      with its inputs named the way the filter reads them.
    * `field` — everything else, labelled above its input. A select also
      applies as soon as it changes (`autosubmit`).

    A filterset may declare `custom_range = ("when", "occurred_on")`: the
    range then stays out of the way until the `when` select is set to
    Custom, or a range is already in the URL.
    """
    from django import forms

    request = context["request"]
    trigger, ranged = getattr(filterset, "custom_range", (None, None))
    choosing_custom = bool(trigger) and request.GET.get(trigger) == CUSTOM_RANGE

    items = []
    for index, bound in enumerate(filterset.form):
        name, field = bound.name, bound.field
        keys = _query_keys(name, field)
        item = {"field": bound, "name": name, "label": field.label or name.title()}

        if index == 0:
            item["kind"] = "search"
        elif len(keys) > 1:
            values = [request.GET.get(key, "") for key in keys]
            parts = getattr(field.widget, "widgets", [])
            input_type = parts[0].attrs.get("type", "text") if parts else "text"
            item.update(
                kind="range",
                id=f"id_{name}",
                parts=[
                    {"name": key, "value": value, "caption": caption}
                    for key, value, caption in zip(keys, values, ("From", "To"), strict=False)
                ],
                input_type=input_type,
                controlled_by=f"id_{trigger}" if name == ranged else "",
                hidden=name == ranged and not choosing_custom and not any(values),
            )
        else:
            item.update(
                kind="field",
                autosubmit=isinstance(field.widget, forms.Select),
                controls=bound.auto_id if name == trigger else "",
            )
        items.append(item)
    return items


@register.simple_tag(takes_context=True)
def has_active_filters(context, filterset):
    """Whether any of the filterset's own fields is currently applied.

    `page` and `sort` are in the query string too, but resetting is about the
    search — not about sending the reader back to page 1 of an unsorted list.
    """
    request = context["request"]
    return any(
        request.GET.get(key)
        for name, field in filterset.form.fields.items()
        for key in _query_keys(name, field)
    )


@register.inclusion_tag("partials/active_filters.html", takes_context=True)
def active_filters(context, filterset):
    """Pills naming each applied filter, each able to clear just itself.

    Without them a filtered list looks the same as an unfiltered one until you
    read the form — which is how people end up convinced records are missing.
    """
    request = context["request"]
    pills = []

    for name, field in filterset.form.fields.items():
        keys = _query_keys(name, field)
        if len(keys) > 1:
            # A range reads as one pill, "from – to", and clears as one.
            parts = [request.GET.get(key, "") for key in keys]
            if not any(parts):
                continue
            pills.append(
                {
                    "label": field.label or name.replace("_", " ").title(),
                    "value": " – ".join(part or "…" for part in parts),
                    "remove_url": filtered_url(request, **dict.fromkeys(keys)),
                }
            )
            continue

        raw = request.GET.get(name)
        if not raw:
            continue
        if raw == CUSTOM_RANGE and name == getattr(filterset, "custom_range", (None,))[0]:
            # The range's own pill already says which dates.
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
