from fastapi import APIRouter, Depends
from fastapi.templating import Jinja2Templates

from app.dependencies import get_template_context

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
def home(context: dict = Depends(get_template_context)):
    return templates.TemplateResponse(context["request"], "home.html", {**context, "app_name": "Rubric"})


@router.get("/health")
def health():
    return {"status": "ok"}
