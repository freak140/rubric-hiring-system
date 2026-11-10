from app.models.enums import (
    ApplicationStage,
    AppRole,
    CheckStatus,
    DecisionOutcome,
    InterviewStatus,
    InterviewType,
    RefereeRelationship,
    ReferenceStatus,
    ScorecardStatus,
    ScreeningOutcome,
)
from app.services import gates
from tests.factories import (
    make_application,
    make_decision,
    make_interview,
    make_opening,
    make_rating,
    make_reference,
    make_safeguarding_check,
    make_scorecard,
    make_user,
)


def test_sourced_to_screening_passes_with_approved_scorecard():
    chairman = make_user(AppRole.chairman)
    opening = make_opening(chairman)
    make_scorecard(opening, status=ScorecardStatus.approved)
    application = make_application(opening)

    result = gates.check_gate(application, ApplicationStage.screening)
    assert result.allowed
    assert result.reasons == []


def test_sourced_to_screening_blocked_without_scorecard():
    chairman = make_user(AppRole.chairman)
    opening = make_opening(chairman)
    application = make_application(opening)

    result = gates.check_gate(application, ApplicationStage.screening)
    assert not result.allowed
    assert "no scorecard" in result.reasons[0].lower()


def test_sourced_to_screening_blocked_when_not_approved():
    chairman = make_user(AppRole.chairman)
    opening = make_opening(chairman)
    make_scorecard(opening, status=ScorecardStatus.draft)
    application = make_application(opening)

    result = gates.check_gate(application, ApplicationStage.screening)
    assert not result.allowed
    assert any("approved" in r for r in result.reasons)


def test_sourced_to_screening_blocked_without_outcome_or_competency():
    chairman = make_user(AppRole.chairman)
    opening = make_opening(chairman)
    make_scorecard(opening, status=ScorecardStatus.approved, with_items=False)
    application = make_application(opening)

    result = gates.check_gate(application, ApplicationStage.screening)
    assert not result.allowed
    assert any("outcome" in r for r in result.reasons)
    assert any("competency" in r for r in result.reasons)


def _app_with_opening():
    chairman = make_user(AppRole.chairman)
    opening = make_opening(chairman)
    make_scorecard(opening, status=ScorecardStatus.approved)
    return make_application(opening)


def test_screening_to_who_passes_with_completed_pass():
    application = _app_with_opening()
    interviewer = make_user(AppRole.interviewer)
    make_interview(
        application, InterviewType.screening, interviewer, InterviewStatus.completed, ScreeningOutcome.pass_
    )

    result = gates.check_gate(application, ApplicationStage.who_interview)
    assert result.allowed


def test_screening_to_who_blocked_without_interview():
    application = _app_with_opening()
    result = gates.check_gate(application, ApplicationStage.who_interview)
    assert not result.allowed
    assert "no screening interview" in result.reasons[0].lower()


def test_screening_to_who_blocked_on_fail():
    application = _app_with_opening()
    interviewer = make_user(AppRole.interviewer)
    make_interview(
        application, InterviewType.screening, interviewer, InterviewStatus.completed, ScreeningOutcome.fail
    )

    result = gates.check_gate(application, ApplicationStage.who_interview)
    assert not result.allowed
    assert any("pass" in r.lower() for r in result.reasons)


def test_who_to_focused_passes_with_who_interview_and_two_references_incl_former_manager():
    application = _app_with_opening()
    interviewer = make_user(AppRole.interviewer)
    make_interview(application, InterviewType.who, interviewer, InterviewStatus.completed)
    make_reference(application, RefereeRelationship.former_manager)
    make_reference(application, RefereeRelationship.peer)

    result = gates.check_gate(application, ApplicationStage.focused)
    assert result.allowed


def test_who_to_focused_blocked_with_only_one_reference():
    application = _app_with_opening()
    interviewer = make_user(AppRole.interviewer)
    make_interview(application, InterviewType.who, interviewer, InterviewStatus.completed)
    make_reference(application, RefereeRelationship.former_manager)

    result = gates.check_gate(application, ApplicationStage.focused)
    assert not result.allowed
    assert any("2 references" in r or "at least 2" in r.lower() for r in result.reasons)


def test_who_to_focused_blocked_with_two_references_but_no_former_manager():
    application = _app_with_opening()
    interviewer = make_user(AppRole.interviewer)
    make_interview(application, InterviewType.who, interviewer, InterviewStatus.completed)
    make_reference(application, RefereeRelationship.peer)
    make_reference(application, RefereeRelationship.direct_report)

    result = gates.check_gate(application, ApplicationStage.focused)
    assert not result.allowed
    assert any("former manager" in r.lower() for r in result.reasons)


def _app_ready_for_focused():
    application = _app_with_opening()
    interviewer = make_user(AppRole.interviewer)
    make_interview(application, InterviewType.who, interviewer, InterviewStatus.completed)
    make_reference(application, RefereeRelationship.former_manager)
    make_reference(application, RefereeRelationship.peer)
    return application


