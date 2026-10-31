# Solar Installation Management System

Operational platform for a rooftop solar company: enquiries, surveys,
quotations, orders, inventory with serial traceability, installation,
warranties, repairs, subsidies and reporting.

Scope and technical decisions are in [spec.md](spec.md). Decisions and
progress are in [decisions.md](decisions.md). Working practices,
permissions and coding standards are in `rules.md`, which is not in the
repository — ask Aditya for a copy.

## Stack

Django 5.2 · DRF 3.16 · PostgreSQL 16 · React 19 · TypeScript 5 ·
Vite 7 · Python 3.12 · Node 22+

## First-time setup

You need Python 3.12, Node 22 or newer, and PostgreSQL 16 installed
locally. Everyone runs their own database; there is no shared server.

### 1. PostgreSQL

Install PostgreSQL 16 and **write down the superuser password you set
during installation** — recovering it later means editing `pg_hba.conf`
as administrator.

Create the application role and database. Open **SQL Shell (psql)** from
the Start menu, press Enter through the four prompts, enter your
superuser password, then run:

```sql
CREATE ROLE solar_app LOGIN PASSWORD 'pick-your-own';
CREATE DATABASE solar_db OWNER solar_app ENCODING 'UTF8';
```

The password is yours alone — it only has to match your own `.env`.

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

cp .env.example .env
```

Edit `.env`:

- `POSTGRES_PASSWORD` — the password you chose above, no quotes.
- `DJANGO_SECRET_KEY` — generate one:
  `python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"`

Then:

```bash
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py createsuperuser
.venv/Scripts/python.exe manage.py runserver
```

API on http://127.0.0.1:8000, admin at `/admin`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

App on http://localhost:5173. Vite proxies `/api` and `/admin` to the
Django server, so run both.

## Daily use

| Task | Command |
|---|---|
| Run backend | `cd backend && .venv/Scripts/python.exe manage.py runserver` |
| Run frontend | `cd frontend && npm run dev` |
| New migration | `manage.py makemigrations <app>` then `manage.py migrate` |
| Backend tests | `manage.py test` |
| Typecheck | `cd frontend && npx tsc --noEmit` |
| Production build | `cd frontend && npm run build` |

After pulling, re-run `pip install -r requirements.txt`, `npm install`
and `manage.py migrate` if any of those changed.

## Things that will bite you

- **Never commit `.env`.** It is gitignored. Credentials differ per
  machine; `.env.example` is the shared template.
- **Migrations are shared.** Pull before creating one. If two people
  generate migrations against the same app in parallel, the numbering
  collides and someone has to merge them by hand.
- **The custom user model is `accounts.User`.** Reference it via
  `settings.AUTH_USER_MODEL`, never `django.contrib.auth.models.User`.
- **Money and measured quantities use `Decimal`,** never `float`. See
  spec.md section 6.
- **Timestamps are stored in UTC** and displayed in Asia/Kolkata. The
  time something happened and the time it was recorded are separate
  fields.

## Repository layout

```
backend/
  config/      settings, root urls, wsgi
  apps/        one package per feature area
  .env         local only, never committed
frontend/
  src/         React application
spec.md        locked scope and technical baseline
decisions.md   decision register and progress
```

## How we work

One spec feature (F01–F20 in spec.md section 7) is the unit of work,
built as a vertical slice through database, backend, UI and tests. Two
or three commits per feature, each prefixed with the feature ID:

```
F07 backend: orders, payment recording and dispatch gating
F07 frontend: order detail, payment entry and balance display
```

Full details, including the permission matrix and commit rules, are in
`rules.md`.
