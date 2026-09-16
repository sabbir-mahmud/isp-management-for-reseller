# ISP Manager

Back office for an internet service provider reseller: customers, subscriptions,
monthly invoicing, payment collection, inventory, and the reports that tell you
whether the business is making money.

Runs on **Python 3.14** and **Django 6.1**.

> **Scope:** this system does not talk to MikroTik, Cisco or any network
> hardware. It records and reports on the business. Nothing here provisions or
> disconnects a connection.

## What it does

| Area | Detail |
| --- | --- |
| **Customers** | Clients with status, POP, assigned ONU, contact and NID details; one-box search across name, code, phone, username and NID |
| **Subscriptions** | Plan and price per client, with the price frozen at sign-up so re-pricing a package never rewrites history |
| **Billing** | Monthly invoice generation (idempotent, with a dry-run preview), partial payments, cancellations, aged-debt tracking |
| **Settlement** | Both reseller arrangements — you collect and remit upstream, or clients pay upstream and you draw commission — with a running balance each way |
| **Money** | Expenses and non-subscription income, commission tracking, monthly P&L |
| **Inventory** | Serialised ONUs with assignment tracking, stock items with a movement ledger instead of an editable quantity |
| **Reporting** | Dashboard (collections, MRR, ARPU, churn, collection rate, aged debt, top debtors), financial report, CSV exports |
| **Access** | Four roles backed by real Django permissions, throttled login, audit stamps on every record |

## The two reseller arrangements

Resellers settle with their upstream operator in one of two ways, and the
system supports both — including a mix of the two in one customer base.

| | **You collect** | **Client pays upstream** |
| --- | --- | --- |
| Who the customer pays | you | the upstream operator, online |
| What you hold | the full bill | nothing |
| What you earn | your commission, kept from what you collected | your commission, paid to you afterwards |
| Running balance | **you owe upstream** the rest of what you collected | **upstream owes you** the commission |

Set the default under **Billing → Settings**, and override it on any individual
client who pays the other way. The commission rate resolves per client too:

```
the client's own rate  →  the package's rate  →  the rate in billing settings
```

Both are recorded on each invoice as it is raised, so changing the arrangement
or the rate later never rewrites what past months were worth.

**Billing → Upstream** shows the two running balances and the settlements
behind them: what you have remitted, and what commission you have been paid.

> One rule worth knowing: money you remit upstream is **not** an expense. It
> was never your revenue — your revenue is the commission — so record it as a
> settlement, never in the expense ledger, or the same money is deducted twice.
> Every profit figure in the app follows this rule.

## Quick start

```bash
make install                  # virtualenv + dependencies
cp .env.example .env

python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
# paste into SECRET_KEY in .env, and set DEBUG=True for local work

make migrate
make seed                     # optional: 350 clients, 15 packages, 150 POPs, 6 months of billing
make superuser                # or sign in as the seeded `owner`
make run
```

Then open http://127.0.0.1:8000/.

The seeded logins are `owner`, `manager`, `accountant` and `support`, all with
the password `demopass123`. Sign in as each to see how much of the application
a role can reach.

The dataset is deliberately full size — 350 clients across a three-level POP
tree, a 15-plan catalogue including two retired plans clients are still on, and
both settlement arrangements in use — so pagination, filtering and the POP
hierarchy are all exercised rather than merely rendering. Adjust with
`--clients`, `--pops` and `--months`.

## Running it for real

```bash
docker compose up --build     # Postgres + Redis + gunicorn
```

Or deploy the image anywhere that can run it. The essentials:

1. `SECRET_KEY`, `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` set, `DEBUG=False`.
2. `DATABASE_URL` pointing at Postgres.
3. `REDIS_URL` set once you run more than one worker — the login throttle
   counts failures in the cache, and a per-process cache lets each worker
   count separately.
4. `python manage.py migrate` on release (the `Procfile` does this).
5. The two scheduled jobs below.

Verify a deployment with `make check`, which runs Django's system checks, the
production hardening audit, and confirms models and migrations agree.

### Scheduled jobs

```cron
# Raise the month's invoices, on the 1st at 01:00
0 1 1 * * cd /app && python manage.py generate_invoices

# Flag invoices that have passed their due date, daily at 02:00
0 2 * * * cd /app && python manage.py refresh_overdue
```

`generate_invoices` skips clients who already have an invoice for the month, so
re-running it after a partial failure is safe. Preview first with
`make invoices ARGS="--dry-run"`.

## Roles

| Role | Can |
| --- | --- |
| **Owner** | Everything, including staff accounts and deleting financial records |
| **Manager** | Clients, inventory and billing; can record settlements but not delete them |
| **Accountant** | Invoices, payments, settlements, ledgers and reports; read-only on customers and inventory |
| **Support** | View clients and devices, change a client's status; no access to money |

Roles are defined in `apps/users/roles.py` and applied as Django groups by
`sync_roles`, which runs automatically after every `migrate`. Editing that
matrix is the only supported way to change access — permissions granted by hand
in the admin are removed on the next sync.

## Development

```bash
make test        # 286 tests
make coverage    # with a coverage report
make lint        # ruff check + format check
make format      # apply fixes
make check       # system checks, migration drift, deployment audit
make help        # every target
```

Tests live in `tests/` and run against a real database through pytest-django.
The suite covers billing rules, both settlement arrangements and the
commission arithmetic, metric definitions, role permissions, the login
throttle, model constraints and every page rendering.

## Configuration

Everything is read from the environment; see `.env.example` for the full list
with notes. Nothing in `isp_management/settings.py` needs editing to move
between environments.

| Variable | Notes |
| --- | --- |
| `SECRET_KEY` | **Required.** The app refuses to start without it |
| `DEBUG` | Defaults to `False` |
| `ALLOWED_HOSTS` | Comma-separated; required in production |
| `DATABASE_URL` | Omit for local SQLite; `postgres://…` in production |
| `REDIS_URL` | Shared cache; needed with more than one worker |
| `SITE_NAME` / `CURRENCY_SYMBOL` | Branding and currency display |
| `ADMIN_URL` | Moves the Django admin off its default path |

With `DEBUG=False`, TLS redirects, HSTS, secure cookies and the rest switch on
automatically.

## Further reading

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the layers fit together,
  the money model, the deletion policy, and what was deliberately left out
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md) — month-end routine, backups,
  and what to do when something looks wrong
