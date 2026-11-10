from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.dependencies import CURRENT_USER_COOKIE

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/switch-user")
def switch_user(request: Request, user_id: int = Form(...)):
    redirect_to = request.headers.get("referer", "/")
    response = RedirectResponse(url=redirect_to, status_code=303)
    response.set_cookie(CURRENT_USER_COOKIE, str(user_id), httponly=True, samesite="lax")
    return response
