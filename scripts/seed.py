"""Wipes and reseeds a realistic demo school. Running it twice gives the same
world (same users, openings, candidates, stages, relationships) -- the only
thing that isn't bit-identical between runs is wall-clock timestamps.

Run: python scripts/seed.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models.applications import Application  # noqa: E402
from app.models.candidates import Candidate  # noqa: E402
from app.models.decisions import Decision  # noqa: E402
from app.models.enums import (  # noqa: E402
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
from app.models.interviews import Interview, Rating  # noqa: E402
from app.models.openings import RoleOpening  # noqa: E402
from app.models.references import Reference  # noqa: E402
from app.models.safeguarding import SafeguardingCheck  # noqa: E402
from app.models.scorecards import Scorecard, ScorecardItem  # noqa: E402
from app.models.sell_plans import SellPlan  # noqa: E402
from app.models.users import User  # noqa: E402
from app.services.ai import prompts  # noqa: E402
from app.services.ai.client import compute_input_hash  # noqa: E402
from app.services.ai.features import (  # noqa: E402
    _decision_summary_input,
    _evidence_map_input,
    _focused_questions_input,
    _scorecard_draft_input,
    ratings_text_for,
    references_text_for,
)
from app.services.audit import log_event  # noqa: E402
from app.services.auth import hash_password  # noqa: E402
from app.services.workflow import advance_application, approve_scorecard  # noqa: E402

ALL_TABLES = [
    "ai_outputs", "ratings", "interviews", "sell_plans", "decisions",
    "safeguarding_checks", "references", "applications", "scorecard_items",
    "scorecards", "candidates", "role_openings", "audit_events", "users",
]


def wipe(db) -> None:
    table_list = ", ".join(f'"{t}"' for t in ALL_TABLES)
    db.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"))
    db.commit()


# Shared password for every seeded user, so "normal mode" (real /login) can be
# tried against the demo data too. Documented in README.md.
DEMO_PASSWORD = "rubric-demo"


def make_users(db) -> dict[str, User]:
    password_hash = hash_password(DEMO_PASSWORD)
    chairman = User(name="Arvind Mehta", email="arvind.mehta@rubric.school", app_role=AppRole.chairman, password_hash=password_hash)
    principal = User(name="Sunita Iyer", email="sunita.iyer@rubric.school", app_role=AppRole.principal, password_hash=password_hash)
    senior_teacher = User(name="Deepak Menon", email="deepak.menon@rubric.school", app_role=AppRole.interviewer, password_hash=password_hash)
    interviewer2 = User(name="Fatima Siddiqui", email="fatima.siddiqui@rubric.school", app_role=AppRole.interviewer, password_hash=password_hash)
    interviewer3 = User(name="Rohan Kapoor", email="rohan.kapoor@rubric.school", app_role=AppRole.interviewer, password_hash=password_hash)
    hr = User(name="Kavita Nair", email="kavita.nair@rubric.school", app_role=AppRole.hr, password_hash=password_hash)
    db.add_all([chairman, principal, senior_teacher, interviewer2, interviewer3, hr])
    db.flush()
    return {
        "chairman": chairman,
        "principal": principal,
        "senior_teacher": senior_teacher,
        "interviewer2": interviewer2,
        "interviewer3": interviewer3,
        "hr": hr,
    }


def make_candidate(db, full_name: str, email: str, source: CandidateSource, source_detail: str | None = None) -> Candidate:
    candidate = Candidate(full_name=full_name, email=email, source=source, source_detail=source_detail)
    db.add(candidate)
    db.flush()
    return candidate


def days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


def advance(db, application, actor, target_stage, **kwargs):
    """advance_application, but fails loudly if the gate blocks the move.

    A silent no-op here (the normal, correct behaviour for a real blocked
    gate) would otherwise show up several lines later as a confusing
    "X is not the next stage after Y" from a totally unrelated call.
    """
    result = advance_application(db, application, actor, target_stage, **kwargs)
    if not result.allowed:
        raise RuntimeError(
            f"Seed data for application {application.id} does not satisfy the gate into "
            f"{target_stage.value}: {result.reasons}"
        )
    return result


def clear_safeguarding(db, application, users, days_back: int) -> None:
    for check in application.safeguarding_checks:
        check.status = CheckStatus.cleared
        check.notes = "Verified, no issues."
        check.verified_by_id = users["hr"].id
        check.verified_at = days_ago(days_back)
        log_event(db, users["hr"], "safeguarding.update", "SafeguardingCheck", check.id, details={"status": "cleared"})


# --- Opening 1: Grade 8 Mathematics Teacher -------------------------------


def make_maths_opening(db, users) -> tuple[RoleOpening, Scorecard, list[ScorecardItem]]:
    opening = RoleOpening(
        title="Grade 8 Mathematics Teacher", role_type=RoleType.teaching, department="Academics",
        status=OpeningStatus.open, hiring_manager=users["principal"],
    )
    db.add(opening)
    db.flush()
    log_event(db, users["principal"], "opening.create", "RoleOpening", opening.id, details={"title": opening.title})

    scorecard = Scorecard(
        opening=opening,
        mission="Help every Grade 8 student build real confidence and competence in mathematics, "
        "measured by benchmark results and classroom engagement.",
        status=ScorecardStatus.draft,
    )
    db.add(scorecard)
    db.flush()

    outcome1 = ScorecardItem(
        scorecard=scorecard, kind=ScorecardItemKind.outcome, title="Benchmark mastery",
        description="90% of students pass the term-end benchmark test.",
        measure="Term-end benchmark pass rate", position=0,
    )
    outcome2 = ScorecardItem(
        scorecard=scorecard, kind=ScorecardItemKind.outcome, title="Lesson plans on time",
        description="Weekly lesson plans submitted every Friday, aligned to the syllabus.",
        measure="On-time submission rate", position=1,
    )
    competency1 = ScorecardItem(
        scorecard=scorecard, kind=ScorecardItemKind.competency, title="Classroom management",
        description="Keeps a class of 35 engaged and on task without raising her voice.", position=2,
    )
    competency2 = ScorecardItem(
        scorecard=scorecard, kind=ScorecardItemKind.competency, title="Parent communication",
        description="Responds to parent concerns within 2 working days with a clear plan.", position=3,
    )
    items = [outcome1, outcome2, competency1, competency2]
    db.add_all(items)
    db.flush()
    for item in items:
        log_event(db, users["principal"], "scorecard_item.add", "ScorecardItem", item.id, details={"title": item.title})

    approve_scorecard(db, scorecard, users["principal"])
    return opening, scorecard, items


def hire_priya(db, opening, items, users) -> Application:
    candidate = make_candidate(
        db, "Priya Sharma", "priya.sharma@example.com", CandidateSource.referral,
        "Referred by a current Grade 7 teacher",
    )
    application = Application(candidate=candidate, opening=opening, stage=ApplicationStage.sourced)
    db.add(application)
    db.flush()
    log_event(
        db, users["principal"], "application.create", "Application", application.id,
        details={"candidate_id": candidate.id, "opening_id": opening.id},
    )

    advance(db, application, users["principal"], ApplicationStage.screening)

    screening = Interview(
        application=application, interview_type=InterviewType.screening, interviewer=users["interviewer2"],
        status=InterviewStatus.completed, screening_outcome=ScreeningOutcome.pass_,
        notes="Clear about wanting to move from a coaching institute into a full-time school role. "
        "Salary expectations are within band. Available to join within 3 weeks.",
        conducted_at=days_ago(20),
    )
    db.add(screening)
    db.flush()
    log_event(
        db, users["principal"], "interview.assign", "Interview", screening.id,
        details={"interview_type": "screening", "interviewer_id": users["interviewer2"].id},
    )
    log_event(db, users["interviewer2"], "interview.complete", "Interview", screening.id, details={"outcome": "pass"})

    advance(db, application, users["principal"], ApplicationStage.who_interview)

    who_notes = (
        "Hired at her last school to turn around a weak Grade 8 batch; most proud of raising the batch's "
        "average benchmark score by 15 points over two terms. Low point: her first term there, she tried "
        "to cover too much syllabus too fast and had to slow down and rebuild trust with the class. "
        "Worked closely with the vice principal, who she says would rate her 8/10 and call her "
        "'reliable under pressure.' Leaving because her family is relocating to be closer to her parents."
    )
    who = Interview(
        application=application, interview_type=InterviewType.who, interviewer=users["senior_teacher"],
        status=InterviewStatus.completed, notes=who_notes, conducted_at=days_ago(18),
    )
    db.add(who)
    db.flush()
    log_event(
        db, users["principal"], "interview.assign", "Interview", who.id,
        details={"interview_type": "who", "interviewer_id": users["senior_teacher"].id},
    )
    log_event(db, users["senior_teacher"], "interview.complete", "Interview", who.id)

    ref1 = Reference(
        application=application, referee_name="Meena Krishnan", referee_relationship=RefereeRelationship.former_manager,
        contact="meena.k@example.com", status=ReferenceStatus.named,
    )
    ref2 = Reference(
        application=application, referee_name="Arjun Rao", referee_relationship=RefereeRelationship.peer,
        contact="arjun.rao@example.com", status=ReferenceStatus.named,
    )
    db.add_all([ref1, ref2])
    db.flush()
    log_event(db, users["senior_teacher"], "reference.add", "Reference", ref1.id, details={"referee_name": ref1.referee_name})
    log_event(db, users["senior_teacher"], "reference.add", "Reference", ref2.id, details={"referee_name": ref2.referee_name})

    advance(db, application, users["principal"], ApplicationStage.focused)

    focused = Interview(
        application=application, interview_type=InterviewType.focused, interviewer=users["interviewer2"],
        status=InterviewStatus.completed,
        notes="Walked through how she'd handle a parent upset about a low test grade: she'd call within "
        "a day, share the error pattern, and propose two check-ins before the next test.",
        conducted_at=days_ago(12),
    )
    demo = Interview(
        application=application, interview_type=InterviewType.demo_lesson, interviewer=users["senior_teacher"],
        status=InterviewStatus.completed,
        notes="Taught a sample lesson on linear equations to a group of 8 students. Checked for "
        "understanding every few minutes with quick whiteboard answers.",
        conducted_at=days_ago(10),
    )
    db.add_all([focused, demo])
    db.flush()
    log_event(
        db, users["principal"], "interview.assign", "Interview", focused.id,
        details={"interview_type": "focused", "interviewer_id": users["interviewer2"].id},
    )
    log_event(
        db, users["principal"], "interview.assign", "Interview", demo.id,
        details={"interview_type": "demo_lesson", "interviewer_id": users["senior_teacher"].id},
    )

    ratings = [
        Rating(interview=focused, scorecard_item=items[0], grade=Grade.A,
               evidence="Described exactly how she tracks which students are below benchmark and adjusts "
               "weekly plans to close the gap."),
        Rating(interview=focused, scorecard_item=items[1], grade=Grade.B,
               evidence="Keeps a shared lesson-plan calendar but admitted she has missed a Friday deadline "
               "twice this year."),
        Rating(interview=focused, scorecard_item=items[2], grade=Grade.A,
               evidence="Gave a specific, calm de-escalation example rather than a generic answer."),
        Rating(interview=focused, scorecard_item=items[3], grade=Grade.A,
               evidence="Concrete two-step plan for an upset parent call, with a same-day response commitment."),
        Rating(interview=demo, scorecard_item=items[0], grade=Grade.A,
               evidence="Every student in the sample group could solve a similar equation unassisted by "
               "the end of the lesson."),
        Rating(interview=demo, scorecard_item=items[1], grade=Grade.B,
               evidence="Brought a fully typed lesson plan for the demo, consistent with her stated habit "
               "of planning ahead even though she sometimes slips on the Friday deadline."),
        Rating(interview=demo, scorecard_item=items[2], grade=Grade.B,
               evidence="Classroom management was good overall; one student was briefly off-task and she "
               "handled it smoothly mid-lesson."),
        Rating(interview=demo, scorecard_item=items[3], grade=Grade.A,
               evidence="After the lesson, she noted she'd message one student's parent about a concept "
               "he struggled with -- unprompted."),
    ]
    db.add_all(ratings)
    db.flush()
    log_event(db, users["interviewer2"], "interview.complete", "Interview", focused.id)
    log_event(db, users["senior_teacher"], "interview.complete", "Interview", demo.id)

    advance(db, application, users["principal"], ApplicationStage.references)

    ref1.status = ReferenceStatus.completed
    ref1.notes = (
        "Priya ran the Grade 8 maths department under me for two years. Reliable, data-driven, and good "
        "with difficult parents. I would rehire her without hesitation."
    )
    ref1.conducted_by_id = users["hr"].id
    ref1.completed_at = days_ago(8)
    ref2.status = ReferenceStatus.completed
    ref2.notes = (
        "We taught adjoining classes. She shares resources generously and her students talk about her "
        "lessons positively. Occasionally runs over the bell."
    )
    ref2.conducted_by_id = users["hr"].id
    ref2.completed_at = days_ago(7)
    log_event(db, users["hr"], "reference.complete", "Reference", ref1.id)
    log_event(db, users["hr"], "reference.complete", "Reference", ref2.id)

    clear_safeguarding(db, application, users, days_back=5)

    advance(db, application, users["principal"], ApplicationStage.decision)

    decision = Decision(
        application=application, outcome=DecisionOutcome.hire, overall_grade=Grade.A,
        rationale="Strong, specific evidence across every scorecard item: benchmark-driven lesson "
        "planning, calm classroom management, and a proactive approach to parent communication. "
        "Former manager would rehire without hesitation.",
        decided_by_id=users["principal"].id, decided_at=days_ago(4),
    )
    db.add(decision)
    application.decision = decision
    db.flush()
    log_event(db, users["principal"], "decision.record", "Decision", decision.id, details={"outcome": "hire"})

    advance(db, application, users["principal"], ApplicationStage.offer)

    sell_plan = SellPlan(
        application=application,
        fit="She's looking for a school that takes benchmark data seriously but still has a strong staff "
        "community -- exactly our culture.",
        family="She's relocating to be near her parents; our school is a 10-minute drive from that neighbourhood.",
        freedom="Happy to let her keep running her weekend maths olympiad club for students.",
        fortune="Offer matches her ask, with the same annual increment structure as her current school.",
        fun="Our staff room runs a Friday quiz; she mentioned she used to host something similar.",
    )
    db.add(sell_plan)
    application.sell_plan = sell_plan
    db.flush()
    log_event(db, users["principal"], "sell_plan.record", "SellPlan", sell_plan.id)

    advance(db, application, users["principal"], ApplicationStage.hired)
    opening.status = OpeningStatus.filled
    return application


def block_rahul(db, opening, items, users) -> Application:
    candidate = make_candidate(db, "Rahul Verma", "rahul.verma@example.com", CandidateSource.job_board)
    application = Application(candidate=candidate, opening=opening, stage=ApplicationStage.sourced)
    db.add(application)
    db.flush()
    log_event(
        db, users["principal"], "application.create", "Application", application.id,
        details={"candidate_id": candidate.id, "opening_id": opening.id},
    )

    advance(db, application, users["principal"], ApplicationStage.screening)

    screening = Interview(
        application=application, interview_type=InterviewType.screening, interviewer=users["interviewer3"],
        status=InterviewStatus.completed, screening_outcome=ScreeningOutcome.pass_,
        notes="Good energy, clear about why he wants to move from tutoring into full-time teaching.",
        conducted_at=days_ago(16),
    )
    db.add(screening)
    db.flush()
    log_event(
        db, users["principal"], "interview.assign", "Interview", screening.id,
        details={"interview_type": "screening", "interviewer_id": users["interviewer3"].id},
    )
    log_event(db, users["interviewer3"], "interview.complete", "Interview", screening.id, details={"outcome": "pass"})

    advance(db, application, users["principal"], ApplicationStage.who_interview)

    who = Interview(
        application=application, interview_type=InterviewType.who, interviewer=users["senior_teacher"],
        status=InterviewStatus.completed,
        notes="Tutored privately for 4 years before this; proud of getting a struggling student from a D "
        "to a B over one year. Says he left his one classroom job because of a difficult vice principal. "
        "Didn't have much detail on who he worked with day to day.",
        conducted_at=days_ago(14),
    )
    db.add(who)
    db.flush()
    log_event(
        db, users["principal"], "interview.assign", "Interview", who.id,
        details={"interview_type": "who", "interviewer_id": users["senior_teacher"].id},
    )
    log_event(db, users["senior_teacher"], "interview.complete", "Interview", who.id)

    ref1 = Reference(
        application=application, referee_name="Mrs. Kulkarni (tutoring parent)",
        referee_relationship=RefereeRelationship.former_manager, status=ReferenceStatus.named,
    )
    ref2 = Reference(
        application=application, referee_name="Sameer Joshi (fellow tutor)",
        referee_relationship=RefereeRelationship.peer, status=ReferenceStatus.named,
    )
    db.add_all([ref1, ref2])
    db.flush()
    log_event(db, users["senior_teacher"], "reference.add", "Reference", ref1.id, details={"referee_name": ref1.referee_name})
    log_event(db, users["senior_teacher"], "reference.add", "Reference", ref2.id, details={"referee_name": ref2.referee_name})

    advance(db, application, users["principal"], ApplicationStage.focused)

    focused = Interview(
        application=application, interview_type=InterviewType.focused, interviewer=users["interviewer2"],
        status=InterviewStatus.completed,
        notes="Solid answer on handling a parent complaint, but vague on how he'd track benchmark progress "
        "across a full class rather than one-on-one.",
        conducted_at=days_ago(9),
    )
    db.add(focused)
    db.flush()
    log_event(
        db, users["principal"], "interview.assign", "Interview", focused.id,
        details={"interview_type": "focused", "interviewer_id": users["interviewer2"].id},
    )
    ratings = [
        Rating(interview=focused, scorecard_item=items[0], grade=Grade.C,
               evidence="Could describe one-on-one progress tracking but not a classroom-wide benchmark system."),
        Rating(interview=focused, scorecard_item=items[1], grade=Grade.B,
               evidence="Has used a weekly planner for tutoring sessions; plausible he'd adapt it to lesson plans."),
        Rating(interview=focused, scorecard_item=items[2], grade=Grade.B,
               evidence="No classroom-of-35 experience, but had sensible instincts in the roleplay."),
        Rating(interview=focused, scorecard_item=items[3], grade=Grade.A,
               evidence="Gave a specific, calm script for a parent call, drawn from real tutoring experience."),
    ]
    db.add_all(ratings)
    db.flush()
    log_event(db, users["interviewer2"], "interview.complete", "Interview", focused.id)

    advance(db, application, users["principal"], ApplicationStage.references)

    ref1.status = ReferenceStatus.completed
    ref1.notes = (
        "Rahul tutored my daughter for two years. Patient and always prepared. I can't speak to classroom "
        "teaching since I only saw him one-on-one."
    )
    ref1.conducted_by_id = users["hr"].id
    ref1.completed_at = days_ago(3)
    log_event(db, users["hr"], "reference.complete", "Reference", ref1.id)
    # ref2 (Sameer Joshi) intentionally stays "named": HR hasn't reached him yet, so this
    # application sits blocked at references with only one completed reference.

    # A still-pending demo lesson: a distinct round from the focused interview above (teaching
    # candidates get both, same as Priya did), given by a different interviewer, not a repeat of
    # a round already held. This is also the demo tour's live "submit a rating" moment -- unlike
    # a hired candidate, Rahul's application is genuinely still active, so a pending interview
    # here is expected, not contradictory.
    demo_lesson = Interview(
        application=application, interview_type=InterviewType.demo_lesson, interviewer=users["interviewer3"],
        status=InterviewStatus.assigned,
    )
    db.add(demo_lesson)
    db.flush()
    log_event(
        db, users["principal"], "interview.assign", "Interview", demo_lesson.id,
        details={"interview_type": "demo_lesson", "interviewer_id": users["interviewer3"].id},
    )

    return application


def partial_anjali(db, opening, users) -> Application:
    candidate = make_candidate(
        db, "Anjali Desai", "anjali.desai@example.com", CandidateSource.network,
        "Known to the principal through a teachers' network",
    )
    application = Application(candidate=candidate, opening=opening, stage=ApplicationStage.sourced)
    db.add(application)
    db.flush()
    log_event(
        db, users["principal"], "application.create", "Application", application.id,
        details={"candidate_id": candidate.id, "opening_id": opening.id},
    )

    advance(db, application, users["principal"], ApplicationStage.screening)

    screening = Interview(
        application=application, interview_type=InterviewType.screening, interviewer=users["interviewer3"],
        status=InterviewStatus.completed, screening_outcome=ScreeningOutcome.pass_,
        notes="Currently teaching Grade 6 maths elsewhere; wants to move up to Grade 8. Comfortable with "
        "our salary band.",
        conducted_at=days_ago(6),
    )
    db.add(screening)
    db.flush()
    log_event(
        db, users["principal"], "interview.assign", "Interview", screening.id,
        details={"interview_type": "screening", "interviewer_id": users["interviewer3"].id},
    )
    log_event(db, users["interviewer3"], "interview.complete", "Interview", screening.id, details={"outcome": "pass"})

    advance(db, application, users["principal"], ApplicationStage.who_interview)

    who = Interview(
        application=application, interview_type=InterviewType.who, interviewer=users["senior_teacher"],
        status=InterviewStatus.assigned,
    )
    db.add(who)
    db.flush()
    log_event(
        db, users["principal"], "interview.assign", "Interview", who.id,
        details={"interview_type": "who", "interviewer_id": users["senior_teacher"].id},
    )
    return application


def reject_vikram(db, opening, users) -> Application:
    candidate = make_candidate(db, "Vikram Nair", "vikram.nair@example.com", CandidateSource.job_board)
    application = Application(candidate=candidate, opening=opening, stage=ApplicationStage.sourced)
    db.add(application)
    db.flush()
    log_event(
        db, users["principal"], "application.create", "Application", application.id,
        details={"candidate_id": candidate.id, "opening_id": opening.id},
    )

    advance(db, application, users["principal"], ApplicationStage.screening)

    screening = Interview(
        application=application, interview_type=InterviewType.screening, interviewer=users["interviewer2"],
        status=InterviewStatus.completed, screening_outcome=ScreeningOutcome.fail,
        notes="Dismissive about parent communication, said it 'wasn't really his job.' Also vague about "
        "why he left his last two schools within a year each.",
        conducted_at=days_ago(15),
    )
    db.add(screening)
    db.flush()
    log_event(
        db, users["principal"], "interview.assign", "Interview", screening.id,
        details={"interview_type": "screening", "interviewer_id": users["interviewer2"].id},
    )
    log_event(db, users["interviewer2"], "interview.complete", "Interview", screening.id, details={"outcome": "fail"})

    advance(
        db, application, users["principal"], ApplicationStage.rejected,
        reason="Screening revealed a mismatch on parent communication expectations and an unexplained "
        "pattern of short tenures.",
    )
    return application


# --- Opening 2: School Bus Driver (draft scorecard, no candidates) -------


def make_bus_driver_opening(db, users) -> RoleOpening:
    opening = RoleOpening(
        title="School Bus Driver", role_type=RoleType.non_teaching, department="Transport",
        status=OpeningStatus.draft, hiring_manager=users["principal"],
    )
    db.add(opening)
    db.flush()
    log_event(db, users["principal"], "opening.create", "RoleOpening", opening.id, details={"title": opening.title})

    scorecard = Scorecard(
        opening=opening, mission="Get every student to and from school safely and on time, every day.",
        status=ScorecardStatus.draft,
    )
    db.add(scorecard)
    db.flush()

    outcome = ScorecardItem(
        scorecard=scorecard, kind=ScorecardItemKind.outcome, title="On-time, incident-free routes",
        description="Completes the assigned route on schedule with zero safety incidents.",
        measure="On-time percentage and incident log", position=0,
    )
    competency = ScorecardItem(
        scorecard=scorecard, kind=ScorecardItemKind.competency, title="Vehicle safety discipline",
        description="Follows the pre-trip inspection checklist and defensive driving practices every day.",
        position=1,
    )
    db.add_all([outcome, competency])
    db.flush()
    log_event(db, users["principal"], "scorecard_item.add", "ScorecardItem", outcome.id, details={"title": outcome.title})
    log_event(db, users["principal"], "scorecard_item.add", "ScorecardItem", competency.id, details={"title": competency.title})
    # Deliberately left unapproved: this opening is "awaiting approval."
    return opening


# --- Opening 3: Accounts Officer (chairman override hire) ----------------


def make_accounts_opening_with_override(db, users) -> RoleOpening:
    opening = RoleOpening(
        title="Accounts Officer", role_type=RoleType.non_teaching, department="Finance",
        status=OpeningStatus.filled, hiring_manager=users["principal"],
    )
    db.add(opening)
    db.flush()
    log_event(db, users["principal"], "opening.create", "RoleOpening", opening.id, details={"title": opening.title})

    scorecard = Scorecard(
        opening=opening, mission="Keep the school's books accurate, current, and audit-ready at all times.",
        status=ScorecardStatus.draft,
    )
    db.add(scorecard)
    db.flush()
    item1 = ScorecardItem(
        scorecard=scorecard, kind=ScorecardItemKind.outcome, title="Month-end close speed",
        description="Closes the books accurately within 5 working days of month end.",
        measure="Days to close", position=0,
    )
    item2 = ScorecardItem(
        scorecard=scorecard, kind=ScorecardItemKind.competency, title="Error detection",
        description="Catches discrepancies before they become losses.", position=1,
    )
    db.add_all([item1, item2])
    db.flush()
    log_event(db, users["principal"], "scorecard_item.add", "ScorecardItem", item1.id, details={"title": item1.title})
    log_event(db, users["principal"], "scorecard_item.add", "ScorecardItem", item2.id, details={"title": item2.title})
    approve_scorecard(db, scorecard, users["principal"])

    candidate = make_candidate(
        db, "Suresh Pillai", "suresh.pillai@rubric.school", CandidateSource.referral,
        "Internal transfer from the Accounts Assistant role",
    )
    application = Application(candidate=candidate, opening=opening, stage=ApplicationStage.sourced)
    db.add(application)
    db.flush()
    log_event(
        db, users["principal"], "application.create", "Application", application.id,
        details={"candidate_id": candidate.id, "opening_id": opening.id, "note": "internal transfer"},
    )

    advance(db, application, users["principal"], ApplicationStage.screening)

    # No screening interview is recorded -- the chairman overrides the gate for this internal transfer.
    advance(
        db, application, users["chairman"], ApplicationStage.who_interview,
        override_reason="Internal transfer from Accounts Assistant with 2 years of in-school track "
        "record; waiving the formal phone screening.",
    )

    who = Interview(
        application=application, interview_type=InterviewType.who, interviewer=users["hr"],
        status=InterviewStatus.completed,
        notes="Already familiar with our systems from the Accounts Assistant role. Proud of catching a "
        "double-booked vendor payment last year. Wants to move up for the growth, not leaving anything behind.",
        conducted_at=days_ago(30),
    )
    db.add(who)
    db.flush()
    log_event(
        db, users["principal"], "interview.assign", "Interview", who.id,
        details={"interview_type": "who", "interviewer_id": users["hr"].id},
    )
    log_event(db, users["hr"], "interview.complete", "Interview", who.id)

    ref1 = Reference(
        application=application, referee_name="Sunita Iyer (as former supervisor)",
        referee_relationship=RefereeRelationship.former_manager, status=ReferenceStatus.completed,
        notes="Supervised Suresh directly in his Accounts Assistant role for 2 years. Meticulous, flags "
        "issues early, ready for more responsibility.",
        conducted_by_id=users["hr"].id, completed_at=days_ago(26),
    )
    ref2 = Reference(
        application=application, referee_name="Nisha Bhatt (finance peer)",
        referee_relationship=RefereeRelationship.peer, status=ReferenceStatus.completed,
        notes="We cross-check each other's entries. Suresh is the one who usually catches my mistakes, "
        "not the other way around.",
        conducted_by_id=users["hr"].id, completed_at=days_ago(25),
    )
    db.add_all([ref1, ref2])
    db.flush()
    log_event(db, users["hr"], "reference.add", "Reference", ref1.id, details={"referee_name": ref1.referee_name})
    log_event(db, users["hr"], "reference.complete", "Reference", ref1.id)
    log_event(db, users["hr"], "reference.add", "Reference", ref2.id, details={"referee_name": ref2.referee_name})
    log_event(db, users["hr"], "reference.complete", "Reference", ref2.id)

    advance(db, application, users["principal"], ApplicationStage.focused)

    focused = Interview(
        application=application, interview_type=InterviewType.focused, interviewer=users["hr"],
        status=InterviewStatus.completed,
        notes="Walked through last year's month-end close, which he closed in 3 working days, and the "
        "vendor overpayment catch in detail.",
        conducted_at=days_ago(20),
    )
    db.add(focused)
    db.flush()
    log_event(
        db, users["principal"], "interview.assign", "Interview", focused.id,
        details={"interview_type": "focused", "interviewer_id": users["hr"].id},
    )
    ratings = [
        Rating(interview=focused, scorecard_item=item1, grade=Grade.A,
               evidence="Closed last month-end in 3 working days, down from 7 the year before."),
        Rating(interview=focused, scorecard_item=item2, grade=Grade.A,
               evidence="Caught a vendor overpayment of 40,000 rupees during a routine reconciliation "
               "before it was paid out twice."),
    ]
    db.add_all(ratings)
    db.flush()
    log_event(db, users["hr"], "interview.complete", "Interview", focused.id)

    advance(db, application, users["principal"], ApplicationStage.references)
    clear_safeguarding(db, application, users, days_back=15)

    advance(db, application, users["principal"], ApplicationStage.decision)

    decision = Decision(
        application=application, outcome=DecisionOutcome.hire, overall_grade=Grade.A,
        rationale="Proven track record in the Accounts Assistant role, strong references from his direct "
        "supervisor and a peer, and clear evidence of catching costly errors early.",
        decided_by_id=users["principal"].id, decided_at=days_ago(14),
    )
    db.add(decision)
    application.decision = decision
    db.flush()
    log_event(db, users["principal"], "decision.record", "Decision", decision.id, details={"outcome": "hire"})

    advance(db, application, users["principal"], ApplicationStage.offer)

    sell_plan = SellPlan(
        application=application,
        fit="Internal promotion recognising two years of strong work -- framed as a natural next step, "
        "not a new job search.",
        family="No relocation needed; same commute.",
        freedom="More ownership over vendor reconciliation, less day-to-day oversight.",
        fortune="A meaningful pay increase that reflects the Officer-level responsibility.",
        fun="Keeps his seat next to the rest of the finance team he already works well with.",
    )
    db.add(sell_plan)
    application.sell_plan = sell_plan
    db.flush()
    log_event(db, users["principal"], "sell_plan.record", "SellPlan", sell_plan.id)

    advance(db, application, users["principal"], ApplicationStage.hired)
    return application


# --- Pre-generated AIOutput rows ------------------------------------------


def seed_ai_outputs(db, users, maths_items, bus_opening, priya_application) -> None:
    """Hand-written AI outputs so the demo never needs a live call to show the
    caching path. These are written by hand, not produced by calling the API.
    """
    from app.models.ai_outputs import AIOutput

    rows = []

    bus_brief = "Drives a fixed morning and afternoon route, keeps the vehicle roadworthy, and lets parents know promptly about delays."
    bus_input = _scorecard_draft_input(bus_opening, bus_brief)
    bus_output = {
        "mission": "Get every student to and from school safely, on time, and with a calm ride.",
        "outcomes": [
            {
                "title": "On-time route completion",
                "description": "Completes the assigned morning and afternoon route within the scheduled window.",
                "measure": "Percentage of trips completed on schedule each month",
            },
            {
                "title": "Zero preventable incidents",
                "description": "No at-fault accidents or safety violations over a school term.",
                "measure": "Incident log reviewed each term",
            },
            {
                "title": "Proactive delay communication",
                "description": "Notifies the transport coordinator and affected parents as soon as a delay is known.",
                "measure": "Time between delay start and parent notification",
            },
        ],
        "competencies": [
            {"title": "Defensive driving", "description": "Anticipates hazards and keeps a safe following distance in all conditions."},
            {"title": "Vehicle upkeep", "description": "Completes the daily pre-trip inspection checklist and reports issues before they become breakdowns."},
            {"title": "Calm with students", "description": "Keeps order on the bus without escalating minor misbehaviour."},
            {"title": "Reliability", "description": "Shows up on time, every day, with a plan for when that is not possible."},
        ],
    }
    rows.append(("scorecard_draft", bus_input, prompts.SCORECARD_DRAFT_PROMPT_VERSION, bus_output, "RoleOpening", bus_opening.id))

    fq_input = _focused_questions_input(maths_items, True)
    fq_output = {
        "questions": [
            "Walk me through how you would track which students are falling behind benchmark, week to week.",
            "Describe a time a lesson plan deadline slipped. What happened and what did you change afterwards?",
            "A student keeps distracting their table group. What do you do in the moment, and what do you do afterwards?",
            "A parent emails angry about a grade. Walk me through your reply, start to finish.",
        ],
        "demo_lesson_brief": "Teach a 15-minute sample lesson introducing linear equations to a small group, as if it were the first lesson on the topic.",
    }
    rows.append(("focused_questions", fq_input, prompts.FOCUSED_QUESTIONS_PROMPT_VERSION, fq_output, "RoleOpening", priya_application.opening_id))

    evidence_notes = (
        "She managed a class of 35 and raised benchmark scores by 15 points last term. She also ran an "
        "after-school coding club on Thursdays. When a student was disruptive, she quietly moved them to "
        "the front row rather than calling them out."
    )
    evidence_input = _evidence_map_input(evidence_notes, maths_items)
    evidence_output = {
        "items": [
            {"scorecard_item_title": "Benchmark mastery", "quotes": ["raised benchmark scores by 15 points last term"]},
            {"scorecard_item_title": "Lesson plans on time", "quotes": []},
            {"scorecard_item_title": "Classroom management",
             "quotes": ["managed a class of 35", "she quietly moved them to the front row rather than calling them out"]},
            {"scorecard_item_title": "Parent communication", "quotes": []},
        ],
    }
    rows.append(("evidence_map", evidence_input, prompts.EVIDENCE_MAPPING_PROMPT_VERSION, evidence_output, "Application", priya_application.id))

    ds_input = _decision_summary_input(ratings_text_for(priya_application), references_text_for(priya_application))
    ds_output = {
        "summary": "Priya's benchmark mastery and parent communication were both rated A, with specific "
        "evidence: a 15-point benchmark improvement at her prior school and a concrete two-step plan for "
        "an upset parent call. Classroom management was rated A in the focused interview and B in the demo "
        "lesson, where one student briefly went off-task. Lesson-plan timeliness was rated B after she "
        "mentioned missing a Friday deadline twice this year. Her former manager described her as reliable "
        "under pressure and said she would rehire her without hesitation; a peer reference was positive "
        "with a minor note about running over the bell.",
    }
    rows.append(("decision_summary", ds_input, prompts.DECISION_SUMMARY_PROMPT_VERSION, ds_output, "Application", priya_application.id))

    for task, input_data, prompt_version, output, entity_type, entity_id in rows:
        input_hash = compute_input_hash({**input_data, "prompt_version": prompt_version})
        record = AIOutput(
            task=task, input_hash=input_hash, provider="seed", model="hand-written",
            prompt_version=prompt_version, output=output,
        )
        db.add(record)
        db.flush()
        log_event(
            db, None, f"ai.{task}", entity_type, entity_id,
            details={"provider": "seed", "model": "hand-written", "cached": False, "seeded": True},
        )


def run_seed() -> None:
    db = SessionLocal()
    try:
        wipe(db)
        users = make_users(db)

        maths_opening, maths_scorecard, maths_items = make_maths_opening(db, users)
        priya_application = hire_priya(db, maths_opening, maths_items, users)
        block_rahul(db, maths_opening, maths_items, users)
        partial_anjali(db, maths_opening, users)
        reject_vikram(db, maths_opening, users)

        bus_opening = make_bus_driver_opening(db, users)
        make_accounts_opening_with_override(db, users)

        seed_ai_outputs(db, users, maths_items, bus_opening, priya_application)

        db.commit()
        print("Seed complete:")
        print(f"  Users: {db.query(User).count()}")
        print(f"  Openings: {db.query(RoleOpening).count()}")
        print(f"  Candidates: {db.query(Candidate).count()}")
        print(f"  Applications: {db.query(Application).count()}")
        print(f"\nNormal-mode login (any seeded user's email, shared password): {DEMO_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
