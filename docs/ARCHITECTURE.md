# Architecture

## What this system is

A back office for an ISP reseller: who the customers are, what they pay, what
has actually been collected, what the business spends, and what is left. It
does **not** talk to MikroTik, Cisco or any network device — nothing here
provisions, shapes or disconnects a connection. Every number comes from what
an operator recorded.

That boundary is deliberate and it shapes the model: `Client.username` is a
label used to match a customer to a connection someone else provisions, not a
credential this system issues.

## Layers

```
URL  →  View  →  Service  →  Model
                    ↑
                 Metrics  (read-only aggregation)
```

| Layer | Holds | Rule |
| --- | --- | --- |
| `views.py` | HTTP concerns: permissions, forms, redirects, context | No business arithmetic |
| `services.py` | Operations that span models or must be atomic | Raises `BillingError` / `ProvisioningError`, never returns HTTP |
| `models.py` | Shape, constraints, derived values | Enforces invariants the database can enforce |
| `reports/metrics.py` | Every business figure | Pure reads, takes the period as an argument |

A view calling `Invoice.objects.create(...)` directly is a bug: invoice
numbering, line items and status all live in `generate_invoices`.

## Apps

| Package | Label | Responsibility |
| --- | --- | --- |
| `apps.core` | `core` | Abstract models, money helpers, mixins, template tags, health check |
| `apps.users` | `users` | Staff profiles, the role→permission matrix, login throttle |
| `apps.accounts` | `accounts` | Clients, packages, subscriptions |
| `apps.warehouse` | `warehouse` | POPs, categories, stock, ONUs, stock movements |
| `apps.accountants` | `accountants` | Invoices, payments, expenses, income, billing settings |
| `apps.reports` | `reports` | Dashboard, financial report, CSV export (no models) |

The labels `accounts`, `warehouse` and `accountants` no longer describe their
contents well. They are kept because renaming an app label rewrites migration
history for every deployment; `AppConfig.verbose_name` carries the real name
in the admin.

## Two settlement arrangements

Resellers operate under one of two arrangements with their upstream operator,
and the difference decides what "revenue" even means:

| | `RESELLER` collects | `UPSTREAM` collects |
| --- | --- | --- |
| Who the customer pays | the reseller | the upstream operator, online |
| Cash through the reseller's hands | the full bill | nothing |
| The reseller's earnings | commission, kept from what they collected | commission, paid across afterwards |
| Resulting balance | **payable** — the upstream share is held and owed | **receivable** — commission is earned and awaited |

`CollectionMode` lives in `apps/core/choices.py` rather than in either app,
because the customer app needs it for a per-client override and the billing
app needs it for settings, invoices and payments; defining it in one of them
would make the pair sensitive to `INSTALLED_APPS` ordering.

### Resolution order

Both the arrangement and the rate are resolved per client, because a real
reseller's base is mixed — some customers pay at the counter, others pay the
portal — and upstream operators commonly pay a different rate per plan tier.

```
collection mode:     Client.collection_mode      -> BillingSettings.collection_mode
commission rate:     Subscription.commission_percent
                     -> Package.commission_percent
                     -> BillingSettings.commission_percent
```

Both are **snapshotted onto the invoice** when it is raised. Switching the
business to a different arrangement, or renegotiating the rate, therefore
never restates what last quarter's invoices were worth.

### Where the money is tracked

- `Payment.commission_amount` / `upstream_amount` — split per payment, not per
  invoice, so a half-paid bill earns half its commission rather than all of it
  up front. `Payment.collection_mode` is denormalised from the invoice so
  cash-position queries never join back through it.
- `UpstreamSettlement` — money moving between the two parties, in either
  direction: a `REMITTANCE` out, or a `COMMISSION_PAYOUT` in.
- `services.upstream_position()` — the two running balances, all-time or for
  one month.

### A remittance is not an expense

The upstream share was never the reseller's revenue. Recording a remittance as
an `Expense` *as well* would deduct the same money twice. This is why
`metrics.revenue()` is commission plus other income, and never gross
collections — counting gross overstates the business by the upstream share,
typically four fifths of it. The UI states this on the settlement form, and
`seed_demo` deliberately follows the same rule.

### Splitting money safely

`core.utils.split_commission` subtracts the remainder rather than computing
both halves, so the two parts always add back to exactly the original. Rounding
each half independently leaks a paisa on roughly half of all invoices, and
those pennies become a permanent unexplained gap against the upstream
operator's own books. `tests/test_collection_modes.py` asserts the property
across a range of awkward amounts.

