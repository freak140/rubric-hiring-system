"""Append-only audit trail. There is deliberately no update or delete here."""

from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
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
