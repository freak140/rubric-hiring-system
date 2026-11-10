"""FastAPI-specific request wiring: current user and shared template context.

This is deliberately separate from app/services, which holds business rules
with no framework dependency.
"""

import json

from fastapi import Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.db import get_db
from app.models.enums import AppRole
from app.models.users import User

CURRENT_USER_COOKIE = "rubric_user_id"
FLASH_COOKIE = "rubric_flash"


def get_current_user(
    db: Session = Depends(get_db),
    rubric_user_id: str | None = Cookie(default=None, alias=CURRENT_USER_COOKIE),
) -> User:
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
) -> dict:
    all_users = db.query(User).order_by(User.app_role, User.name).all()
    return {"request": request, "current_user": current_user, "all_users": all_users, "flash": flash}
