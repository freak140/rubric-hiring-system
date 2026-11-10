"""Stage-gate rules for the Who hiring pipeline.

Pure functions: no database access. Callers must pass an Application with
its relationships (opening.scorecard.items, interviews.ratings, references,
safeguarding_checks, decision) already loaded.
"""

from dataclasses import dataclass, field

from app.models.applications import Application
from app.models.enums import (
    ApplicationStage,
    CheckStatus,
    DecisionOutcome,
    InterviewStatus,
    InterviewType,
    RefereeRelationship,
    ReferenceStatus,
    ScorecardItemKind,
    ScorecardStatus,
    ScreeningOutcome,
)

MIN_REFERENCES = 2
MIN_FOCUSED_INTERVIEWS = 1


@dataclass
class GateResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


# Stages a forward move cannot leave.
TERMINAL_STAGES = {ApplicationStage.hired, ApplicationStage.rejected, ApplicationStage.withdrawn}

# The single next stage for each active stage, in Who-method order.
NEXT_STAGE: dict[ApplicationStage, ApplicationStage] = {
    ApplicationStage.sourced: ApplicationStage.screening,
    ApplicationStage.screening: ApplicationStage.who_interview,
    ApplicationStage.who_interview: ApplicationStage.focused,
    ApplicationStage.focused: ApplicationStage.references,
    ApplicationStage.references: ApplicationStage.decision,
    ApplicationStage.decision: ApplicationStage.offer,
    ApplicationStage.offer: ApplicationStage.hired,
}


def gate_sourced_to_screening(application: Application) -> GateResult:
    reasons: list[str] = []
    scorecard = application.opening.scorecard
    if scorecard is None:
        reasons.append("The opening has no scorecard yet.")
    else:
        if scorecard.status != ScorecardStatus.approved:
            reasons.append("The opening's scorecard has not been approved yet.")
        if not any(item.kind == ScorecardItemKind.outcome for item in scorecard.items):
            reasons.append("The scorecard needs at least one outcome.")
        if not any(item.kind == ScorecardItemKind.competency for item in scorecard.items):
            reasons.append("The scorecard needs at least one competency.")
    return GateResult(allowed=not reasons, reasons=reasons)


def gate_screening_to_who_interview(application: Application) -> GateResult:
    reasons: list[str] = []
    screenings = [i for i in application.interviews if i.interview_type == InterviewType.screening]
    completed = [i for i in screenings if i.status == InterviewStatus.completed]
    if not screenings:
        reasons.append("No screening interview has been recorded.")
    elif not completed:
        reasons.append("The screening interview has not been completed.")
    elif not any(i.screening_outcome == ScreeningOutcome.pass_ for i in completed):
        reasons.append("The screening interview did not result in a pass.")
    return GateResult(allowed=not reasons, reasons=reasons)


def gate_who_interview_to_focused(application: Application) -> GateResult:
    reasons: list[str] = []
    who_interviews = [i for i in application.interviews if i.interview_type == InterviewType.who]
    if not any(i.status == InterviewStatus.completed for i in who_interviews):
        reasons.append("A completed Who interview is required.")

    references = application.references
    if len(references) < MIN_REFERENCES:
        reasons.append(f"At least {MIN_REFERENCES} references must be named (currently {len(references)}).")
    if not any(r.referee_relationship == RefereeRelationship.former_manager for r in references):
        reasons.append("At least one named reference must be a former manager.")
    return GateResult(allowed=not reasons, reasons=reasons)


def gate_focused_to_references(application: Application) -> GateResult:
    reasons: list[str] = []
    relevant_types = (InterviewType.focused, InterviewType.demo_lesson)
    interviews = [i for i in application.interviews if i.interview_type in relevant_types]
    completed = [i for i in interviews if i.status == InterviewStatus.completed]

    if len(completed) < MIN_FOCUSED_INTERVIEWS:
        reasons.append(
            f"At least {MIN_FOCUSED_INTERVIEWS} completed focused or demo lesson interview(s) are required."
        )

    for interview in interviews:
        if interview.status not in (InterviewStatus.completed, InterviewStatus.released):
            reasons.append(f"The {interview.interview_type.value} interview (id {interview.id}) is still in progress.")
        elif interview.status == InterviewStatus.released and not (
            interview.release_reason and interview.release_reason.strip()
        ):
            reasons.append(
                f"The released {interview.interview_type.value} interview (id {interview.id}) is missing a release reason."
            )

    scorecard_items = application.opening.scorecard.items if application.opening.scorecard else []
    for interview in completed:
        rated_item_ids = {r.scorecard_item.id for r in interview.ratings if r.evidence and r.evidence.strip()}
        missing_titles = [item.title for item in scorecard_items if item.id not in rated_item_ids]
        if missing_titles:
            reasons.append(
                f"The {interview.interview_type.value} interview (id {interview.id}) is missing evidence for: "
                + ", ".join(missing_titles)
                + "."
            )

    return GateResult(allowed=not reasons, reasons=reasons)


def gate_references_to_decision(application: Application) -> GateResult:
    reasons: list[str] = []
    completed_refs = [r for r in application.references if r.status == ReferenceStatus.completed]
    if len(completed_refs) < MIN_REFERENCES:
        reasons.append(
            f"At least {MIN_REFERENCES} completed references are required (currently {len(completed_refs)})."
        )
    if not any(r.referee_relationship == RefereeRelationship.former_manager for r in completed_refs):
        reasons.append("At least one completed reference must be a former manager.")

    checks = application.safeguarding_checks
    if not checks:
        reasons.append("No safeguarding checks have been created for this application.")
    else:
        uncleared = [c for c in checks if c.status != CheckStatus.cleared]
        if uncleared:
            reasons.append(f"{len(uncleared)} safeguarding check(s) are not yet cleared.")

    return GateResult(allowed=not reasons, reasons=reasons)


def gate_decision_to_offer(application: Application) -> GateResult:
    reasons: list[str] = []
    decision = application.decision
    if decision is None:
        reasons.append("No decision has been recorded yet.")
    else:
        if decision.outcome != DecisionOutcome.hire:
            reasons.append("The recorded decision is not a hire.")
        if not (decision.rationale and decision.rationale.strip()):
            reasons.append("The decision is missing a rationale.")
    return GateResult(allowed=not reasons, reasons=reasons)


def gate_offer_to_hired(application: Application) -> GateResult:
    return GateResult(allowed=True, reasons=[])


_GATES = {
    ApplicationStage.screening: gate_sourced_to_screening,
    ApplicationStage.who_interview: gate_screening_to_who_interview,
    ApplicationStage.focused: gate_who_interview_to_focused,
    ApplicationStage.references: gate_focused_to_references,
    ApplicationStage.decision: gate_references_to_decision,
    ApplicationStage.offer: gate_decision_to_offer,
    ApplicationStage.hired: gate_offer_to_hired,
}


def check_gate(application: Application, target_stage: ApplicationStage) -> GateResult:
    """Check whether `application` may move into `target_stage`."""
    gate_fn = _GATES.get(target_stage)
    if gate_fn is None:
        return GateResult(allowed=True, reasons=[])
    return gate_fn(application)
