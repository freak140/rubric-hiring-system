from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import get_template_context
from app.models.applications import Application
from app.models.audit import AuditEvent
from app.models.enums import ApplicationStage
from app.models.interviews import Interview, Rating
from app.models.openings import RoleOpening
from app.models.references import Reference
from app.models.safeguarding import SafeguardingCheck
from app.models.scorecards import Scorecard
from app.models.users import User
from app.services import gates, permissions
from app.services.audit import events_for_openings

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")

STALE_AFTER_DAYS = 14


def _last_activity(application: Application) -> datetime:
    timestamps = [application.updated_at]
    timestamps += [i.updated_at for i in application.interviews]
    timestamps += [r.updated_at for r in application.references]
    timestamps += [c.updated_at for c in application.safeguarding_checks]
    if application.decision:
        timestamps.append(application.decision.updated_at)
    if application.sell_plan:
        timestamps.append(application.sell_plan.updated_at)
    return max(timestamps)


def _describe_event(event: AuditEvent) -> str:
    actor = event.actor.name if event.actor else "System"
    details = event.details or {}
    action = event.action

    if action == "application.advance":
        to_stage = (details.get("to_stage") or "?").replace("_", " ")
        return f"{actor} advanced the application to {to_stage}" + (" (override)." if event.is_override else ".")
    if action in ("application.rejected", "application.withdrawn"):
        verb = "rejected" if action == "application.rejected" else "withdrew"
        reason = details.get("reason", "")
        return f"{actor} {verb} the application" + (f": {reason}" if reason else ".")
    if action == "application.create":
        return f"{actor} added a new candidate."
    if action == "interview.assign":
        itype = (details.get("interview_type") or "").replace("_", " ")
        return f"{actor} assigned a {itype} interview."
    if action == "interview.complete":
        outcome = details.get("outcome")
        return f"{actor} completed an interview" + (f" (outcome: {outcome})" if outcome else "") + "."
    if action == "interview.release":
        reason = details.get("reason", "")
        return f"{actor} released an interviewer" + (f": {reason}" if reason else ".")
    if action == "reference.add":
        name = details.get("referee_name", "")
        return f"{actor} named a reference" + (f": {name}" if name else ".")
    if action == "reference.complete":
        return f"{actor} completed a reference check."
    if action == "safeguarding.update":
        return f"{actor} marked a safeguarding check {details.get('status', '')}."
    if action == "safeguarding.create_defaults":
        return "Safeguarding checklist created automatically."
    if action in ("decision.record", "decision.edit"):
        return f"{actor} recorded a decision: {details.get('outcome', '')}."
    if action in ("sell_plan.record", "sell_plan.edit"):
        return f"{actor} recorded an offer plan."
    if action == "scorecard.approve":
        return f"{actor} approved the scorecard."
    if action in ("scorecard.create", "scorecard.edit_mission"):
        return f"{actor} updated the scorecard mission."
    if action == "scorecard_item.add":
        return f"{actor} added a scorecard item" + (f": {details.get('title', '')}" if details.get("title") else ".")
    if action.startswith("ai."):
        return f"{actor} generated an AI draft ({action.split('.', 1)[1].replace('_', ' ')})."
    if action == "opening.create":
        return f"{actor} created this opening."
    if action == "opening.status_change":
        return f"{actor} changed the opening status to {details.get('to', '?')}."
    return f"{actor}: {action.replace('.', ' ').replace('_', ' ')}."


def _event_url(event: AuditEvent) -> str | None:
    if event.entity_type == "Application":
        return f"/applications/{event.entity_id}"
    if event.entity_type == "Interview":
        return f"/interviews/{event.entity_id}"
    return None


