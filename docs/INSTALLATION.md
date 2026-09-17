# Installation

This guide gets ISP Manager running on your own machine, for trying it out or
working on it. To put it on a server for real use, follow
[DEPLOYMENT.md](DEPLOYMENT.md) instead.

- [Requirements](#requirements)
- [1. Get the code](#1-get-the-code)
- [2. Create the environment](#2-create-the-environment)
- [3. Configure](#3-configure)
- [4. Create the database](#4-create-the-database)
- [5. Run it](#5-run-it)
- [Running with Docker instead](#running-with-docker-instead)
- [Everyday commands](#everyday-commands)
- [Troubleshooting](#troubleshooting)

---

## Requirements

| | Version | Notes |
| --- | --- | --- |
| Python | **3.14** | The code uses 3.14 syntax; older versions will not start |
| Git | any | To clone the repository |
| Make | any | Optional — every `make` target is a one-line command you can run by hand |
| PostgreSQL | 15 or newer | Optional locally — SQLite is used when no database is configured |
| Redis | 7 | Optional locally — only needed with several web workers |

Check your Python:

```bash
python3 --version   # Python 3.14.x
```

If you have an older one, install 3.14 from [python.org](https://www.python.org/downloads/),
with `brew install python@3.14` on macOS, or with
[`uv python install 3.14`](https://docs.astral.sh/uv/) on any platform.

## 1. Get the code

```bash
git clone https://github.com/sabbir-mahmud/isp-management-for-reseller.git
cd isp-management-for-reseller
```

## 2. Create the environment

```bash
make install
```

That creates a virtualenv in `venv/` and installs the runtime and development
dependencies. Without Make:

```bash
python3.14 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
```

## 3. Configure

All settings come from environment variables, read from a `.env` file in the
project root.

```bash
cp .env.example .env
```

Generate a secret key and paste it into `SECRET_KEY`:

```bash
venv/bin/python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

For local work, also set:

```dotenv
DEBUG=True
```

Leave `DATABASE_URL` unset to use a local SQLite file (`db.sqlite3`). To use
Postgres instead:

```dotenv
DATABASE_URL=postgres://isp:secret@localhost:5432/isp
```

Every variable is described in [`.env.example`](../.env.example).

## 4. Create the database

```bash
make migrate
```

This also creates the four staff roles (Owner, Manager, Accountant, Support)
and their permissions.

Then **either** load the demo data:

```bash
make seed
```

which creates 350 clients, 15 packages, 150 POPs in a three-level tree and six
months of billing, plus four logins — `owner`, `manager`, `accountant` and
`support` — all with the password `demopass123`. Adjust the size with
`venv/bin/python manage.py seed_demo --clients 50 --pops 10 --months 3`.

**or** start empty with your own owner account:

```bash
make superuser
```

## 5. Run it

```bash
make run
```

Open <http://127.0.0.1:8000/> and sign in.

A sensible first tour:

1. **Billing → Settings** — who collects the money by default, your commission
   rate and invoice numbering.
2. **Customers → Packages** and **POPs** — the plans you sell and where clients
   connect.
3. **Customers → Clients → Add client** — their details, plan and billing day.
4. **Billing → Invoices → Generate month** — preview, then raise the month's
   invoices.

## Running with Docker instead

If you have Docker, this starts Postgres, Redis and the app under gunicorn —
the same shape as production:

```bash
cp .env.example .env              # set SECRET_KEY in it
docker compose up --build
```

The app is on <http://localhost:8000/>. Migrations run on start. Create an
owner in another terminal:

```bash
docker compose exec web python manage.py createsuperuser
```

Load demo data the same way, with `python manage.py seed_demo`.

> The compose file runs with `DEBUG=False`, so static files are served from
> the image and pages behave as they will in production.

## Everyday commands

| Command | What it does |
| --- | --- |
| `make run` | Development server on port 8000 |
| `make test` | The test suite |
| `make coverage` | Tests with a coverage report |
| `make lint` | Ruff lint and format check |
| `make format` | Apply formatting and safe lint fixes |
| `make check` | Django system checks, migration drift and the deployment audit |
| `make invoices ARGS="--dry-run"` | Preview this month's invoices from the command line |
| `make clean` | Remove caches and build output |
| `make help` | Every target |

## Troubleshooting

**`UndefinedValueError: SECRET_KEY not found`** or **"The SECRET_KEY setting
must not be empty"** — the app refuses to start without one. Check `.env`
exists in the project root and `SECRET_KEY=` has a value.

**`SyntaxError` on start** — the virtualenv was made with an older Python.
Delete `venv/` and run `make install` again with 3.14 on your `PATH`.

**Pages have no styling with `DEBUG=False`** — static files are only served
after they are collected: `venv/bin/python manage.py collectstatic`.

**`DisallowedHost`** — add the host you are browsing to `ALLOWED_HOSTS`.

**"CSRF verification failed" when signing in** — with `DEBUG=False`, add the
full origin, scheme included, to `CSRF_TRUSTED_ORIGINS`
(e.g. `http://localhost:8000`).

**Locked out after failed sign-ins** — the lockout lasts
`LOGIN_FAILURE_TIMEOUT` seconds (15 minutes by default). Restarting the dev
server also clears it, since the local cache lives in memory.
