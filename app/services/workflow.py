"""State changes for applications, interviews and scorecards.

Every function here that mutates data writes an audit event. This is the
only place stage transitions, scorecard approval and interviewer release
are allowed to happen.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import DEFAULT_SAFEGUARDING_CHECKS
from app.models.applications import Application
from app.models.enums import ApplicationStage, AppRole, InterviewStatus, ScorecardStatus
from app.models.interviews import Interview
from app.models.safeguarding import SafeguardingCheck
from app.models.scorecards import Scorecard
from app.models.users import User
from app.services import gates
from app.services.audit import log_event


class WorkflowError(Exception):
    """Raised when a requested action is not permitted, independent of gate reasons."""


def advance_application(
    db: Session,
    application: Application,
    actor: User,
    target_stage: ApplicationStage,
    reason: str | None = None,
    override_reason: str | None = None,
) -> gates.GateResult:
    current_stage = application.stage

    if current_stage in gates.TERMINAL_STAGES:
        raise WorkflowError(f"'{current_stage.value}' is a final stage; no further moves are possible.")

    if target_stage in (ApplicationStage.rejected, ApplicationStage.withdrawn):
        if not (reason and reason.strip()):
            raise WorkflowError("A reason is required to reject or withdraw an application.")
        application.stage = target_stage
        log_event(
            db,
            actor,
            f"application.{target_stage.value}",
            "Application",
            application.id,
            details={"from_stage": current_stage.value, "to_stage": target_stage.value, "reason": reason},
        )
        return gates.GateResult(allowed=True, reasons=[])

    expected_next = gates.NEXT_STAGE.get(current_stage)
    if expected_next != target_stage:
        raise WorkflowError(f"'{target_stage.value}' is not the next stage after '{current_stage.value}'.")

    result = gates.check_gate(application, target_stage)

    if result.allowed:
        _apply_forward_move(db, application, actor, current_stage, target_stage)
        return result

    if override_reason and override_reason.strip():
        if actor.app_role != AppRole.chairman:
            raise WorkflowError("Only the chairman can override a blocked gate.")
        _apply_forward_move(
            db, application, actor, current_stage, target_stage, is_override=True, override_reason=override_reason,
            gate_reasons=result.reasons,
        )
        return gates.GateResult(allowed=True, reasons=[])

    return result


def _apply_forward_move(
    db: Session,
    application: Application,
    actor: User,
    current_stage: ApplicationStage,
    target_stage: ApplicationStage,
    is_override: bool = False,
    override_reason: str | None = None,
    gate_reasons: list[str] | None = None,
) -> None:
    application.stage = target_stage
    details: dict = {"from_stage": current_stage.value, "to_stage": target_stage.value}
    if gate_reasons:
        details["gate_reasons"] = gate_reasons
    log_event(
        db,
        actor,
        "application.advance",
        "Application",
        application.id,
        details=details,
        is_override=is_override,
        override_reason=override_reason,
    )
    if target_stage == ApplicationStage.references:
        create_default_safeguarding_checks(db, application)


def release_interviewer(db: Session, interview: Interview, actor: User, reason: str) -> Interview:
    if not (reason and reason.strip()):
        raise WorkflowError("A reason is required to release an interviewer.")
    hiring_manager_id = interview.application.opening.hiring_manager_id
    if actor.app_role != AppRole.chairman and actor.id != hiring_manager_id:
        raise WorkflowError("Only the opening's hiring manager or the chairman can release an interviewer.")

    interview.status = InterviewStatus.released
    interview.release_reason = reason
    log_event(
        db,
        actor,
        "interview.release",
        "Interview",
        interview.id,
        details={"reason": reason, "interviewer_id": interview.interviewer_id},
    )
    return interview


def assert_scorecard_editable(scorecard: Scorecard) -> None:
    if scorecard.status == ScorecardStatus.approved:
        raise WorkflowError("An approved scorecard cannot be edited.")


def approve_scorecard(db: Session, scorecard: Scorecard, actor: User) -> Scorecard:
    assert_scorecard_editable(scorecard)
    scorecard.status = ScorecardStatus.approved
    scorecard.approved_by_id = actor.id
    scorecard.approved_at = datetime.now(timezone.utc)
    log_event(
        db, actor, "scorecard.approve", "Scorecard", scorecard.id, details={"opening_id": scorecard.opening_id}
    )
    return scorecard


def create_default_safeguarding_checks(db: Session, application: Application) -> list[SafeguardingCheck]:
    if application.safeguarding_checks:
        return application.safeguarding_checks

    checks = [SafeguardingCheck(application=application, check_name=name) for name in DEFAULT_SAFEGUARDING_CHECKS]
    db.add_all(checks)
    db.flush()
    log_event(
        db,
        None,
        "safeguarding.create_defaults",
        "Application",
        application.id,
        details={"checks": DEFAULT_SAFEGUARDING_CHECKS},
    )
    return checks
