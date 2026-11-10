"""Builders for in-memory model objects used by the test suite.

None of these touch a database session; they just wire up Python objects
via relationship() back_populates, which SQLAlchemy keeps in sync without
a session being involved.
"""

from datetime import datetime, timezone
from itertools import count

from app.models.applications import Application
from app.models.candidates import Candidate
from app.models.decisions import Decision
from app.models.enums import (
    ApplicationStage,
    AppRole,
    CandidateSource,
    CheckStatus,
    DecisionOutcome,
    Grade,
    InterviewStatus,
    InterviewType,
    OpeningStatus,
    RefereeRelationship,
    ReferenceStatus,
    RoleType,
    ScorecardItemKind,
    ScorecardStatus,
    ScreeningOutcome,
)
from app.models.interviews import Interview, Rating
from app.models.openings import RoleOpening
from app.models.references import Reference
from app.models.safeguarding import SafeguardingCheck
from app.models.scorecards import Scorecard, ScorecardItem
from app.models.users import User

_ids = count(1)


def next_id() -> int:
    return next(_ids)


def make_user(role: AppRole = AppRole.chairman, name: str = "Test User") -> User:
    uid = next_id()
    return User(id=uid, name=name, email=f"user{uid}@rubric.test", app_role=role)


def make_opening(hiring_manager: User, status: OpeningStatus = OpeningStatus.open) -> RoleOpening:
    return RoleOpening(
        id=next_id(),
        title="Grade 8 Mathematics Teacher",
        role_type=RoleType.teaching,
        department="Academics",
        status=status,
        hiring_manager_id=hiring_manager.id,
        hiring_manager=hiring_manager,
    )


def make_scorecard(
    opening: RoleOpening, status: ScorecardStatus = ScorecardStatus.approved, with_items: bool = True
) -> Scorecard:
    scorecard = Scorecard(id=next_id(), opening=opening, mission="Teach maths well.", status=status)
    if with_items:
        make_scorecard_item(scorecard, kind=ScorecardItemKind.outcome)
        make_scorecard_item(scorecard, kind=ScorecardItemKind.competency)
    return scorecard


def make_scorecard_item(scorecard: Scorecard, kind: ScorecardItemKind, title: str | None = None) -> ScorecardItem:
    item_id = next_id()
    return ScorecardItem(
        id=item_id,
        scorecard=scorecard,
        kind=kind,
        title=title or f"Item {item_id}",
        description="Description.",
        position=item_id,
    )


def make_application(opening: RoleOpening) -> Application:
    candidate = Candidate(
        id=next_id(), full_name="Jane Doe", email=f"jane{next_id()}@example.com", source=CandidateSource.referral
    )
    return Application(id=next_id(), opening=opening, candidate=candidate, stage=ApplicationStage.sourced)


def make_interview(
    application: Application,
    interview_type: InterviewType,
    interviewer: User,
    status: InterviewStatus = InterviewStatus.completed,
    screening_outcome: ScreeningOutcome | None = None,
    release_reason: str | None = None,
) -> Interview:
    return Interview(
        id=next_id(),
        application=application,
        interview_type=interview_type,
        interviewer=interviewer,
        interviewer_id=interviewer.id,
        status=status,
        screening_outcome=screening_outcome,
        release_reason=release_reason,
    )


def make_rating(interview: Interview, scorecard_item: ScorecardItem, evidence: str = "Observed evidence.") -> Rating:
    return Rating(id=next_id(), interview=interview, scorecard_item=scorecard_item, grade=Grade.B, evidence=evidence)


def make_reference(
    application: Application,
    relationship: RefereeRelationship = RefereeRelationship.former_manager,
    status: ReferenceStatus = ReferenceStatus.named,
) -> Reference:
    return Reference(
        id=next_id(),
        application=application,
        referee_name="Referee Name",
        referee_relationship=relationship,
        status=status,
    )


def make_safeguarding_check(application: Application, status: CheckStatus = CheckStatus.cleared) -> SafeguardingCheck:
    return SafeguardingCheck(id=next_id(), application=application, check_name="Check", status=status)


def make_decision(
    application: Application, outcome: DecisionOutcome = DecisionOutcome.hire, rationale: str = "Strong fit."
) -> Decision:
    return Decision(
        id=next_id(),
        application=application,
        outcome=outcome,
        overall_grade=Grade.B,
        rationale=rationale,
        decided_by_id=1,
        decided_at=datetime.now(timezone.utc),
    )
