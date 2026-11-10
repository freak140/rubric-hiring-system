"""Pydantic schemas the AI's JSON output is validated against.

None of these have a grade, score, rank, or recommendation field -- that is
enforced by the schema shape itself, not just by the prompt.
"""

from pydantic import BaseModel, Field


class ScorecardOutcomeDraft(BaseModel):
    title: str
    description: str
    measure: str


class ScorecardCompetencyDraft(BaseModel):
    title: str
    description: str


class ScorecardDraft(BaseModel):
    mission: str
    outcomes: list[ScorecardOutcomeDraft] = Field(min_length=3, max_length=8)
    competencies: list[ScorecardCompetencyDraft] = Field(min_length=4, max_length=8)


class FocusedQuestions(BaseModel):
    questions: list[str] = Field(min_length=3)
    demo_lesson_brief: str | None = None


class EvidenceMappingItem(BaseModel):
    scorecard_item_title: str
    quotes: list[str]


class EvidenceMapping(BaseModel):
    items: list[EvidenceMappingItem]


class DecisionSummary(BaseModel):
    summary: str