def test_focused_to_references_passes_with_completed_rated_interview():
    application = _app_ready_for_focused()
    interviewer = make_user(AppRole.interviewer)
    interview = make_interview(application, InterviewType.focused, interviewer, InterviewStatus.completed)
    for item in application.opening.scorecard.items:
        make_rating(interview, item, evidence="Clear evidence from the lesson.")

    result = gates.check_gate(application, ApplicationStage.references)
    assert result.allowed


def test_focused_to_references_blocked_missing_evidence():
    application = _app_ready_for_focused()
    interviewer = make_user(AppRole.interviewer)
    interview = make_interview(application, InterviewType.focused, interviewer, InterviewStatus.completed)
    # Only rate the first item, leave the rest unrated.
    make_rating(interview, application.opening.scorecard.items[0], evidence="Some evidence.")

    result = gates.check_gate(application, ApplicationStage.references)
    assert not result.allowed
    assert any("missing evidence" in r.lower() for r in result.reasons)


def test_focused_to_references_blocked_released_without_reason():
    application = _app_ready_for_focused()
    interviewer = make_user(AppRole.interviewer)
    make_interview(application, InterviewType.focused, interviewer, InterviewStatus.released, release_reason=None)

    result = gates.check_gate(application, ApplicationStage.references)
    assert not result.allowed
    assert any("release reason" in r.lower() for r in result.reasons)


def test_focused_to_references_passes_with_released_with_reason_and_one_completed():
    application = _app_ready_for_focused()
    interviewer_a = make_user(AppRole.interviewer, "Interviewer A")
    interviewer_b = make_user(AppRole.interviewer, "Interviewer B")
    make_interview(
        application, InterviewType.focused, interviewer_a, InterviewStatus.released, release_reason="Conflict of interest."
    )
    interview = make_interview(application, InterviewType.demo_lesson, interviewer_b, InterviewStatus.completed)
    for item in application.opening.scorecard.items:
        make_rating(interview, item, evidence="Taught a clear sample lesson.")

    result = gates.check_gate(application, ApplicationStage.references)
    assert result.allowed


def _app_ready_for_decision():
    application = _app_ready_for_focused()
    interviewer = make_user(AppRole.interviewer)
    interview = make_interview(application, InterviewType.focused, interviewer, InterviewStatus.completed)
    for item in application.opening.scorecard.items:
        make_rating(interview, item, evidence="Evidence noted.")
    return application


def test_references_to_decision_passes():
    application = _app_ready_for_decision()
    make_reference(application, RefereeRelationship.former_manager, ReferenceStatus.completed)
    make_reference(application, RefereeRelationship.peer, ReferenceStatus.completed)
    make_safeguarding_check(application, CheckStatus.cleared)
    make_safeguarding_check(application, CheckStatus.cleared)

    result = gates.check_gate(application, ApplicationStage.decision)
    assert result.allowed


def test_references_to_decision_blocked_zero_safeguarding_checks():
    application = _app_ready_for_decision()
    make_reference(application, RefereeRelationship.former_manager, ReferenceStatus.completed)
    make_reference(application, RefereeRelationship.peer, ReferenceStatus.completed)
    # No safeguarding checks created at all.

    result = gates.check_gate(application, ApplicationStage.decision)
    assert not result.allowed
    assert any("no safeguarding checks" in r.lower() for r in result.reasons)


def test_references_to_decision_blocked_uncleared_check():
    application = _app_ready_for_decision()
    make_reference(application, RefereeRelationship.former_manager, ReferenceStatus.completed)
    make_reference(application, RefereeRelationship.peer, ReferenceStatus.completed)
    make_safeguarding_check(application, CheckStatus.flagged)

    result = gates.check_gate(application, ApplicationStage.decision)
    assert not result.allowed
    assert any("not yet cleared" in r.lower() for r in result.reasons)


def test_decision_to_offer_passes_with_hire_and_rationale():
    application = _app_with_opening()
    make_decision(application, DecisionOutcome.hire, "Excellent evidence across the board.")

    result = gates.check_gate(application, ApplicationStage.offer)
    assert result.allowed


def test_decision_to_offer_blocked_without_decision():
    application = _app_with_opening()
    result = gates.check_gate(application, ApplicationStage.offer)
    assert not result.allowed


def test_decision_to_offer_blocked_when_no_hire():
    application = _app_with_opening()
    make_decision(application, DecisionOutcome.no_hire, "Not a fit.")

    result = gates.check_gate(application, ApplicationStage.offer)
    assert not result.allowed
    assert any("not a hire" in r.lower() for r in result.reasons)


def test_offer_to_hired_has_no_gate():
    application = _app_with_opening()
    result = gates.check_gate(application, ApplicationStage.hired)
    assert result.allowed
    assert result.reasons == []