def _chairman_dashboard(context: dict, db: Session):
    openings = db.scalars(
        select(RoleOpening).options(
            selectinload(RoleOpening.hiring_manager),
            selectinload(RoleOpening.applications).selectinload(Application.candidate),
            selectinload(RoleOpening.applications).selectinload(Application.interviews),
            selectinload(RoleOpening.applications).selectinload(Application.references),
            selectinload(RoleOpening.applications).selectinload(Application.safeguarding_checks),
            selectinload(RoleOpening.applications).selectinload(Application.decision),
            selectinload(RoleOpening.applications).selectinload(Application.sell_plan),
        )
    ).all()

    opening_rows = []
    all_applications: list[Application] = []
    for opening in openings:
        stage_counts: dict[str, int] = {}
        for application in opening.applications:
            stage_counts[application.stage.value] = stage_counts.get(application.stage.value, 0) + 1
            all_applications.append(application)
        opening_rows.append({"opening": opening, "stage_counts": stage_counts, "total": len(opening.applications)})

    hired_applications = [a for a in all_applications if a.stage == ApplicationStage.hired]
    hires_to_date = len(hired_applications)

    hired_at_by_app: dict[int, datetime] = {}
    if hired_applications:
        hired_ids = [a.id for a in hired_applications]
        hire_events = db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == "Application",
                AuditEvent.entity_id.in_(hired_ids),
                AuditEvent.action == "application.advance",
            )
            .order_by(AuditEvent.created_at)
        ).all()
        for event in hire_events:
            if (event.details or {}).get("to_stage") == "hired":
                hired_at_by_app[event.entity_id] = event.created_at

    hire_days: list[float] = []
    recent_hires = []
    for application in hired_applications:
        hired_at = hired_at_by_app.get(application.id)
        if hired_at:
            hire_days.append((hired_at - application.opening.created_at).total_seconds() / 86400)
        recent_hires.append({"application": application, "hired_at": hired_at})
    recent_hires.sort(key=lambda row: row["hired_at"] or row["application"].updated_at, reverse=True)

    avg_days_to_hire = round(sum(hire_days) / len(hire_days), 1) if hire_days else None

    active_stage_order = ["sourced", "screening", "who_interview", "focused", "references", "decision", "offer"]
    in_progress = [
        a
        for a in all_applications
        if a.stage not in (ApplicationStage.hired, ApplicationStage.rejected, ApplicationStage.withdrawn)
    ]
    in_progress_rows = [
        {"application": a, "last_activity": _last_activity(a)} for a in in_progress
    ]
    in_progress_rows.sort(
        key=lambda row: (row["application"].opening.title, active_stage_order.index(row["application"].stage.value))
    )

    overrides = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.is_override.is_(True))
        .options(selectinload(AuditEvent.actor))
        .order_by(AuditEvent.created_at.desc())
    ).all()

    released_interviews = db.scalars(
        select(Interview)
        .where(Interview.release_reason.is_not(None))
        .options(
            selectinload(Interview.interviewer),
            selectinload(Interview.application).selectinload(Application.candidate),
            selectinload(Interview.application).selectinload(Application.opening),
        )
        .order_by(Interview.updated_at.desc())
    ).all()

    cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_AFTER_DAYS)
    stale_applications = [row for row in in_progress_rows if row["last_activity"] < cutoff]
    stale_applications.sort(key=lambda row: row["last_activity"])

    return templates.TemplateResponse(
        context["request"],
        "dashboard/index.html",
        {
            **context,
            "opening_rows": opening_rows,
            "hires_to_date": hires_to_date,
            "avg_days_to_hire": avg_days_to_hire,
            "recent_hires": recent_hires,
            "in_progress_rows": in_progress_rows,
            "overrides": overrides,
            "released_interviews": released_interviews,
            "stale_applications": stale_applications,
            "stale_after_days": STALE_AFTER_DAYS,
        },
    )


