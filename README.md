# Rubric

*Every hire, one standard.*

A hiring platform for a private K-12 school, built around "Who: The A Method
for Hiring": Scorecard, Source, Select, Sell. Rubric enforces stage gates so
no one skips straight to a gut-feel decision; a chairman can override a gate
for good reason, but only with a reason that is written to a permanent audit
trail. AI only drafts, structures, and flags gaps -- it never scores, rates,
or ranks candidates, and the app works fully with AI disabled.

See `docs/architecture.md` for a component diagram and `docs/overview.md`
for the one-page pitch.

## Stack

- Python 3.11+, FastAPI, server-rendered Jinja2 templates + HTMX (no React,
  no separate frontend build)
- Tailwind CSS (play CDN) and HTMX loaded from CDN with pinned versions
- PostgreSQL via SQLAlchemy 2.0 typed ORM (`Mapped[...]`) with psycopg 3;
  Alembic for migrations
- Settings via pydantic-settings, read from a `.env` file
- LLM calls via the `openai` Python client pointed at OpenAI-compatible
  endpoints: Groq primary, Google Gemini fallback
- One deployable service: FastAPI serves the templates and static files

## Local setup

1. Create a virtual environment and install dependencies (add `pytest` as a
   dev dependency with `requirements-dev.txt`):

   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements-dev.txt
   ```

2. Copy `.env.example` to `.env` and fill in `DATABASE_URL` at minimum (a
   free [Neon](https://neon.tech) Postgres project works well -- see
   "Database connection" below for the exact URL format):

   ```
   copy .env.example .env
   ```

3. Apply migrations:

   ```
   alembic upgrade head
   ```

4. Seed realistic demo data (safe to rerun -- it wipes and reseeds):

   ```
   python scripts/seed.py
   ```

5. Run the app:

   ```
   uvicorn app.main:app --reload
   ```

6. Visit http://127.0.0.1:8000/ -- the home page is a 5-step guided tour of
   the seeded demo. A chairman can also reset the demo data from there at
   any time (`/demo/reset`).

### Demo mode vs. normal mode

Rubric has two ways to become "the current user":

- **Demo mode** (the default): the top-bar role switcher freely impersonates
  any seeded user, no password needed. This is what the home page's tour
  uses, and what most reviewers will want for exploring the app quickly.
- **Normal mode**: a real `/login` with email + password. Every seeded user
  shares the same demo password, **`rubric-demo`** (printed again each time
  `scripts/seed.py` runs); try e.g. `sunita.iyer@rubric.school` (principal) or
  `rohan.kapoor@rubric.school` (interviewer). Logging in replaces the role
  switcher with your own name and a "Log out" button, drops you straight on
  your own panel (dashboard / my-interviews / openings, depending on role),
  and every permission check (what you can see, what you can act on) is
  enforced exactly as it is in demo mode -- normal mode doesn't add any new
  rules, it just removes the ability to freely become someone else.

## Running tests

```
pytest
```

All tests run against in-memory model objects or a mocked AI client -- no
database or network access is required to run the suite.

To evaluate the AI evidence-mapping feature against 3 hand-labelled samples
(requires `AI_ENABLED=true` and a provider key configured):

```
python scripts/eval_evidence.py
```

## Database connection

Rubric uses SQLAlchemy's psycopg 3 dialect, which needs the `+psycopg`
suffix in the URL scheme. A connection string copied from most Postgres
dashboards (Neon included) uses the bare `postgresql://` scheme -- change it
to `postgresql+psycopg://`. Neon also requires SSL; keep `sslmode=require`
(and `channel_binding=require`, which Neon adds by default) in the query
string:

```
DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>/<database>?sslmode=require&channel_binding=require
```

## Environment variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | yes | — | Must use `postgresql+psycopg://`; see above. |
| `SECRET_KEY` | no | a dev-only placeholder | Signs the normal-mode login session cookie. Set a real random value (`python -c "import secrets; print(secrets.token_hex(32))"`) in any shared or deployed environment. |
| `AI_ENABLED` | no | `false` | The app is fully usable with this `false`; AI buttons simply don't appear. |
| `GROQ_API_KEY` | no (unless AI enabled) | — | Omit to skip Groq and fall through to Gemini. |
| `GROQ_MODEL` | no | `openai/gpt-oss-20b` | Any current Groq chat model that supports JSON mode. |
| `GEMINI_API_KEY` | no (unless AI enabled) | — | Omit to skip Gemini. |
| `GEMINI_MODEL` | no | `gemini-2.5-flash` | Any current Gemini model exposed on its OpenAI-compatible endpoint. |

If both provider keys are omitted while `AI_ENABLED=true`, AI calls fail
soft with "AI is unavailable right now. Please continue manually." --
nothing else in the app is affected.

## Deploying to Render

`render.yaml` defines one free-tier web service in the Singapore region.

1. Push this repository to GitHub (or GitLab).
2. In the Render dashboard, choose **New > Blueprint** and point it at the
   repository. Render reads `render.yaml` and proposes the `rubric` service.
3. Before the first deploy, Render will prompt for every env var marked
   `sync: false` in `render.yaml`: `DATABASE_URL`, `GROQ_API_KEY`,
   `GEMINI_API_KEY`. Paste in your Neon connection string (with
   `+psycopg` and `sslmode=require`, as above) and your provider keys (or
   leave the AI keys blank and keep `AI_ENABLED=false`, which is the
   blueprint's default).
4. Deploy. The build step runs `pip install -r requirements.txt`; the start
   step runs `alembic upgrade head` (applying any pending migrations) and
   then starts `uvicorn` bound to Render's `$PORT`. Render polls
   `/health` to confirm the service is up.
5. Once live, run the seed script once against the production database from
   a Render shell (or locally with `DATABASE_URL` pointed at it) if you want
   the demo data there too: `python scripts/seed.py`. This is destructive
   (it wipes every table first) -- only run it against a database you
   intend to reset.

This repository has not been deployed as part of this submission; the steps
above describe how to do so.
