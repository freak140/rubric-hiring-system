from app.models.enums import AppRole, InterviewStatus, InterviewType
from app.services import permissions
from tests.factories import make_application, make_interview, make_opening, make_user


def test_chairman_can_create_opening_anyone_else_restricted_to_principal():
    chairman = make_user(AppRole.chairman)
    principal = make_user(AppRole.principal)
    hr = make_user(AppRole.hr)
    interviewer = make_user(AppRole.interviewer)

    assert permissions.can_create_opening(chairman)
    assert permissions.can_create_opening(principal)
    assert not permissions.can_create_opening(hr)
    assert not permissions.can_create_opening(interviewer)


def test_only_the_managing_principal_or_chairman_can_manage_the_scorecard():
    chairman = make_user(AppRole.chairman)
    managing_principal = make_user(AppRole.principal)
    other_principal = make_user(AppRole.principal)
    opening = make_opening(managing_principal)

    assert permissions.can_manage_scorecard(chairman, opening)
    assert permissions.can_manage_scorecard(managing_principal, opening)
    assert not permissions.can_manage_scorecard(other_principal, opening)


def test_hr_and_chairman_manage_references_and_safeguarding():
    chairman = make_user(AppRole.chairman)
    hr = make_user(AppRole.hr)
    principal = make_user(AppRole.principal)

    assert permissions.can_manage_references(chairman)
    assert permissions.can_manage_references(hr)
    assert not permissions.can_manage_references(principal)
    assert permissions.can_manage_safeguarding(hr)
    assert not permissions.can_manage_safeguarding(principal)


def test_only_chairman_sees_dashboard_audit_log_and_can_override():
    chairman = make_user(AppRole.chairman)
    principal = make_user(AppRole.principal)

    assert permissions.can_view_dashboard(chairman)
    assert not permissions.can_view_dashboard(principal)
    assert permissions.can_view_audit_log(chairman)
    assert not permissions.can_view_audit_log(principal)
    assert permissions.can_override_gate(chairman)
    assert not permissions.can_override_gate(principal)


def test_only_principal_sees_the_principal_dashboard():
    chairman = make_user(AppRole.chairman)
    principal = make_user(AppRole.principal)
    hr = make_user(AppRole.hr)

    assert permissions.can_view_principal_dashboard(principal)
    assert not permissions.can_view_principal_dashboard(chairman)
    assert not permissions.can_view_principal_dashboard(hr)


def test_only_the_assigned_interviewer_can_submit_their_rating():
    principal = make_user(AppRole.principal)
    opening = make_opening(principal)
    application = make_application(opening)
    interviewer = make_user(AppRole.interviewer)
    other_interviewer = make_user(AppRole.interviewer)
    interview = make_interview(application, InterviewType.focused, interviewer, InterviewStatus.assigned)

    assert permissions.can_submit_rating(interviewer, interview)
    assert not permissions.can_submit_rating(other_interviewer, interview)


def test_interviewer_can_only_view_their_own_assigned_interview():
    principal = make_user(AppRole.principal)
    opening = make_opening(principal)
    application = make_application(opening)
    interviewer = make_user(AppRole.interviewer)
    other_interviewer = make_user(AppRole.interviewer)
    interview = make_interview(application, InterviewType.focused, interviewer, InterviewStatus.assigned)

    assert permissions.can_view_interview(interviewer, interview)
    assert not permissions.can_view_interview(other_interviewer, interview)
    assert permissions.can_view_interview(principal, interview)  # the managing principal

    chairman = make_user(AppRole.chairman)
    hr = make_user(AppRole.hr)
    assert permissions.can_view_interview(chairman, interview)
    assert permissions.can_view_interview(hr, interview)


def test_who_interviewer_and_hr_chairman_can_name_a_reference_but_others_cannot():
    principal = make_user(AppRole.principal)
    opening = make_opening(principal)
    application = make_application(opening)
    who_interviewer = make_user(AppRole.interviewer)
    other_interviewer = make_user(AppRole.interviewer)
    make_interview(application, InterviewType.who, who_interviewer, InterviewStatus.completed)

    chairman = make_user(AppRole.chairman)
    hr = make_user(AppRole.hr)
    assert permissions.can_name_reference(chairman, application)
    assert permissions.can_name_reference(hr, application)
    assert permissions.can_name_reference(who_interviewer, application)
    assert not permissions.can_name_reference(other_interviewer, application)
    assert not permissions.can_name_reference(principal, application)
