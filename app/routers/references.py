from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import get_template_context, set_flash
from app.models.enums import ReferenceStatus
from app.models.references import Reference
from app.routers._common import load_application
from app.services import permissions
from app.services.audit import log_event

router = APIRouter(tags=["references"])
templates = Jinja2Templates(directory="app/templates")

REFERENCE_QUESTIONS = [
    "In what context did you work with the person?",
    "What were their biggest strengths?",
    "What were their biggest areas for improvement back then?",
    "How would you rate their overall performance on a 1-10 scale, and why?",
    "The candidate mentioned they struggled with ___; can you tell me more?",
]


def _load_reference(db: Session, reference_id: int) -> Reference:
    reference = db.get(
        Reference,
        reference_id,
        options=[selectinload(Reference.application)],
    )
    if reference is None:
        raise HTTPException(status_code=404, detail="Reference not found.")
    return reference


@router.post("/applications/{application_id}/references")
def add_reference(
    application_id: int,
    referee_name: str = Form(...),
    referee_relationship: str = Form(...),
    contact: str | None = Form(None),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    application = load_application(db, application_id)
    current_user = context["current_user"]
    redirect_target = f"/applications/{application_id}"
    response = RedirectResponse(url=redirect_target, status_code=303)
    if not permissions.can_name_reference(current_user, application):
        raise HTTPException(status_code=403, detail="You cannot add references for this application.")

    from app.models.enums import RefereeRelationship

    reference = Reference(
        application=application,
        referee_name=referee_name.strip(),
        referee_relationship=RefereeRelationship(referee_relationship),
        contact=(contact or "").strip() or None,
        status=ReferenceStatus.named,
    )
    db.add(reference)
    db.flush()
    log_event(db, current_user, "reference.add", "Reference", reference.id, details={"referee_name": reference.referee_name})
    db.commit()
    set_flash(response, "success", f"Reference '{reference.referee_name}' added.")
    return response


@router.get("/references/{reference_id}")
def reference_form(reference_id: int, context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    reference = _load_reference(db, reference_id)
    current_user = context["current_user"]
    if not permissions.can_manage_references(current_user):
        raise HTTPException(status_code=403, detail="You cannot manage references.")
    return templates.TemplateResponse(
        context["request"],
        "references/interview_form.html",
        {**context, "reference": reference, "questions": REFERENCE_QUESTIONS},
    )


@router.post("/references/{reference_id}")
def submit_reference(
    reference_id: int,
    notes: str = Form(""),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    reference = _load_reference(db, reference_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/applications/{reference.application_id}", status_code=303)
    if not permissions.can_manage_references(current_user):
        raise HTTPException(status_code=403, detail="You cannot manage references.")

    reference.notes = notes.strip() or None
    reference.status = ReferenceStatus.completed
    reference.conducted_by_id = current_user.id
    reference.completed_at = datetime.now(timezone.utc)
    log_event(db, current_user, "reference.complete", "Reference", reference.id)
    db.commit()
    set_flash(response, "success", f"Reference from {reference.referee_name} marked complete.")
    return response
