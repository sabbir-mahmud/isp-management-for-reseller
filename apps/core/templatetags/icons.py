"""Inline SVG icons.

Drawn inline rather than pulled from an icon font or a CDN sprite: the app has
to work on an office LAN with no internet, inline paths cannot 404, and they
inherit `currentColor` so a single CSS rule restyles every icon.

Paths are 24x24, stroked rather than filled, so they stay crisp at the 18px
the sidebar renders them at.
"""

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Each entry is the inner markup of a 24x24 stroked icon.
ICONS = {
    "dashboard": '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/>'
    '<rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    "report": '<path d="M3 3v18h18"/><rect x="7" y="12" width="3" height="5" rx="1"/>'
    '<rect x="12" y="8" width="3" height="9" rx="1"/><rect x="17" y="5" width="3" height="12" rx="1"/>',
    "clients": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
    '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "packages": '<path d="M12 2 3 7v10l9 5 9-5V7z"/><path d="M3 7l9 5 9-5"/><path d="M12 12v10"/>',
    "pops": '<path d="M12 22s8-5.33 8-12a8 8 0 1 0-16 0c0 6.67 8 12 8 12z"/><circle cx="12" cy="10" r="3"/>',
    "invoices": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
    '<path d="M14 2v6h6"/><path d="M8 13h8"/><path d="M8 17h5"/>',
    "payments": '<rect x="2" y="5" width="20" height="14" rx="2"/><circle cx="12" cy="12" r="2.5"/>'
    '<path d="M6 12h.01"/><path d="M18 12h.01"/>',
    "upstream": '<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="M16 21l4-4-4-4"/><path d="M20 17H4"/>',
    "expenses": '<path d="M22 17 13.5 8.5 8.5 13.5 2 7"/><path d="M16 17h6v-6"/>',
    "income": '<path d="M22 7 13.5 15.5 8.5 10.5 2 17"/><path d="M16 7h6v6"/>',
    "onu": '<rect x="2" y="13" width="20" height="8" rx="2"/><path d="M6 17h.01"/><path d="M10 17h.01"/>'
    '<path d="M18 17h-4"/><path d="M6.5 8.5a6 6 0 0 1 11 0"/><path d="M9.5 5.5a10 10 0 0 1 5 0"/>',
    "stock": '<path d="M21 8V5a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v3"/><rect x="2" y="8" width="20" height="12" rx="1"/>'
    '<path d="M10 12h4"/>',
    "categories": '<path d="M3 7V4a1 1 0 0 1 1-1h3l11 11-4 4L3 7z"/><circle cx="7" cy="7" r="1.2"/>'
    '<path d="M14 3h6a1 1 0 0 1 1 1v6"/>',
    "movements": '<path d="M7 3v14"/><path d="M4 14l3 3 3-3"/><path d="M17 21V7"/><path d="M14 10l3-3 3 3"/>',
    "staff": '<rect x="2" y="4" width="20" height="16" rx="2"/><circle cx="9" cy="11" r="2.5"/>'
    '<path d="M5 17a4 4 0 0 1 8 0"/><path d="M16 10h4"/><path d="M16 14h4"/>',
    "settings": '<path d="M4 6h10"/><circle cx="17" cy="6" r="2.5"/><path d="M20 12H10"/>'
    '<circle cx="7" cy="12" r="2.5"/><path d="M4 18h10"/><circle cx="17" cy="18" r="2.5"/>',
    "admin": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "logout": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    "key": '<circle cx="7.5" cy="15.5" r="4.5"/><path d="m10.7 12.3 8.3-8.3"/><path d="m17 6 3 3"/><path d="m14 9 3 3"/>',
    "menu": '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/>',
    "close": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "reset": '<path d="M3 12a9 9 0 1 0 2.6-6.4"/><path d="M3 4v5h5"/>',
    "chevron": '<path d="m9 6 6 6-6 6"/>',
    "collapse": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/><path d="m15 9-2 3 2 3"/>',
}


@register.simple_tag
def icon(name, size=18, css_class="icon"):
    """Render a named icon inline.

    An unknown name renders nothing rather than raising: a missing icon should
    never take a page down.
    """
    body = ICONS.get(name)
    if body is None:
        return ""
    return mark_safe(
        f'<svg class="{css_class}" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true" focusable="false">{body}</svg>'
    )
