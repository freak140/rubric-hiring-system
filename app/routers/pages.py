from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.dependencies import CURRENT_USER_COOKIE, get_landing_path, get_template_context

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
def home(context: dict = Depends(get_template_context)):
    if not context["is_demo"]:
        return RedirectResponse(url=get_landing_path(context["current_user"]), status_code=303)

    has_chosen_demo = CURRENT_USER_COOKIE in context["request"].cookies
    if has_chosen_demo:
        return templates.TemplateResponse(context["request"], "home.html", {**context, "app_name": "Rubric"})

    # A genuinely fresh visitor: no demo cookie and no session cookie yet.
    # Ask explicitly rather than silently defaulting them into demo mode.
    return templates.TemplateResponse(context["request"], "landing.html", {**context, "app_name": "Rubric"})


@router.get("/health")
def health():
    return {"status": "ok"}
