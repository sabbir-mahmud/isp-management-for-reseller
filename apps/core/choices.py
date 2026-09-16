"""Domain choices shared by more than one app.

`CollectionMode` is needed by both the customer app (a per-client override)
and the billing app (settings, invoices, payments). Defining it here rather
than in either one keeps the two apps from importing each other at module
load, which would make them sensitive to `INSTALLED_APPS` ordering.
"""

from django.db import models


class CollectionMode(models.TextChoices):
    """Who takes the customer's money.

    Resellers run one of two settlement arrangements, and the difference
    decides what the reseller's revenue actually is:

    * `RESELLER` — the reseller collects the bill, keeps the commission and
      remits the rest upstream. Gross cash passes through their hands, and
      the upstream share is a liability from the moment it is collected.
    * `UPSTREAM` — the customer pays the upstream operator directly (online),
      and the upstream operator pays the reseller a commission afterwards.
      No customer cash reaches the reseller; the commission is a receivable.

    In both cases the reseller's revenue is the commission, never the gross.
    """

    RESELLER = "reseller", "Reseller collects"
    UPSTREAM = "upstream", "Client pays upstream directly"
