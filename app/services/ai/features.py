"""AI-assisted drafting features. Every result here is a draft a human reviews
before it has any effect -- these functions never write to application data,
they only return drafted content for a route to show or apply.
"""

from sqlalchemy.orm import Session

from app.models.openings import RoleOpening
from app.models.scorecards import ScorecardItem
from app.services.ai import prompts
from app.services.ai.client import AICallResult, call_llm_cached, peek_cache
from app.services.ai.schemas import DecisionSummary, EvidenceMapping, FocusedQuestions, ScorecardDraft


def draft_scorecard(db: Session, opening: RoleOpening, brief: str) -> AICallResult:
    input_data = {
        "title": opening.title,
        "role_type": opening.role_type.value,
        "department": opening.department,
        "brief": brief,
    }
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


def map_evidence(db: Session, notes: str, scorecard_items: list[ScorecardItem]) -> AICallResult:
    items_payload = [{"title": i.title, "description": i.description} for i in scorecard_items]
    input_data = {"notes": notes, "items": items_payload}
    result = call_llm_cached(
        db,
        task="evidence_map",
        input_data=input_data,
        prompt_version=prompts.EVIDENCE_MAPPING_PROMPT_VERSION,
        system_prompt=prompts.EVIDENCE_MAPPING_SYSTEM_PROMPT,
        user_prompt=prompts.evidence_mapping_user_prompt(notes, items_payload),
        schema=EvidenceMapping,
    )
    mapping: EvidenceMapping = result.output
    for item in mapping.items:
        item.quotes = _verified_quotes(item.quotes, notes)
    return result


def summarize_decision(db: Session, ratings_text: str, references_text: str) -> AICallResult:
    input_data = {"ratings_text": ratings_text, "references_text": references_text}
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
    input_data = {"ratings_text": ratings_text, "references_text": references_text}
    return peek_cache(db, "decision_summary", input_data, prompts.DECISION_SUMMARY_PROMPT_VERSION, DecisionSummary)
