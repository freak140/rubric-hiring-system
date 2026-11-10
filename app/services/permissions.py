"""Who can do what. Pure functions, no database access.

These are consulted from routes (to enforce) and templates (to hide actions
the current user cannot take) -- never duplicated as ad-hoc role checks
elsewhere.
"""

from app.models.applications import Application
from app.models.enums import AppRole, InterviewType
from app.models.interviews import Interview
from app.models.openings import RoleOpening
from app.models.users import User


def _manages_opening(user: User, opening: RoleOpening) -> bool:
    return user.app_role == AppRole.principal and user.id == opening.hiring_manager_id


def can_create_opening(user: User) -> bool:
    return user.app_role in (AppRole.chairman, AppRole.principal)


def can_manage_scorecard(user: User, opening: RoleOpening) -> bool:
    return user.app_role == AppRole.chairman or _manages_opening(user, opening)


def can_approve_scorecard(user: User, opening: RoleOpening) -> bool:
    return can_manage_scorecard(user, opening)


def can_add_candidate(user: User) -> bool:
    return user.app_role in (AppRole.chairman, AppRole.principal, AppRole.hr)


def can_assign_interviewer(user: User, opening: RoleOpening) -> bool:
    return user.app_role == AppRole.chairman or _manages_opening(user, opening)


def can_record_decision(user: User, opening: RoleOpening) -> bool:
    return user.app_role == AppRole.chairman or _manages_opening(user, opening)


def can_record_sell_plan(user: User, opening: RoleOpening) -> bool:
    return user.app_role == AppRole.chairman or _manages_opening(user, opening)


def can_manage_references(user: User) -> bool:
    return user.app_role in (AppRole.chairman, AppRole.hr)


def can_name_reference(user: User, application: Application) -> bool:
    """Naming a reference is narrower than managing it: the Who interviewer does
    this live, during their interview, in addition to chairman/hr."""
    if can_manage_references(user):
        return True
    return user.app_role == AppRole.interviewer and any(
        i.interview_type == InterviewType.who and i.interviewer_id == user.id for i in application.interviews
    )


def can_manage_safeguarding(user: User) -> bool:
    return user.app_role in (AppRole.chairman, AppRole.hr)


def can_view_dashboard(user: User) -> bool:
    return user.app_role == AppRole.chairman


def can_view_audit_log(user: User) -> bool:
    return user.app_role == AppRole.chairman


def can_override_gate(user: User) -> bool:
    return user.app_role == AppRole.chairman


def can_reject_or_withdraw(user: User, opening: RoleOpening) -> bool:
    return user.app_role == AppRole.chairman or _manages_opening(user, opening)


def can_release_interviewer(user: User, opening: RoleOpening) -> bool:
    return user.app_role == AppRole.chairman or _manages_opening(user, opening)


def can_submit_rating(user: User, interview: Interview) -> bool:
    """Only the assigned interviewer may fill in their own rating form."""
    return user.id == interview.interviewer_id


def can_view_interview(user: User, interview: Interview) -> bool:
    if user.app_role in (AppRole.chairman, AppRole.hr):
        return True
    if user.app_role == AppRole.principal and _manages_opening(user, interview.application.opening):
        return True
    return user.app_role == AppRole.interviewer and user.id == interview.interviewer_id
