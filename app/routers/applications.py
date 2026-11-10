from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import get_db
from app.dependencies import get_template_context, set_flash
from app.models.audit import AuditEvent
from app.models.decisions import Decision
from app.models.enums import ApplicationStage, AppRole, DecisionOutcome, Grade, InterviewType
from app.models.sell_plans import SellPlan
from app.models.users import User
from app.routers._common import load_application
from app.services import gates, permissions, visibility
from app.services.ai.client import AIUnavailableError
from app.services.ai.features import peek_decision_summary, summarize_decision
from app.services.audit import log_event
from app.services.workflow import WorkflowError, advance_application

router = APIRouter(prefix="/applications", tags=["applications"])
templates = Jinja2Templates(directory="app/templates")


def _ratings_matrix(application) -> list[dict]:
    """Rows of {interview, ratings_by_item_id, can_view} for the ratings matrix."""
    rated_interviews = [
        i for i in application.interviews if i.interview_type.value in ("focused", "demo_lesson")
    ]
    return rated_interviews


def _ratings_text(application) -> str:
    lines = []
    for interview in _ratings_matrix(application):
        for rating in interview.ratings:
            lines.append(f"{rating.scorecard_item.title}: grade {rating.grade.value} -- {rating.evidence}")
    return "\n".join(lines) or "No ratings recorded yet."


def _references_text(application) -> str:
    lines = [
        f"{r.referee_name} ({r.referee_relationship.value}): {r.notes}"
        for r in application.references
        if r.status.value == "completed" and r.notes
    ]
    return "\n".join(lines) or "No completed references yet."


