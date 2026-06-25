# AIECO — AI Carbon Footprint Calculator

A Django web app that estimates the energy use, CO₂ emissions and electricity
cost of AI workloads, with research-backed methodology and an open dataset.
Live at [aieco.uk](https://aieco.uk).

## Features

- **Hardware calculator** — estimate energy/CO₂/cost for a hardware + region +
  workload configuration. The formula runs server-side (`/api/hw-calculate/`),
  not in the browser.
- **Prompt calculator** — estimate emissions for a prompt and save sessions.
- **Personal dashboard** — monthly totals, per-model breakdown, budget tracking.
- **Community forum** — share results, tips and questions.
- **EcoBot** — a chat assistant proxied server-side to Google Gemini.
- **Methodology page** — every assumption and formula, generated from the same
  constants the calculator uses (`calculator/methodology.py`).
- **Open data** — reference tables downloadable as CSV/JSON (CC-BY-4.0).

## Tech stack

- Django 4.2, Python 3.11+ (developed on 3.13)
- PostgreSQL in production (via `dj-database-url`), SQLite locally
- Gunicorn + WhiteNoise for serving
- Deploys on Render (`render.yaml`) or Railway (`railway.json`)

## Local development

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/Scripts/activate   # Windows (Git Bash); use venv/bin/activate on macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create a .env file (gitignored) — see "Environment variables" below
#    At minimum, set DEBUG=True for local development.

# 4. Set up the database and seed reference data
python manage.py migrate
python manage.py seed_data        # carbon regions, hardware, models, etc.
python manage.py create_admin     # creates a superuser (idempotent)

# 5. Run the development server
python manage.py runserver
```

Then open http://127.0.0.1:8000/.

## Environment variables

Set these in a local `.env` file (never committed) and in your host's dashboard
for production:

| Variable         | Required        | Purpose                                              |
|------------------|-----------------|------------------------------------------------------|
| `DEBUG`          | dev only        | `True` locally; defaults to `False` (secure) in prod |
| `SECRET_KEY`     | **prod**        | Django secret key. Must be set in production.        |
| `DATABASE_URL`   | prod            | Postgres connection string; falls back to SQLite.    |
| `GEMINI_API_KEY` | for EcoBot      | Google Gemini key; EcoBot is disabled without it.    |

> **Production note:** `SECRET_KEY` must be set in the host dashboard. Render
> generates one automatically (`render.yaml`); on Railway you must add it
> yourself, otherwise the app falls back to an insecure development key.

## Tests

```bash
python manage.py test
```

## Methodology

Estimates are research-derived, not measured. Key sources: Samsi et al. (2023),
Guidi et al. (2024), Faiz et al. (2024). See the in-app `/methodology` page and
`calculator/methodology.py` for every constant and formula.

## Deployment

- **Build:** `build.sh` installs deps, runs `collectstatic`, `migrate` and
  `seed_data`.
- **Start:** `gunicorn aieco.wsgi`.
- Static files are served by WhiteNoise (`CompressedManifestStaticFilesStorage`).