def _principal_dashboard(current_user: User, context: dict, db: Session):
    openings = db.scalars(
        select(RoleOpening)
        .where(RoleOpening.hiring_manager_id == current_user.id)
        .options(
            selectinload(RoleOpening.scorecard).selectinload(Scorecard.items),
            selectinload(RoleOpening.applications).selectinload(Application.candidate),
            selectinload(RoleOpening.applications)
            .selectinload(Application.interviews)
            .selectinload(Interview.ratings)
            .selectinload(Rating.scorecard_item),
            selectinload(RoleOpening.applications).selectinload(Application.interviews).selectinload(Interview.interviewer),
            selectinload(RoleOpening.applications).selectinload(Application.references),
            selectinload(RoleOpening.applications).selectinload(Application.safeguarding_checks),
            selectinload(RoleOpening.applications).selectinload(Application.decision),
        )
        .order_by(RoleOpening.title)
    ).all()

    opening_rows = []
    needs_attention = []
    interview_rows = []
    for opening in openings:
        stage_counts: dict[str, int] = {}
        for application in opening.applications:
            stage_counts[application.stage.value] = stage_counts.get(application.stage.value, 0) + 1
            for interview in application.interviews:
                interview_rows.append({"interview": interview, "application": application, "opening": opening})
            if application.stage in (ApplicationStage.hired, ApplicationStage.rejected, ApplicationStage.withdrawn):
                continue
            next_stage = gates.NEXT_STAGE.get(application.stage)
            if next_stage is None:
                continue
            result = gates.check_gate(application, next_stage)
            if not result.allowed:
                needs_attention.append(
                    {"application": application, "opening": opening, "next_stage": next_stage, "reasons": result.reasons}
                )
        opening_rows.append({"opening": opening, "stage_counts": stage_counts, "total": len(opening.applications)})

    # Pending (still-assigned) interviews first, most recently touched within each group.
    interview_rows.sort(key=lambda row: row["interview"].updated_at, reverse=True)
    interview_rows.sort(key=lambda row: row["interview"].status.value != "assigned")

    recent_events = events_for_openings(db, [o.id for o in openings], limit=20)
    recent_activity = [
        {"event": event, "description": _describe_event(event), "url": _event_url(event)} for event in recent_events
    ]

    return templates.TemplateResponse(
        context["request"],
        "dashboard/principal.html",
        {
            **context,
            "opening_rows": opening_rows,
            "needs_attention": needs_attention,
            "interview_rows": interview_rows,
            "recent_activity": recent_activity,
        },
    )


@router.get("/dashboard")
def dashboard(context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    current_user = context["current_user"]
    if permissions.can_view_dashboard(current_user):
        return _chairman_dashboard(context, db)
    if permissions.can_view_principal_dashboard(current_user):
        return _principal_dashboard(current_user, context, db)
    raise HTTPException(status_code=403, detail="You don't have a dashboard.")


@router.get("/audit-log")
def audit_log(
    opening_id: int | None = None,
    user_id: int | None = None,
    action: str | None = None,
    overrides_only: bool = False,
    context: dict = Depends(get_template_context),
    db: Session = Depends(get_db),
):
    current_user = context["current_user"]
    if not permissions.can_view_audit_log(current_user):
        raise HTTPException(status_code=403, detail="Only the chairman can view this page.")

    query = select(AuditEvent).options(selectinload(AuditEvent.actor)).order_by(AuditEvent.created_at.desc())
    if user_id:
        query = query.where(AuditEvent.actor_id == user_id)
    if action:
        query = query.where(AuditEvent.action == action)
    if overrides_only:
        query = query.where(AuditEvent.is_override.is_(True))
    events = db.scalars(query.limit(500)).all()

    if opening_id:
        opening_app_ids = set(db.scalars(select(Application.id).where(Application.opening_id == opening_id)))
        opening_interview_ids = set(
            db.scalars(select(Interview.id).join(Application).where(Application.opening_id == opening_id))
        )
        opening_reference_ids = set(
            db.scalars(select(Reference.id).join(Application).where(Application.opening_id == opening_id))
        )
        opening_check_ids = set(
            db.scalars(
                select(SafeguardingCheck.id).join(Application).where(Application.opening_id == opening_id)
            )
        )

        def matches_opening(event: AuditEvent) -> bool:
            if event.entity_type == "RoleOpening" and event.entity_id == opening_id:
                return True
            if event.entity_type == "Application" and event.entity_id in opening_app_ids:
                return True
            if event.entity_type == "Interview" and event.entity_id in opening_interview_ids:
                return True
            if event.entity_type == "Reference" and event.entity_id in opening_reference_ids:
                return True
            if event.entity_type == "SafeguardingCheck" and event.entity_id in opening_check_ids:
                return True
            return False

        events = [e for e in events if matches_opening(e)]

    openings = db.scalars(select(RoleOpening).order_by(RoleOpening.title)).all()
    users = db.scalars(select(User).order_by(User.name)).all()
    actions = sorted({row[0] for row in db.execute(select(AuditEvent.action).distinct())})

    return templates.TemplateResponse(
        context["request"],
        "dashboard/audit_log.html",
        {
            **context,
            "events": events,
            "openings": openings,
            "users": users,
            "actions": actions,
            "selected_opening_id": opening_id,
            "selected_user_id": user_id,
            "selected_action": action,
            "overrides_only": overrides_only,
        },
    )
