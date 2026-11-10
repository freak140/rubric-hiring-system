import pytest

from app.config import DEFAULT_SAFEGUARDING_CHECKS
from app.models.enums import ApplicationStage, AppRole, InterviewStatus, InterviewType, ScorecardStatus
from app.services.workflow import (
    WorkflowError,
    advance_application,
    approve_scorecard,
    assert_scorecard_editable,
    create_default_safeguarding_checks,
    release_interviewer,
)
from tests.factories import make_application, make_interview, make_opening, make_scorecard, make_user


class FakeSession:
    """Stand-in for a SQLAlchemy Session; records what would be persisted."""

    def __init__(self):
        self.added: list = []

    def add(self, obj):
        self.added.append(obj)

    def add_all(self, objs):
        self.added.extend(objs)

    def flush(self):
        pass


def _blocked_application():
    """An application with no scorecard: the sourced->screening gate is blocked."""
    chairman = make_user(AppRole.chairman)
    opening = make_opening(chairman)
    return make_application(opening), chairman


def _ready_application():
    chairman = make_user(AppRole.chairman)
    opening = make_opening(chairman)
    make_scorecard(opening, status=ScorecardStatus.approved)
    return make_application(opening), chairman


def test_advance_moves_forward_when_gate_passes():
    application, chairman = _ready_application()
    db = FakeSession()

    result = advance_application(db, application, chairman, ApplicationStage.screening)

    assert result.allowed
    assert application.stage == ApplicationStage.screening


def test_advance_rejects_skipping_a_stage():
    application, chairman = _ready_application()
    db = FakeSession()

    with pytest.raises(WorkflowError):
        advance_application(db, application, chairman, ApplicationStage.focused)


def test_cannot_advance_from_a_terminal_stage():
    application, chairman = _ready_application()
    application.stage = ApplicationStage.hired
    db = FakeSession()

    with pytest.raises(WorkflowError):
        advance_application(db, application, chairman, ApplicationStage.offer)


def test_override_by_principal_is_refused():
    application, _ = _blocked_application()
    principal = make_user(AppRole.principal)
    db = FakeSession()

    with pytest.raises(WorkflowError):
        advance_application(
            db, application, principal, ApplicationStage.screening, override_reason="Please let it through."
        )
    assert application.stage == ApplicationStage.sourced


def test_override_by_chairman_without_reason_is_blocked():
    application, chairman = _blocked_application()
    db = FakeSession()

    result = advance_application(db, application, chairman, ApplicationStage.screening)

    assert not result.allowed
    assert application.stage == ApplicationStage.sourced


def test_override_by_chairman_with_reason_is_allowed():
    application, chairman = _blocked_application()
    db = FakeSession()

    result = advance_application(
        db, application, chairman, ApplicationStage.screening, override_reason="Urgent hire; principal vouches."
    )

    assert result.allowed
    assert application.stage == ApplicationStage.screening
    audit_events = [e for e in db.added if hasattr(e, "is_override")]
    assert any(e.is_override and e.override_reason for e in audit_events)


def test_reject_requires_a_reason():
    application, chairman = _blocked_application()
    db = FakeSession()

    with pytest.raises(WorkflowError):
        advance_application(db, application, chairman, ApplicationStage.rejected)


def test_reject_with_reason_succeeds_from_an_active_stage():
    application, chairman = _blocked_application()
    db = FakeSession()

    result = advance_application(db, application, chairman, ApplicationStage.rejected, reason="Not a fit after screening.")

    assert result.allowed
    assert application.stage == ApplicationStage.rejected


def test_release_interviewer_without_reason_is_blocked():
    application, chairman = _blocked_application()
    interviewer = make_user(AppRole.interviewer)
    interview = make_interview(application, InterviewType.focused, interviewer, InterviewStatus.assigned)
    db = FakeSession()

    with pytest.raises(WorkflowError):
        release_interviewer(db, interview, chairman, reason="")


def test_release_interviewer_by_hiring_manager_succeeds():
    application, chairman = _blocked_application()
    hiring_manager = application.opening.hiring_manager
    interviewer = make_user(AppRole.interviewer)
    interview = make_interview(application, InterviewType.focused, interviewer, InterviewStatus.assigned)
    db = FakeSession()

    release_interviewer(db, interview, hiring_manager, reason="Scheduling conflict.")

    assert interview.status == InterviewStatus.released
    assert interview.release_reason == "Scheduling conflict."


def test_release_interviewer_by_unrelated_user_is_refused():
    application, chairman = _blocked_application()
    interviewer = make_user(AppRole.interviewer)
    unrelated_principal = make_user(AppRole.principal)
    interview = make_interview(application, InterviewType.focused, interviewer, InterviewStatus.assigned)
    db = FakeSession()

    with pytest.raises(WorkflowError):
        release_interviewer(db, interview, unrelated_principal, reason="Not my call.")


def test_approve_scorecard_sets_status_and_approver():
    chairman = make_user(AppRole.chairman)
    opening = make_opening(chairman)
    scorecard = make_scorecard(opening, status=ScorecardStatus.draft)
    db = FakeSession()

    approve_scorecard(db, scorecard, chairman)

    assert scorecard.status == ScorecardStatus.approved
    assert scorecard.approved_by_id == chairman.id
    assert scorecard.approved_at is not None


def test_assert_scorecard_editable_blocks_an_approved_scorecard():
    chairman = make_user(AppRole.chairman)
    opening = make_opening(chairman)
    scorecard = make_scorecard(opening, status=ScorecardStatus.approved)

    with pytest.raises(WorkflowError):
        assert_scorecard_editable(scorecard)


def test_create_default_safeguarding_checks():
    application, _ = _blocked_application()
    db = FakeSession()

    checks = create_default_safeguarding_checks(db, application)

    assert [c.check_name for c in checks] == DEFAULT_SAFEGUARDING_CHECKS
    assert application.safeguarding_checks == checks


def test_create_default_safeguarding_checks_is_not_duplicated():
    application, _ = _blocked_application()
    db = FakeSession()

    create_default_safeguarding_checks(db, application)
    checks_again = create_default_safeguarding_checks(db, application)

    assert len(application.safeguarding_checks) == len(DEFAULT_SAFEGUARDING_CHECKS)
    assert checks_again == application.safeguarding_checks


def test_advancing_into_references_creates_safeguarding_checks():
    chairman = make_user(AppRole.chairman)
    opening = make_opening(chairman)
    make_scorecard(opening, status=ScorecardStatus.approved)
    application = make_application(opening)
    application.stage = ApplicationStage.focused
    db = FakeSession()

    advance_application(
        db, application, chairman, ApplicationStage.references, override_reason="Fast-tracking for the demo."
    )

    assert len(application.safeguarding_checks) == len(DEFAULT_SAFEGUARDING_CHECKS)