@router.get("/{application_id}")
def application_detail(application_id: int, context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    application = load_application(db, application_id)
    current_user = context["current_user"]

    gate_result = None
    next_stage = gates.NEXT_STAGE.get(application.stage)
    if next_stage is not None:
        gate_result = gates.check_gate(application, next_stage)

    rated_interviews = _ratings_matrix(application)
    ratings_visibility = {i.id: visibility.can_view_ratings(current_user, i) for i in rated_interviews}
    interviewers = db.scalars(select(User).where(User.app_role == AppRole.interviewer).order_by(User.name)).all()

    ai_decision_summary = None
    if settings.AI_ENABLED and application.stage == ApplicationStage.decision:
        ai_decision_summary = peek_decision_summary(db, _ratings_text(application), _references_text(application))

    return templates.TemplateResponse(
        context["request"],
        "applications/detail.html",
        {
            **context,
            "application": application,
            "opening": application.opening,
            "gate_result": gate_result,
            "next_stage": next_stage,
            "can_reject_or_withdraw": permissions.can_reject_or_withdraw(current_user, application.opening),
            "can_override": permissions.can_override_gate(current_user),
            "can_assign_interviewer": permissions.can_assign_interviewer(current_user, application.opening),
            "can_manage_references": permissions.can_manage_references(current_user),
            "can_name_reference": permissions.can_name_reference(current_user, application),
            "can_manage_safeguarding": permissions.can_manage_safeguarding(current_user),
            "can_record_decision": permissions.can_record_decision(current_user, application.opening),
            "can_record_sell_plan": permissions.can_record_sell_plan(current_user, application.opening),
            "rated_interviews": rated_interviews,
            "ratings_visibility": ratings_visibility,
            "interviewers": interviewers,
            "interview_types": list(InterviewType),
            "ai_enabled": settings.AI_ENABLED,
            "ai_decision_summary": ai_decision_summary,
        },
    )


@router.post("/{application_id}/advance")
def advance(application_id: int, context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    application = load_application(db, application_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/applications/{application_id}", status_code=303)
    target_stage = gates.NEXT_STAGE.get(application.stage)
    if target_stage is None:
        set_flash(response, "error", "There is no next stage for this application.")
        return response
    try:
        result = advance_application(db, application, current_user, target_stage)
        db.commit()
        if result.allowed:
            set_flash(response, "success", f"Moved to {target_stage.value.replace('_', ' ')}.")
        else:
            set_flash(response, "error", "Not ready to advance yet. See the reasons below.")
    except WorkflowError as exc:
        db.rollback()
        set_flash(response, "error", str(exc))
    return response


@router.post("/{application_id}/override")
def override(
    application_id: int,
    override_reason: str = Form(...),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    application = load_application(db, application_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/applications/{application_id}", status_code=303)
    target_stage = gates.NEXT_STAGE.get(application.stage)
    if target_stage is None:
        set_flash(response, "error", "There is no next stage for this application.")
        return response
    try:
        advance_application(db, application, current_user, target_stage, override_reason=override_reason)
        db.commit()
        set_flash(response, "success", f"Overridden into {target_stage.value.replace('_', ' ')}.")
    except WorkflowError as exc:
        db.rollback()
        set_flash(response, "error", str(exc))
    return response


@router.post("/{application_id}/reject")
def reject(
    application_id: int,
    reason: str = Form(...),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    application = load_application(db, application_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/applications/{application_id}", status_code=303)
    try:
        advance_application(db, application, current_user, ApplicationStage.rejected, reason=reason)
        db.commit()
        set_flash(response, "success", "Application rejected.")
    except WorkflowError as exc:
        db.rollback()
        set_flash(response, "error", str(exc))
    return response


@router.post("/{application_id}/withdraw")
def withdraw(
    application_id: int,
    reason: str = Form(...),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    application = load_application(db, application_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/applications/{application_id}", status_code=303)
    try:
        advance_application(db, application, current_user, ApplicationStage.withdrawn, reason=reason)
        db.commit()
        set_flash(response, "success", "Application withdrawn.")
    except WorkflowError as exc:
        db.rollback()
        set_flash(response, "error", str(exc))
    return response


@router.post("/{application_id}/ai/decision-summary")
def ai_decision_summary_route(application_id: int, context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    application = load_application(db, application_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/applications/{application_id}", status_code=303)
    if not settings.AI_ENABLED:
        set_flash(response, "error", "AI is disabled.")
        return response
    if not permissions.can_record_decision(current_user, application.opening):
        raise HTTPException(status_code=403, detail="You cannot use this here.")

    try:
        result = summarize_decision(db, _ratings_text(application), _references_text(application))
    except AIUnavailableError as exc:
        db.rollback()
        set_flash(response, "error", str(exc))
        return response

    log_event(
        db, current_user, "ai.decision_summary", "Application", application.id,
        details={"provider": result.provider, "model": result.model, "cached": result.cached},
    )
    db.commit()
    set_flash(response, "success", "AI draft: review before use.")
    return response


@router.post("/{application_id}/decision")
def record_decision(
    application_id: int,
    outcome: str = Form(...),
    overall_grade: str = Form(...),
    rationale: str = Form(...),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    application = load_application(db, application_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/applications/{application_id}", status_code=303)
    if not permissions.can_record_decision(current_user, application.opening):
        raise HTTPException(status_code=403, detail="You cannot record a decision for this opening.")
    if application.stage != ApplicationStage.decision:
        set_flash(response, "error", "The application is not at the decision stage yet.")
        return response
    if not rationale.strip():
        set_flash(response, "error", "A rationale is required.")
        return response

    if application.decision is None:
        decision = Decision(
            application=application,
            outcome=DecisionOutcome(outcome),
            overall_grade=Grade(overall_grade),
            rationale=rationale.strip(),
            decided_by_id=current_user.id,
            decided_at=datetime.now(timezone.utc),
        )
        db.add(decision)
        application.decision = decision
        db.flush()
        log_event(db, current_user, "decision.record", "Decision", application.decision.id, details={"outcome": outcome})
    else:
        application.decision.outcome = DecisionOutcome(outcome)
        application.decision.overall_grade = Grade(overall_grade)
        application.decision.rationale = rationale.strip()
        log_event(db, current_user, "decision.edit", "Decision", application.decision.id, details={"outcome": outcome})
    db.commit()
    set_flash(response, "success", "Decision recorded.")
    return response


@router.post("/{application_id}/sell-plan")
def record_sell_plan(
    application_id: int,
    fit: str = Form(""),
    family: str = Form(""),
    freedom: str = Form(""),
    fortune: str = Form(""),
    fun: str = Form(""),
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    application = load_application(db, application_id)
    current_user = context["current_user"]
    response = RedirectResponse(url=f"/applications/{application_id}", status_code=303)
    if not permissions.can_record_sell_plan(current_user, application.opening):
        raise HTTPException(status_code=403, detail="You cannot record a sell plan for this opening.")

    fields = {"fit": fit.strip() or None, "family": family.strip() or None, "freedom": freedom.strip() or None,
              "fortune": fortune.strip() or None, "fun": fun.strip() or None}
    if application.sell_plan is None:
        sell_plan = SellPlan(application=application, **fields)
        db.add(sell_plan)
        application.sell_plan = sell_plan
        db.flush()
        log_event(db, current_user, "sell_plan.record", "SellPlan", application.sell_plan.id)
    else:
        for key, value in fields.items():
            setattr(application.sell_plan, key, value)
        log_event(db, current_user, "sell_plan.edit", "SellPlan", application.sell_plan.id)
    db.commit()
    set_flash(response, "success", "Sell plan saved.")
    return response


def _collect_audit_trail(db: Session, application) -> list[AuditEvent]:
    pairs = [("Application", application.id)]
    pairs += [("Interview", i.id) for i in application.interviews]
    pairs += [("Reference", r.id) for r in application.references]
    pairs += [("SafeguardingCheck", c.id) for c in application.safeguarding_checks]
    if application.decision:
        pairs.append(("Decision", application.decision.id))
    if application.sell_plan:
        pairs.append(("SellPlan", application.sell_plan.id))

    conditions = [(AuditEvent.entity_type == t) & (AuditEvent.entity_id == i) for t, i in pairs]
    return db.scalars(
        select(AuditEvent)
        .where(or_(*conditions))
        .options(selectinload(AuditEvent.actor))
        .order_by(AuditEvent.created_at)
    ).all()


@router.get("/{application_id}/record")
def decision_record(application_id: int, context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    application = load_application(db, application_id)
    audit_trail = _collect_audit_trail(db, application)
    return templates.TemplateResponse(
        context["request"],
        "applications/decision_record.html",
        {**context, "application": application, "opening": application.opening, "audit_trail": audit_trail},
    )
