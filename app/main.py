from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import demo, pages

app = FastAPI(title="Rubric")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(pages.router)
app.include_router(demo.router)
