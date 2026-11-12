"""FastAPI-specific request wiring: current user and shared template context.

This is deliberately separate from app/services, which holds business rules
with no framework dependency.

Two ways to become "the current user":
- Demo mode: the `rubric_user_id` cookie, freely set by the role switcher.
  No password involved -- this is the mode used for exploring/demoing Rubric.
- Normal mode: a signed `rubric_session` cookie set by a real /login with a
  password. Whenever a valid session cookie is present, it wins outright and
  the demo role switcher disappears from the UI.
"""

import json

from fastapi import Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.db import get_db
from app.models.enums import AppRole
from app.models.users import User
from app.services.auth import verify_session

CURRENT_USER_COOKIE = "rubric_user_id"
SESSION_COOKIE = "rubric_session"
FLASH_COOKIE = "rubric_flash"

LANDING_PATH_BY_ROLE = {
    AppRole.chairman: "/dashboard",
    AppRole.principal: "/dashboard",
    AppRole.hr: "/openings",
    AppRole.interviewer: "/my-interviews",
}


def get_landing_path(user: User) -> str:
    return LANDING_PATH_BY_ROLE.get(user.app_role, "/openings")


def is_authenticated(rubric_session: str | None = Cookie(default=None)) -> bool:
    return verify_session(rubric_session) is not None


def get_current_user(
    db: Session = Depends(get_db),
    rubric_session: str | None = Cookie(default=None),
    rubric_user_id: str | None = Cookie(default=None, alias=CURRENT_USER_COOKIE),
) -> User:
    session_user_id = verify_session(rubric_session)
    if session_user_id is not None:
        user = db.get(User, session_user_id)
        if user is not None:
            return user

    if rubric_user_id:
        try:
            user = db.get(User, int(rubric_user_id))
        except (TypeError, ValueError):
            user = None
        if user is not None:
            return user

    default_user = db.query(User).filter(User.app_role == AppRole.chairman).order_by(User.id).first()
    if default_user is not None:
        return default_user

    raise HTTPException(status_code=500, detail="No users found. Run scripts/seed.py to create demo users.")


def get_flash(request: Request, response: Response) -> dict | None:
    raw = request.cookies.get(FLASH_COOKIE)
    if not raw:
        return None
    response.delete_cookie(FLASH_COOKIE)
    try:
        return json.loads(raw)
    except ValueError:
        return None


def set_flash(response: RedirectResponse, level: str, message: str) -> None:
    """level is 'success' or 'error'. Read once by get_flash on the next request."""
    response.set_cookie(FLASH_COOKIE, json.dumps({"level": level, "message": message}), max_age=10)


def get_template_context(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    flash: dict | None = Depends(get_flash),
    authenticated: bool = Depends(is_authenticated),
) -> dict:
    all_users = db.query(User).order_by(User.app_role, User.name).all()
    return {
        "request": request,
        "current_user": current_user,
        "all_users": all_users,
        "flash": flash,
        "is_demo": not authenticated,
    }
