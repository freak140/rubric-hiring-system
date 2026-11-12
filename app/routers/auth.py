from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import (
    CURRENT_USER_COOKIE,
    SESSION_COOKIE,
    get_landing_path,
    get_template_context,
    is_authenticated,
    set_flash,
)
from app.models.users import User
from app.services.auth import sign_session, verify_password

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")

SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 7  # one week


@router.get("/login")
def login_form(authenticated: bool = Depends(is_authenticated), context: dict = Depends(get_template_context)):
    if authenticated:
        return RedirectResponse(url=get_landing_path(context["current_user"]), status_code=303)
    return templates.TemplateResponse(context["request"], "auth/login.html", context)


@router.post("/login")
def login_submit(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not verify_password(password, user.password_hash):
        response = RedirectResponse(url="/login", status_code=303)
        set_flash(response, "error", "Invalid email or password.")
        return response

    response = RedirectResponse(url=get_landing_path(user), status_code=303)
    response.set_cookie(
        SESSION_COOKIE, sign_session(user.id), httponly=True, samesite="lax", max_age=SESSION_MAX_AGE_SECONDS
    )
    response.delete_cookie(CURRENT_USER_COOKIE)
    set_flash(response, "success", f"Welcome, {user.name}.")
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
