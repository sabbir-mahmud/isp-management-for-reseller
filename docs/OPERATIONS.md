# Operations

## The monthly routine

1. **1st, 01:00 — invoices are raised.** The cron job runs
   `generate_invoices`. To do it by hand, open **Billing → Generate month**;
   the page previews exactly what will be billed before writing anything.
2. **Through the month — record payments.** Find the client or the invoice,
   press **Take payment**. Partial payments are fine; the invoice moves to
   *Partially paid* and keeps the remainder outstanding.
3. **Daily, 02:00 — overdue invoices are flagged** by `refresh_overdue`.
4. **Month end — settle with the upstream operator.** Open **Billing →
   Upstream**. It shows two balances:
   * *You owe them* — the upstream share of what you collected. Pay it, then
     **Record remittance** for that amount.
   * *They owe you* — commission on bills your clients paid upstream directly.
     When it arrives, **Record commission received**.
5. **Check the numbers.** **Reports → Financial report** shows what was billed,
   what customers paid, the commission you earned, expenses by category and the
   aged debt.

## Common tasks

**Someone paid the wrong invoice.** Reverse the payment on the invoice page
(Owner only), then record it against the right one. Reversal restores the
balance on the original invoice.

**A client is leaving.** Set their status to *Terminated* on their page. That
cancels the subscription and returns their ONU to stock in one step — which is
why it should be done there rather than by editing fields.

**A price changed for one client.** Edit the client and change the monthly
price. Changing the *package* price affects new subscriptions only, on purpose.

**A client should not be billed this month.** Cancel the invoice (only possible
while no payment is recorded against it). Cancelled invoices are excluded from
the one-per-month constraint, so a corrected one can be raised.

**Stock count is wrong.** Record an *Adjustment* movement rather than editing
the quantity — quantity is the sum of the movement ledger, so it is the only
thing that will hold.

**Someone left the company.** Set their account inactive under **Staff**. Do not
delete it: their name is on the payments they recorded.

**A client switches to paying the upstream portal online.** Edit the client and
set *Collected by* to "Client pays upstream directly". Invoices already raised
keep the old arrangement — which is correct, because that is how those months
actually settled — and everything from the next run uses the new one.

**The upstream operator pays a different rate on one plan.** Put the rate on
the package. For a single negotiated client, put it on the client instead; the
client's rate wins over the package's, and the package's over the default.

## Backups

The database is the whole system; nothing else holds state that matters.

```bash
# Postgres
pg_dump "$DATABASE_URL" --format=custom --file=isp-$(date +%F).dump

# Restore
pg_restore --clean --if-exists --dbname="$DATABASE_URL" isp-2026-09-16.dump
```

Take one before every deploy that includes a migration, and restore it into a
scratch database once a quarter — an untested backup is not a backup.

## When something looks wrong

**An invoice total looks wrong.** Open it: the lines, the discount and each
payment are all listed. `invoice.recalculate()` re-derives the total, the paid
amount and the status from those rows, so the detail page is always the truth.

**The dashboard disagrees with the invoice list.** They measure different
things, by design. *Billed* is what was invoiced for a period. *Collected* is
cash received during that calendar month, whatever period it was billed for. A
payment in September against an August invoice counts as September cash and
August billing.

**MRR does not match collections.** It never will. MRR is a forecast — live
subscriptions times their price. Collections are what arrived. The gap is your
collection rate, which is on the dashboard.

**Revenue looks far lower than the cash I handled.** That is correct. Your
revenue is your commission; the rest of what you collect belongs to the
upstream operator and shows up as *You owe upstream*. The dashboard shows both:
*Cash you collected* is the gross, *Revenue earned* is yours.

**I recorded the upstream payment as an expense and profit collapsed.** Delete
that expense and record it under **Billing → Upstream** instead. The upstream
share is already excluded from your revenue, so booking it as a cost as well
deducts the same money twice.

**The upstream balance looks wrong.** It is derived, not stored: payables are
the upstream share of payments you collected, minus your remittances;
receivables are commission on upstream-collected payments, minus what they have
paid you. Check the payment list (filter by *Collected by*) and the settlement
list for that month — one of the two is missing a row.

**Someone cannot reach a page.** Check their role under **Staff**. If the role
is right but access is not, run `python manage.py sync_roles` — the groups may
have been edited by hand in the admin, and the sync restores the matrix.

**Locked out after failed logins.** The throttle clears itself after
`LOGIN_FAILURE_TIMEOUT` (15 minutes by default). To clear it immediately,
restart the app if the cache is in-memory, or flush the `login-throttle:*` keys
from Redis.

## Health and logs

- `GET /healthz` returns `{"status": "ok", "database": true}` and a 503 when
  the database is unreachable. Unauthenticated and free of business data, so it
  is safe to point a load balancer at.
- Logging goes to stdout. `apps.users` logs every sign-in, failure and lockout;
  `apps.accountants` logs every invoice generation run.

## Upgrading

```bash
git pull
pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py sync_roles
# restart the web process
```

`make check` before restarting will catch a model change whose migration was
never committed.
