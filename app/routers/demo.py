from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import CURRENT_USER_COOKIE, get_template_context, set_flash
from app.models.enums import AppRole
from app.models.users import User
from app.services import permissions

router = APIRouter(prefix="/demo", tags=["demo"])
templates = Jinja2Templates(directory="app/templates")


@router.post("/enter")
def enter_demo_mode(db: Session = Depends(get_db)):
    """The landing page's "Continue in demo mode" choice: starts as the chairman,
    same as the switcher's own default, just with an explicit first click."""
    chairman = db.scalar(select(User).where(User.app_role == AppRole.chairman).order_by(User.id))
    response = RedirectResponse(url="/", status_code=303)
    if chairman is not None:
        response.set_cookie(CURRENT_USER_COOKIE, str(chairman.id), httponly=True, samesite="lax")
    return response


@router.post("/switch-user")
def switch_user(request: Request, user_id: int = Form(...), next: str = Form("")):
    redirect_to = next or request.headers.get("referer", "/")
    response = RedirectResponse(url=redirect_to, status_code=303)
    response.set_cookie(CURRENT_USER_COOKIE, str(user_id), httponly=True, samesite="lax")
    return response


@router.get("/reset")
def reset_confirm(context: dict = Depends(get_template_context)):
    if not permissions.can_view_dashboard(context["current_user"]):
        raise HTTPException(status_code=403, detail="Only the chairman can reset demo data.")
    return templates.TemplateResponse(context["request"], "demo/reset_confirm.html", context)


@router.post("/reset")
def reset_confirmed(
    confirm: str = Form(""), context: dict = Depends(get_template_context), db: Session = Depends(get_db)
):
    if not permissions.can_view_dashboard(context["current_user"]):
        raise HTTPException(status_code=403, detail="Only the chairman can reset demo data.")

    response = RedirectResponse(url="/", status_code=303)
    if confirm != "yes":
        set_flash(response, "error", "Reset was not confirmed.")
        return response

    # run_seed() opens its own session and TRUNCATEs every table. This request's own
    # session (shared with get_template_context via FastAPI's dependency cache) must be
    # closed first, or its still-open read transaction deadlocks against the TRUNCATE.
    db.close()

    from scripts.seed import run_seed

    run_seed()
    set_flash(response, "success", "Demo data reset to its starting state.")
    return response
