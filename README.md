# Rubric

*Every hire, one standard.*

A hiring platform for a K-12 school, built around "Who: The A Method for Hiring"
process: Scorecard, Source, Select, Sell.

## Stack

- Python 3.11+, FastAPI, server-rendered Jinja2 templates + HTMX
- Tailwind CSS (CDN) and HTMX (CDN), no separate frontend build
- PostgreSQL via SQLAlchemy 2.0 (typed ORM) + psycopg 3, migrations via Alembic
- Settings via pydantic-settings, loaded from `.env`

## Setup

1. Create a virtual environment and install dependencies:

   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in values as needed:

   ```
   copy .env.example .env
   ```

3. Run the app:

   ```
   uvicorn app.main:app --reload
   ```

4. Visit http://127.0.0.1:8000/ and http://127.0.0.1:8000/health

## Database migrations (once models exist)

```
alembic revision --autogenerate -m "message"
alembic upgrade head
```
