"""Append-only audit trail. There is deliberately no update or delete here."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.applications import Application
from app.models.audit import AuditEvent
from app.models.decisions import Decision
from app.models.interviews import Interview
from app.models.references import Reference
from app.models.safeguarding import SafeguardingCheck
from app.models.scorecards import Scorecard, ScorecardItem
from app.models.sell_plans import SellPlan
from app.models.users import User


def log_event(
    db: Session,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: int,
    details: dict | None = None,
    is_override: bool = False,
    override_reason: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
        is_override=is_override,
        override_reason=override_reason,
    )
    db.add(event)
    db.flush()
    return event


def events_for_openings(db: Session, opening_ids: list[int], limit: int = 50) -> list[AuditEvent]:
    """Every audit event touching one of these openings, or anything under
    them (applications, interviews, references, safeguarding checks,
    decisions, sell plans, scorecards/items). AuditEvent is polymorphic
    (entity_type + entity_id) with no FK, so this resolves each entity type
    to the set of ids that actually belong to these openings.
    """
    if not opening_ids:
        return []

    app_ids = set(db.scalars(select(Application.id).where(Application.opening_id.in_(opening_ids))))
    interview_ids = set(
        db.scalars(select(Interview.id).join(Application).where(Application.opening_id.in_(opening_ids)))
    )
    reference_ids = set(
        db.scalars(select(Reference.id).join(Application).where(Application.opening_id.in_(opening_ids)))
    )
    check_ids = set(
        db.scalars(select(SafeguardingCheck.id).join(Application).where(Application.opening_id.in_(opening_ids)))
    )
    decision_ids = set(
        db.scalars(select(Decision.id).join(Application).where(Application.opening_id.in_(opening_ids)))
    )
    sell_plan_ids = set(
        db.scalars(select(SellPlan.id).join(Application).where(Application.opening_id.in_(opening_ids)))
    )
    scorecard_ids = set(db.scalars(select(Scorecard.id).where(Scorecard.opening_id.in_(opening_ids))))
    scorecard_item_ids = set(
        db.scalars(select(ScorecardItem.id).join(Scorecard).where(Scorecard.opening_id.in_(opening_ids)))
    )

    conditions = [
        (AuditEvent.entity_type == "RoleOpening") & (AuditEvent.entity_id.in_(opening_ids)),
        (AuditEvent.entity_type == "Application") & (AuditEvent.entity_id.in_(app_ids)),
        (AuditEvent.entity_type == "Interview") & (AuditEvent.entity_id.in_(interview_ids)),
        (AuditEvent.entity_type == "Reference") & (AuditEvent.entity_id.in_(reference_ids)),
        (AuditEvent.entity_type == "SafeguardingCheck") & (AuditEvent.entity_id.in_(check_ids)),
        (AuditEvent.entity_type == "Decision") & (AuditEvent.entity_id.in_(decision_ids)),
        (AuditEvent.entity_type == "SellPlan") & (AuditEvent.entity_id.in_(sell_plan_ids)),
        (AuditEvent.entity_type == "Scorecard") & (AuditEvent.entity_id.in_(scorecard_ids)),
        (AuditEvent.entity_type == "ScorecardItem") & (AuditEvent.entity_id.in_(scorecard_item_ids)),
    ]
    return db.scalars(
        select(AuditEvent)
        .where(or_(*conditions))
        .options(selectinload(AuditEvent.actor))
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    ).all()
