"""Sidebar navigation.

The sidebar used to repeat a `{% if perms %}` / `{% url %}` / active-state
`slice` expression for every one of its sixteen links, which made the active
rule easy to get subtly wrong (`'income'` is a prefix of nothing else, but
`'settlement'` and `'settings'` overlap). One tag owns that logic now.
"""

from django import template
from django.template.base import token_kwargs
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.text import slugify

register = template.Library()


def _current(context) -> str:
    request = context["request"]
    return getattr(request.resolver_match, "url_name", "") or ""


def _matches(current: str, url_name: str, match: str | None = None) -> bool:
    """Does `current` belong to the page `url_name` names?

    `match` is the prefix that marks the item active; it defaults to the URL
    name with any `_list` suffix removed, so `client_list` also highlights for
    `client_detail` and `client_edit`. Matching on `prefix_` rather than
    `prefix` keeps names that merely share an opening from colliding.
    """
    prefix = match or url_name.removesuffix("_list")
    return current == url_name or current.startswith(f"{prefix}_")


@register.inclusion_tag("layout/nav_item.html", takes_context=True)
def nav_item(context, url_name, label, icon_name, match=None, badge=None, badge_tone="danger"):
    """Render one sidebar link."""
    return {
        "url": reverse(url_name),
        "label": label,
        "icon_name": icon_name,
        "is_active": _matches(_current(context), url_name, match),
        "badge": badge or None,
        "badge_tone": badge_tone,
    }


class NavGroupNode(template.Node):
    """Renders a collapsible group around whatever links it wraps."""

    def __init__(self, nodelist, kwargs):
        self.nodelist = nodelist
        self.kwargs = kwargs

    def render(self, context):
        options = {key: value.resolve(context) for key, value in self.kwargs.items()}
        children = self.nodelist.render(context)

        # Whether the group holds the open page is read back off its own
        # rendered children rather than from a second list of page names kept
        # in step by hand. One source of truth, and it cannot drift.
        is_open = 'class="nav-link active"' in children

        group = template.loader.get_template("layout/nav_group.html")
        return group.render(
            {
                "slug": options.get("slug") or slugify(options.get("label", "")),
                "label": options.get("label", ""),
                "icon_name": options.get("icon", ""),
                "badge": options.get("badge") or None,
                "badge_tone": options.get("badge_tone", "danger"),
                "is_open": is_open,
                "children": mark_safe(children),
            },
            request=context.get("request"),
        )


@register.tag("nav_group")
def nav_group(parser, token):
    """{% nav_group label="Billing" icon="invoices" %} ... {% endnav_group %}

    Decided on the server, so a group containing the open page arrives already
    expanded. Leaving it to JavaScript would paint every group shut for a
    frame and then jump.
    """
    bits = token.split_contents()[1:]
    kwargs = token_kwargs(bits, parser, support_legacy=False)
    if bits:
        raise template.TemplateSyntaxError(
            "nav_group takes keyword arguments only (label, icon, slug, badge, badge_tone)."
        )
    nodelist = parser.parse(("endnav_group",))
    parser.delete_first_token()
    return NavGroupNode(nodelist, kwargs)
