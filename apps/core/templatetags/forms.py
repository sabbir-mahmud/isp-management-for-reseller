"""Form layout for the shared create/update screen."""

from django import forms, template

register = template.Library()


@register.simple_tag
def form_sections(form):
    """Group a form's bound fields into the sections the template renders.

    Reads `fieldsets`, `wide_fields` and `compact_fields` off the form when it
    declares them (see `BootstrapFormMixin`) and falls back to a single
    untitled section otherwise — so a plain `forms.Form` that never heard of
    any of this still renders every one of its fields.

    Any field left out of every fieldset is appended in a trailing group
    rather than dropped: adding a field to `Meta.fields` and forgetting to
    place it should show an untidy form, not silently lose the input.
    """
    fieldsets = getattr(form, "fieldsets", ()) or ({"fields": tuple(form.fields)},)
    wide = set(getattr(form, "wide_fields", ()) or ())
    compact = set(getattr(form, "compact_fields", ()) or ())
    addons = getattr(form, "field_addons", None) or {}
    prefixes = getattr(form, "field_prefixes", None) or {}

    def layout(name):
        """One bound field, plus how the template should size it."""
        bound = form[name]
        widget = bound.field.widget
        return {
            "field": bound,
            "wide": name in wide or isinstance(widget, forms.Textarea),
            "compact": name in compact,
            "checkbox": isinstance(widget, forms.CheckboxInput),
            "radio": isinstance(widget, forms.RadioSelect),
            "addon": addons.get(name, ""),
            "prefix": prefixes.get(name, ""),
        }

    placed, sections = set(), []
    for spec in fieldsets:
        names = [name for name in spec.get("fields", ()) if name in form.fields]
        placed.update(names)
        if names:
            sections.append(
                {
                    "title": spec.get("title", ""),
                    "caption": spec.get("caption", ""),
                    "fields": [layout(name) for name in names],
                }
            )

    unplaced = [name for name in form.fields if name not in placed]
    if unplaced:
        sections.append(
            {"title": "Other", "caption": "", "fields": [layout(name) for name in unplaced]}
        )
    return sections
