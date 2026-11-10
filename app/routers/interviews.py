from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import get_db
from app.dependencies import get_template_context, set_flash
from app.models.applications import Application
from app.models.enums import AppRole, Grade, InterviewStatus, InterviewType, RefereeRelationship, RoleType, ScreeningOutcome
from app.models.interviews import Interview, Rating
from app.models.openings import RoleOpening
from app.models.users import User
from app.routers._common import load_application, load_interview
from app.services import permissions
from app.services.ai.client import AIUnavailableError
from app.services.ai.features import generate_focused_questions, map_evidence, peek_focused_questions
from app.services.audit import log_event
from app.services.workflow import WorkflowError, release_interviewer

router = APIRouter(tags=["interviews"])
templates = Jinja2Templates(directory="app/templates")

WHO_QUESTIONS = [
    "What were you hired to do?",
    "What accomplishments are you most proud of?",
    "What were some low points during that job?",
    "Who were the people you worked with, and how would your boss rate you?",
    "Why did you leave?",
]


@router.post("/applications/{application_id}/interviews")
def assign_interviewer(
    application_id: int,
    interview_type: str = Form(...),
    interviewer_id: int = Form(...),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    application = load_application(db, application_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/applications/{application_id}", status_code=303)
    if not permissions.can_assign_interviewer(current_user, application.opening):
        raise HTTPException(status_code=403, detail="You cannot assign interviewers for this opening.")

    interviewer = db.get(User, interviewer_id)
    if interviewer is None:
        set_flash(response, "error", "Interviewer not found.")
        return response

    interview = Interview(
        application=application,
        interview_type=InterviewType(interview_type),
        interviewer=interviewer,
        interviewer_id=interviewer.id,
        status=InterviewStatus.assigned,
    )
    db.add(interview)
    db.flush()
    log_event(
        db, current_user, "interview.assign", "Interview", interview.id,
        details={"interview_type": interview_type, "interviewer_id": interviewer.id},
    )
    db.commit()
    set_flash(response, "success", f"{interviewer.name} assigned to a {interview_type.replace('_', ' ')} interview.")
    return response


@router.get("/interviews/{interview_id}")
def interview_form(interview_id: int, context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    interview = load_interview(db, interview_id)
    current_user = context["current_user"]
    if not permissions.can_view_interview(current_user, interview):
        raise HTTPException(status_code=403, detail="You cannot view this interview.")

    can_submit = permissions.can_submit_rating(current_user, interview)
    can_release = permissions.can_release_interviewer(current_user, interview.application.opening)

    base_ctx = {
        **context,
        "interview": interview,
        "application": interview.application,
        "can_submit": can_submit,
        "can_release": can_release,
    }

    if interview.interview_type == InterviewType.screening:
        return templates.TemplateResponse(context["request"], "interviews/screening_form.html", base_ctx)
    if interview.interview_type == InterviewType.who:
        return templates.TemplateResponse(
            context["request"], "interviews/who_form.html",
            {
                **base_ctx,
                "questions": WHO_QUESTIONS,
                "relationships": list(RefereeRelationship),
                "can_name_reference": permissions.can_name_reference(current_user, interview.application),
            },
        )
    # focused or demo_lesson
    scorecard = interview.application.opening.scorecard
    items = sorted(scorecard.items, key=lambda i: i.position) if scorecard else []
    existing_ratings = {r.scorecard_item.id: r for r in interview.ratings}
    is_teaching = interview.application.opening.role_type == RoleType.teaching
    ai_questions = peek_focused_questions(db, items, is_teaching) if settings.AI_ENABLED and items else None
    return templates.TemplateResponse(
        context["request"], "interviews/focused_form.html",
        {
            **base_ctx,
            "items": items,
            "existing_ratings": existing_ratings,
            "grades": list(Grade),
            "ai_enabled": settings.AI_ENABLED,
            "ai_questions": ai_questions,
        },
    )


@router.post("/interviews/{interview_id}/screening")
def submit_screening(
    interview_id: int,
    notes: str = Form(""),
    outcome: str = Form(...),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    interview = load_interview(db, interview_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/interviews/{interview_id}", status_code=303)
    if not permissions.can_submit_rating(current_user, interview):
        raise HTTPException(status_code=403, detail="Only the assigned interviewer can submit this form.")

    interview.notes = notes.strip() or None
    interview.screening_outcome = ScreeningOutcome(outcome)
    interview.status = InterviewStatus.completed
    interview.conducted_at = datetime.now(timezone.utc)
    log_event(db, current_user, "interview.complete", "Interview", interview.id, details={"outcome": outcome})
    db.commit()
    set_flash(response, "success", "Screening recorded.")
    return response


@router.post("/interviews/{interview_id}/who")
def submit_who(
    interview_id: int,
    notes: str = Form(""),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    interview = load_interview(db, interview_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/interviews/{interview_id}", status_code=303)
    if not permissions.can_submit_rating(current_user, interview):
        raise HTTPException(status_code=403, detail="Only the assigned interviewer can submit this form.")

    interview.notes = notes.strip() or None
    interview.status = InterviewStatus.completed
    interview.conducted_at = datetime.now(timezone.utc)
    log_event(db, current_user, "interview.complete", "Interview", interview.id)
    db.commit()
    set_flash(response, "success", "Who interview recorded.")
    return response


@router.post("/interviews/{interview_id}/focused")
async def submit_focused(interview_id: int, request: Request, context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    interview = load_interview(db, interview_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/interviews/{interview_id}", status_code=303)
    if not permissions.can_submit_rating(current_user, interview):
        raise HTTPException(status_code=403, detail="Only the assigned interviewer can submit this form.")

    form = await request.form()
    notes = (form.get("notes") or "").strip()
    scorecard = interview.application.opening.scorecard
    items = scorecard.items if scorecard else []

    existing_by_item = {r.scorecard_item.id: r for r in interview.ratings}
    missing = []
    for item in items:
        grade_value = (form.get(f"grade_{item.id}") or "").strip()
        evidence_value = (form.get(f"evidence_{item.id}") or "").strip()
        if not grade_value or not evidence_value:
            missing.append(item.title)
            continue
        rating = existing_by_item.get(item.id)
        if rating is None:
            rating = Rating(interview=interview, scorecard_item=item, grade=Grade(grade_value), evidence=evidence_value)
            db.add(rating)
        else:
            rating.grade = Grade(grade_value)
            rating.evidence = evidence_value

    if missing:
        db.rollback()
        set_flash(response, "error", "A grade and evidence are required for: " + ", ".join(missing))
        return response

    interview.notes = notes or None
    interview.status = InterviewStatus.completed
    interview.conducted_at = datetime.now(timezone.utc)
    log_event(db, current_user, "interview.complete", "Interview", interview.id)
    db.commit()
    set_flash(response, "success", "Ratings submitted.")
    return response


@router.post("/interviews/{interview_id}/ai/focused-questions")
def ai_focused_questions(interview_id: int, context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    interview = load_interview(db, interview_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/interviews/{interview_id}", status_code=303)
    if not settings.AI_ENABLED:
        set_flash(response, "error", "AI is disabled.")
        return response
    if not permissions.can_submit_rating(current_user, interview):
        raise HTTPException(status_code=403, detail="Only the assigned interviewer can use this.")

    scorecard = interview.application.opening.scorecard
    items = sorted(scorecard.items, key=lambda i: i.position) if scorecard else []
    if not items:
        set_flash(response, "error", "The opening has no scorecard items yet.")
        return response

    is_teaching = interview.application.opening.role_type == RoleType.teaching
    try:
        result = generate_focused_questions(db, items, is_teaching)
    except AIUnavailableError as exc:
        db.rollback()
        set_flash(response, "error", str(exc))
        return response

    log_event(
        db, current_user, "ai.focused_questions", "Interview", interview.id,
        details={"provider": result.provider, "model": result.model, "cached": result.cached},
    )
    db.commit()
    set_flash(response, "success", "AI draft: review before use.")
    return response


@router.post("/interviews/{interview_id}/ai/evidence-map")
async def ai_evidence_map(interview_id: int, request: Request, context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    interview = load_interview(db, interview_id)
    current_user = context["current_user"]
    if not permissions.can_submit_rating(current_user, interview):
        raise HTTPException(status_code=403, detail="Only the assigned interviewer can use this.")

    form = await request.form()
    notes = (form.get("notes") or "").strip()
    scorecard = interview.application.opening.scorecard
    items = sorted(scorecard.items, key=lambda i: i.position) if scorecard else []

    error = None
    mapping = None
    if not settings.AI_ENABLED:
        error = "AI is disabled."
    elif not notes:
        error = "Add some interview notes first."
    elif not items:
        error = "The opening has no scorecard items yet."
    else:
        try:
            result = map_evidence(db, notes, items)
            mapping = result.output
            log_event(
                db, current_user, "ai.evidence_map", "Interview", interview.id,
                details={"provider": result.provider, "model": result.model, "cached": result.cached},
            )
            db.commit()
        except AIUnavailableError as exc:
            db.rollback()
            error = str(exc)

    return templates.TemplateResponse(
        context["request"], "interviews/_evidence_panel.html", {**context, "mapping": mapping, "error": error}
    )


@router.post("/interviews/{interview_id}/release")
def release(
    interview_id: int,
    reason: str = Form(...),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    interview = load_interview(db, interview_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/applications/{interview.application_id}", status_code=303)
    try:
        release_interviewer(db, interview, current_user, reason)
        db.commit()
        set_flash(response, "success", "Interviewer released.")
    except WorkflowError as exc:
        db.rollback()
        set_flash(response, "error", str(exc))
    return response


@router.get("/my-interviews")
def my_interviews(context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    current_user = context["current_user"]
    interviews = db.scalars(
        select(Interview)
        .where(Interview.interviewer_id == current_user.id)
        .options(
            selectinload(Interview.application).selectinload(Application.candidate),
            selectinload(Interview.application).selectinload(Application.opening).selectinload(RoleOpening.scorecard),
        )
        .order_by(Interview.status, Interview.id.desc())
    ).all()
    return templates.TemplateResponse(
        context["request"], "interviews/my_interviews.html", {**context, "interviews": interviews}
    )
