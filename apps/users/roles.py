"""Role -> permission matrix, and the code that applies it.

Editing this table is the only supported way to change what a role can do.
`python manage.py sync_roles` (also run automatically after every migrate)
makes the database match it, including revoking permissions removed here.
"""

from django.contrib.auth.models import Group, Permission

from .models import Role

# Models each role may fully manage, as "app_label.model" with the actions
# allowed on it. "*" means every action Django generated for that model.
ROLE_MATRIX: dict[str, dict[str, tuple[str, ...]]] = {
    Role.OWNER: {
        "accounts.client": ("*",),
        "accounts.package": ("*",),
        "warehouse.pop": ("*",),
        "accounts.subscription": ("*",),
        "warehouse.category": ("*",),
        "warehouse.product": ("*",),
        "warehouse.onu": ("*",),
        "warehouse.stockmovement": ("*",),
        "accountants.invoice": ("*",),
        "accountants.invoiceline": ("*",),
        "accountants.payment": ("*",),
        "accountants.expense": ("*",),
        "accountants.income": ("*",),
        "accountants.upstreamsettlement": ("*",),
        "accountants.billingsettings": ("*",),
        "users.profile": ("*",),
    },
    Role.MANAGER: {
        "accounts.client": ("add", "change", "delete", "view"),
        "accounts.package": ("add", "change", "view"),
        "warehouse.pop": ("add", "change", "view"),
        "accounts.subscription": ("add", "change", "view"),
        "warehouse.category": ("add", "change", "delete", "view"),
        "warehouse.product": ("add", "change", "delete", "view"),
        "warehouse.onu": ("add", "change", "delete", "view"),
        "warehouse.stockmovement": ("add", "view"),
        # Managers see the money but do not remove records from the books.
        "accountants.invoice": ("add", "change", "view"),
        "accountants.invoiceline": ("add", "change", "view"),
        "accountants.payment": ("add", "view"),
        "accountants.expense": ("add", "change", "view"),
        "accountants.income": ("add", "change", "view"),
        "accountants.upstreamsettlement": ("add", "view"),
        "accountants.billingsettings": (
            "view",
            "view_dashboard",
            "view_financial_report",
            "export_data",
        ),
    },
    Role.ACCOUNTANT: {
        "accounts.client": ("view",),
        "accounts.package": ("view",),
        "warehouse.pop": ("view",),
        "accounts.subscription": ("view",),
        "warehouse.product": ("view",),
        "warehouse.onu": ("view",),
        "accountants.invoice": ("add", "change", "view"),
        "accountants.invoiceline": ("add", "change", "view"),
        "accountants.payment": ("add", "change", "view"),
        "accountants.expense": ("add", "change", "view"),
        "accountants.income": ("add", "change", "view"),
        # Reconciling the upstream statement is the accountant's job.
        "accountants.upstreamsettlement": ("add", "change", "view"),
        "accountants.billingsettings": (
            "view",
            "view_dashboard",
            "view_financial_report",
            "export_data",
        ),
    },
    Role.SUPPORT: {
        "accounts.client": ("change", "view"),
        "accounts.package": ("view",),
        "warehouse.pop": ("view",),
        "accounts.subscription": ("view",),
        "warehouse.product": ("view",),
        "warehouse.onu": ("change", "view"),
        "warehouse.stockmovement": ("add", "view"),
        "accountants.invoice": ("view",),
        "accountants.payment": ("view",),
    },
}

GROUP_NAMES = {role: f"role:{role}" for role in ROLE_MATRIX}

# Permissions that are not one of Django's four defaults.
CUSTOM_CODENAMES = {"view_dashboard", "view_financial_report", "export_data"}


def _codenames_for(target: str, actions: tuple[str, ...], available: set[str]) -> set[str]:
    _, model = target.split(".")
    if actions == ("*",):
        return {c for c in available if c.endswith(f"_{model}") or c in CUSTOM_CODENAMES}
    names = set()
    for action in actions:
        codename = action if action in CUSTOM_CODENAMES else f"{action}_{model}"
        if codename in available:
            names.add(codename)
    return names


def sync_roles(verbose: bool = False) -> dict[str, int]:
    """Create the role groups and set their permissions to match ROLE_MATRIX.

    Idempotent, and authoritative: permissions granted by hand in the admin are
    removed on the next run, so the matrix above is always the truth.
    """
    summary = {}
    for role, targets in ROLE_MATRIX.items():
        group, _ = Group.objects.get_or_create(name=GROUP_NAMES[role])
        wanted = set()
        for target, actions in targets.items():
            app_label, _ = target.split(".")
            available = dict(
                Permission.objects.filter(content_type__app_label=app_label).values_list(
                    "codename", "id"
                )
            )
            for codename in _codenames_for(target, actions, set(available)):
                wanted.add(available[codename])
        group.permissions.set(Permission.objects.filter(id__in=wanted))
        summary[role] = len(wanted)
        if verbose:
            print(f"  {GROUP_NAMES[role]}: {len(wanted)} permissions")
    return summary


def apply_role(user, role: str) -> None:
    """Put `user` in exactly one role group."""
    role_groups = Group.objects.filter(name__in=GROUP_NAMES.values())
    user.groups.remove(*role_groups)
    if role in GROUP_NAMES:
        group, _ = Group.objects.get_or_create(name=GROUP_NAMES[role])
        user.groups.add(group)
