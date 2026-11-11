"""AI-assisted drafting features. Every result here is a draft a human reviews
before it has any effect -- these functions never write to application data,
they only return drafted content for a route to show or apply.

Each feature exposes its input-dict builder (_*_input) so other code --
notably scripts/seed.py, which inserts pre-generated AIOutput rows -- can
compute the exact same cache key without duplicating the shape by hand.
"""

from sqlalchemy.orm import Session

from app.models.applications import Application
from app.models.openings import RoleOpening
from app.models.scorecards import ScorecardItem
from app.services.ai import prompts
from app.services.ai.client import AICallResult, call_llm_cached, peek_cache
from app.services.ai.schemas import DecisionSummary, EvidenceMapping, FocusedQuestions, ScorecardDraft


def rated_interviews_for(application: Application) -> list:
    """The application's focused/demo-lesson interviews -- the ones that carry ratings."""
    return [i for i in application.interviews if i.interview_type.value in ("focused", "demo_lesson")]


def ratings_text_for(application: Application) -> str:
    lines = []
    for interview in rated_interviews_for(application):
        for rating in interview.ratings:
            lines.append(f"{rating.scorecard_item.title}: grade {rating.grade.value} -- {rating.evidence}")
    return "\n".join(lines) or "No ratings recorded yet."


def references_text_for(application: Application) -> str:
    lines = [
        f"{r.referee_name} ({r.referee_relationship.value}): {r.notes}"
        for r in application.references
        if r.status.value == "completed" and r.notes
    ]
    return "\n".join(lines) or "No completed references yet."


def _scorecard_draft_input(opening: RoleOpening, brief: str) -> dict:
    return {
        "title": opening.title,
        "role_type": opening.role_type.value,
        "department": opening.department,
        "brief": brief,
    }


def draft_scorecard(db: Session, opening: RoleOpening, brief: str) -> AICallResult:
    input_data = _scorecard_draft_input(opening, brief)
    return call_llm_cached(
        db,
        task="scorecard_draft",
        input_data=input_data,
        prompt_version=prompts.SCORECARD_DRAFT_PROMPT_VERSION,
        system_prompt=prompts.SCORECARD_DRAFT_SYSTEM_PROMPT,
        user_prompt=prompts.scorecard_draft_user_prompt(opening.title, opening.role_type.value, opening.department, brief),
        schema=ScorecardDraft,
    )


def _focused_questions_input(scorecard_items: list[ScorecardItem], is_teaching: bool) -> dict:
    items_payload = [{"kind": i.kind.value, "title": i.title, "description": i.description} for i in scorecard_items]
    return {"items": items_payload, "is_teaching": is_teaching}


def generate_focused_questions(db: Session, scorecard_items: list[ScorecardItem], is_teaching: bool) -> AICallResult:
    input_data = _focused_questions_input(scorecard_items, is_teaching)
    return call_llm_cached(
        db,
        task="focused_questions",
        input_data=input_data,
        prompt_version=prompts.FOCUSED_QUESTIONS_PROMPT_VERSION,
        system_prompt=prompts.FOCUSED_QUESTIONS_SYSTEM_PROMPT,
        user_prompt=prompts.focused_questions_user_prompt(input_data["items"], is_teaching),
        schema=FocusedQuestions,
    )


def peek_focused_questions(db: Session, scorecard_items: list[ScorecardItem], is_teaching: bool) -> FocusedQuestions | None:
    input_data = _focused_questions_input(scorecard_items, is_teaching)
    return peek_cache(db, "focused_questions", input_data, prompts.FOCUSED_QUESTIONS_PROMPT_VERSION, FocusedQuestions)


def _verified_quotes(quotes: list[str], notes: str) -> list[str]:
    """Discard any quote that is not an exact substring of the notes."""
    return [q for q in quotes if q and q in notes]


def _evidence_map_input(notes: str, scorecard_items: list[ScorecardItem]) -> dict:
    items_payload = [{"title": i.title, "description": i.description} for i in scorecard_items]
    return {"notes": notes, "items": items_payload}


def map_evidence(db: Session, notes: str, scorecard_items: list[ScorecardItem]) -> AICallResult:
    input_data = _evidence_map_input(notes, scorecard_items)
    result = call_llm_cached(
        db,
        task="evidence_map",
        input_data=input_data,
        prompt_version=prompts.EVIDENCE_MAPPING_PROMPT_VERSION,
        system_prompt=prompts.EVIDENCE_MAPPING_SYSTEM_PROMPT,
        user_prompt=prompts.evidence_mapping_user_prompt(notes, input_data["items"]),
        schema=EvidenceMapping,
    )
    mapping: EvidenceMapping = result.output
    for item in mapping.items:
        item.quotes = _verified_quotes(item.quotes, notes)
    return result


def _decision_summary_input(ratings_text: str, references_text: str) -> dict:
    return {"ratings_text": ratings_text, "references_text": references_text}


def summarize_decision(db: Session, ratings_text: str, references_text: str) -> AICallResult:
    input_data = _decision_summary_input(ratings_text, references_text)
    return call_llm_cached(
        db,
        task="decision_summary",
        input_data=input_data,
        prompt_version=prompts.DECISION_SUMMARY_PROMPT_VERSION,
        system_prompt=prompts.DECISION_SUMMARY_SYSTEM_PROMPT,
        user_prompt=prompts.decision_summary_user_prompt(ratings_text, references_text),
        schema=DecisionSummary,
    )


def peek_decision_summary(db: Session, ratings_text: str, references_text: str) -> DecisionSummary | None:
    input_data = _decision_summary_input(ratings_text, references_text)
    return peek_cache(db, "decision_summary", input_data, prompts.DECISION_SUMMARY_PROMPT_VERSION, DecisionSummary)
