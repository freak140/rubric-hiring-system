# Rubric

*Every hire, one standard.*

## Purpose

Rubric is a hiring platform for a private K-12 school that enforces the
"Who: The A Method for Hiring" process: Scorecard, Source, Select, Sell.

## Stack

- Python 3.11+, FastAPI, server-rendered Jinja2 templates + HTMX (no React, no
  separate frontend build)
- Tailwind CSS (play CDN) and HTMX loaded from CDN with pinned versions
- PostgreSQL via SQLAlchemy 2.0 typed ORM (`Mapped[...]`) with psycopg 3;
  Alembic for migrations
- Settings via pydantic-settings, read from a `.env` file
- LLM calls via the `openai` Python client pointed at OpenAI-compatible
  endpoints: Groq primary, Google Gemini fallback
- One deployable service: FastAPI serves the templates and static files

## Rules

- AI never scores, rates, or ranks candidates. It only drafts, structures, and
  flags gaps; humans approve everything.
- The app must work fully with `AI_ENABLED=false`.
- Business rules (stage gates) live in `app/services`, never in routes or
  templates.
- Every state change will be written to an audit log (built later).
- Keep code simple and readable; no extra frameworks or libraries beyond
  those listed above.
- Hiring history is never hard-deleted: `Application -> RoleOpening` and
  `Application -> Candidate` are `ON DELETE RESTRICT`. Deleting an opening or
  a candidate that has applications must fail, not cascade.