## The money model

This is the part that was redesigned most, so it is worth stating plainly.

The original system computed revenue as
`SUM(package.price WHERE client.status = 'active')`. That is a forecast. It
cannot express a partial payment, an arrear, a mid-month join, a discount or
a month someone simply did not pay.

Now:

- **`Subscription`** — what a client is on and what they pay. The price is
  copied from the package at sign-up, so re-pricing a package never rewrites
  what existing customers were charged. One active subscription per client is
  a database constraint; earlier plans stay as cancelled rows.
- **`Invoice`** — what was billed for one client for one month. One per
  client per period (a partial unique index that excludes cancelled rows), so
  the monthly job is safe to re-run.
- **`Payment`** — what was actually received. Recalculates its invoice on
  save and on delete, which is what keeps `amount_paid` and `status` true.
- **`Expense` / `Income`** — money out, and money in that is not a
  subscription. Subscription revenue is *never* entered as `Income`, and the
  upstream share is *never* entered as an `Expense`, so the ledgers can be
  added together without double counting.

`MRR` is labelled a forecast in the UI. `collected` is cash. They are
different numbers and the dashboard never conflates them.

### Money is always `Decimal`

`core.models.money_field` exists so no one reintroduces the original
`FloatField` prices. Aggregates go through `core.aggregates.money_sum`,
because `Coalesce(Sum("total"), 0)` raises `FieldError: Expression contains
mixed types` the moment the default is an int or float beside a
`DecimalField`.

## Deletion policy

| Model | On delete | Why |
| --- | --- | --- |
| `Client` | Soft delete | Invoices and payments point at it; the books must stay readable |
| `Package` ← `Subscription` | `PROTECT` | Deleting a plan must not delete its customers (the original cascaded) |
| `Pop` ← `Client` | `PROTECT` | Same |
| `Pop` ← `Pop` (parent) | `SET_NULL` | Retiring an upstream POP must not delete everything below it |
| `Invoice` ← `Payment` | `PROTECT` | An invoice with money against it cannot vanish |
| `UpstreamSettlement` | Owner-only delete | Removing one moves the settlement balance |
| `Client` ← `Onu` | `SET_NULL` | Hardware outlives the customer |

## Permissions

Roles are **not** checked in views. Each role maps to a Django `Group` holding
real model permissions, defined in `apps/users/roles.py` and applied by
`sync_roles()`, which runs after every `migrate`. So `user.has_perm(...)`, the
admin and the templates all give the same answer, and the matrix is the single
place to change access.

`sync_roles` is authoritative: permissions granted by hand in the admin are
removed on the next run.

| Role | In short |
| --- | --- |
| Owner | Everything, including staff and deletions |
| Manager | Clients, inventory, billing; can record settlements but not delete them |
| Accountant | The books, settlements and reports; read-only on customers and inventory |
| Support | Sees clients and devices, can change a client's status; no money |

`Profile` extends the built-in user rather than replacing `AUTH_USER_MODEL`,
because this project already has an `auth_user` table in the wild and swapping
the user model after the first migration is a known one-way door.

## Performance

- List pages annotate rather than compute per row. `ClientQuerySet.with_related`
  annotates the outstanding balance; as a property it cost one query per row.
  `tests/test_views.py` asserts a ceiling on the query count so it cannot
  regress.
- `revenue_trend` groups in the database (3 queries for 12 months, not 24).
- Indexes exist on the columns the list pages filter and sort by.

## Jobs

| Command | When | Notes |
| --- | --- | --- |
| `generate_invoices` | Monthly, on the 1st | Idempotent; `--dry-run` to preview |
| `refresh_overdue` | Daily | Flips unpaid invoices past their due date |
| `sync_roles` | After a deploy | Also runs automatically after `migrate` |
| `seed_demo` | Never in production | Refuses to run over existing clients without `--force` |

## What was deliberately left out

- **Device integration.** Out of scope by requirement.
- **A REST API.** Nothing consumes one yet; adding DRF later does not disturb
  the service layer, which is where the rules already live.
- **Multi-tenancy.** One reseller per deployment. Retrofitting it means a
  tenant FK on every model and scoped managers — a large change, and not one
  to make speculatively.
- **Automatic suspension for non-payment.** The data supports it (aged debt is
  already computed), but suspending a customer is a business decision that
  should stay a deliberate click.
