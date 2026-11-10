from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import applications, candidates, dashboard, demo, interviews, openings, pages, references, safeguarding

app = FastAPI(title="Rubric")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(pages.router)
app.include_router(demo.router)
app.include_router(openings.router)
app.include_router(candidates.router)
app.include_router(applications.router)
app.include_router(interviews.router)
app.include_router(references.router)
app.include_router(safeguarding.router)
app.include_router(dashboard.router)
