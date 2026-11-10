from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_template_context, set_flash
from app.models.candidates import Candidate
from app.models.enums import ApplicationStage, CandidateSource
from app.models.openings import RoleOpening
from app.models.applications import Application
from app.services import permissions
from app.services.audit import log_event

router = APIRouter(prefix="/openings/{opening_id}/candidates", tags=["candidates"])
templates = Jinja2Templates(directory="app/templates")


def _load_opening(db: Session, opening_id: int) -> RoleOpening:
    opening = db.get(RoleOpening, opening_id)
    if opening is None:
        raise HTTPException(status_code=404, detail="Opening not found.")
    return opening


@router.get("/new")
def new_candidate_form(opening_id: int, context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    opening = _load_opening(db, opening_id)
    if not permissions.can_add_candidate(context["current_user"]):
        raise HTTPException(status_code=403, detail="You cannot add candidates.")
    return templates.TemplateResponse(
        context["request"],
        "candidates/add_form.html",
        {**context, "opening": opening, "sources": list(CandidateSource)},
    )


@router.post("")
def add_candidate(
    opening_id: int,
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str | None = Form(None),
    source: str = Form(...),
    source_detail: str | None = Form(None),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    opening = _load_opening(db, opening_id)
    current_user = context["current_user"]
    if not permissions.can_add_candidate(current_user):
        raise HTTPException(status_code=403, detail="You cannot add candidates.")

    normalized_email = email.strip().lower()
    candidate = db.scalar(select(Candidate).where(Candidate.email == normalized_email))
    created_candidate = candidate is None
    if candidate is None:
        candidate = Candidate(
            full_name=full_name.strip(),
            email=normalized_email,
            phone=(phone or "").strip() or None,
            source=CandidateSource(source),
            source_detail=(source_detail or "").strip() or None,
        )
        db.add(candidate)
        db.flush()
        log_event(db, current_user, "candidate.create", "Candidate", candidate.id, details={"email": candidate.email})

    response = RedirectResponse(url=f"/openings/{opening_id}", status_code=303)
    existing = db.scalar(
        select(Application).where(Application.candidate_id == candidate.id, Application.opening_id == opening_id)
    )
    if existing is not None:
        db.rollback()
        set_flash(response, "error", f"{candidate.full_name} has already applied to this opening.")
        return response

    application = Application(candidate=candidate, opening=opening, stage=ApplicationStage.sourced)
    db.add(application)
    db.flush()
    log_event(
        db, current_user, "application.create", "Application", application.id,
        details={"candidate_id": candidate.id, "opening_id": opening_id, "reused_candidate": not created_candidate},
    )
    db.commit()
    set_flash(response, "success", f"{candidate.full_name} added to the pipeline.")
    return response
