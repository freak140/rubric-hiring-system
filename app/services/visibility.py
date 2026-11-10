"""Who can see what on the ratings matrix."""

from app.models.enums import AppRole
from app.models.interviews import Interview
from app.models.users import User


def can_view_ratings(user: User, interview: Interview) -> bool:
    if user.app_role in (AppRole.chairman, AppRole.hr):
        return True

    application = interview.application
    if user.id == application.opening.hiring_manager_id:
        return True

    if user.app_role == AppRole.interviewer:
        own_interviews = [i for i in application.interviews if i.interviewer_id == user.id]
        return any(i.ratings for i in own_interviews)

    return False
