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
from app.models.interviews import Interview
from app.models.openings import RoleOpening
from app.models.references import Reference
from app.models.safeguarding import SafeguardingCheck
from app.models.users import User
from app.services import permissions

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")

STALE_AFTER_DAYS = 14


def _require_chairman(current_user) -> None:
    if not permissions.can_view_dashboard(current_user):
        raise HTTPException(status_code=403, detail="Only the chairman can view this page.")


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


@router.get("/dashboard")
def dashboard(context: dict = Depends(get_template_context), db: Session = Depends(get_db)):
    current_user = context["current_user"]
    _require_chairman(current_user)

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

    hire_days: list[float] = []
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
        hired_at_by_app: dict[int, datetime] = {}
        for event in hire_events:
            if (event.details or {}).get("to_stage") == "hired":
                hired_at_by_app[event.entity_id] = event.created_at
        for application in hired_applications:
            hired_at = hired_at_by_app.get(application.id)
            opening_created = application.opening.created_at
            if hired_at:
                hire_days.append((hired_at - opening_created).total_seconds() / 86400)

    avg_days_to_hire = round(sum(hire_days) / len(hire_days), 1) if hire_days else None

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
    active_applications = [
        a for a in all_applications
        if a.stage not in (ApplicationStage.hired, ApplicationStage.rejected, ApplicationStage.withdrawn)
    ]
    stale_applications = [
        {"application": a, "last_activity": _last_activity(a)}
        for a in active_applications
        if _last_activity(a) < cutoff
    ]
    stale_applications.sort(key=lambda row: row["last_activity"])

    return templates.TemplateResponse(
        context["request"],
        "dashboard/index.html",
        {
            **context,
            "opening_rows": opening_rows,
            "hires_to_date": hires_to_date,
            "avg_days_to_hire": avg_days_to_hire,
            "overrides": overrides,
            "released_interviews": released_interviews,
            "stale_applications": stale_applications,
            "stale_after_days": STALE_AFTER_DAYS,
        },
    )


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
    _require_chairman(current_user)

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
            db.scalars(select(SafeguardingCheck.id).join(Application).where(Application.opening_id == opening_id))
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
