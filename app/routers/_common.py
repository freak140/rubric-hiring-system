"""Shared loaders used by the application/interview/reference/safeguarding routers."""

from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload

from app.models.applications import Application
from app.models.decisions import Decision
from app.models.interviews import Interview, Rating
from app.models.openings import RoleOpening
from app.models.safeguarding import SafeguardingCheck
from app.models.scorecards import Scorecard


def load_application(db: Session, application_id: int) -> Application:
    application = db.get(
        Application,
        application_id,
        options=[
            selectinload(Application.candidate),
            selectinload(Application.opening).selectinload(RoleOpening.hiring_manager),
            selectinload(Application.opening).selectinload(RoleOpening.scorecard).selectinload(Scorecard.items),
            selectinload(Application.opening).selectinload(RoleOpening.scorecard).selectinload(Scorecard.approved_by),
            selectinload(Application.interviews).selectinload(Interview.interviewer),
            selectinload(Application.interviews).selectinload(Interview.ratings).selectinload(Rating.scorecard_item),
            selectinload(Application.references),
            selectinload(Application.safeguarding_checks).selectinload(SafeguardingCheck.verified_by),
            selectinload(Application.decision).selectinload(Decision.decided_by),
            selectinload(Application.sell_plan),
        ],
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    return application


def load_interview(db: Session, interview_id: int) -> Interview:
    interview = db.get(
        Interview,
        interview_id,
        options=[
            selectinload(Interview.interviewer),
            selectinload(Interview.ratings).selectinload(Rating.scorecard_item),
            selectinload(Interview.application).selectinload(Application.candidate),
            selectinload(Interview.application)
            .selectinload(Application.opening)
            .selectinload(RoleOpening.scorecard)
            .selectinload(Scorecard.items),
            selectinload(Interview.application).selectinload(Application.interviews).selectinload(Interview.ratings),
        ],
    )
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found.")
    return interview
