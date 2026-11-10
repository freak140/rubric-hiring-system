from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_template_context, set_flash
from app.models.enums import CheckStatus
from app.models.safeguarding import SafeguardingCheck
from app.services import permissions
from app.services.audit import log_event

router = APIRouter(prefix="/safeguarding", tags=["safeguarding"])


def _load_check(db: Session, check_id: int) -> SafeguardingCheck:
    check = db.get(SafeguardingCheck, check_id)
    if check is None:
        raise HTTPException(status_code=404, detail="Safeguarding check not found.")
    return check


@router.post("/{check_id}")
def update_check(
    check_id: int,
    status: str = Form(...),
    notes: str = Form(""),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    check = _load_check(db, check_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/applications/{check.application_id}", status_code=303)
    if not permissions.can_manage_safeguarding(current_user):
        raise HTTPException(status_code=403, detail="You cannot manage safeguarding checks.")

    check.status = CheckStatus(status)
    check.notes = notes.strip() or None
    check.verified_by_id = current_user.id
    check.verified_at = datetime.now(timezone.utc)
    log_event(db, current_user, "safeguarding.update", "SafeguardingCheck", check.id, details={"status": status})
    db.commit()
    set_flash(response, "success", f"'{check.check_name}' marked {status}.")
    return response
