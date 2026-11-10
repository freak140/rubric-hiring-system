"""Versioned prompt templates.

Every prompt version here is part of the cache key in app.services.ai.client
(task + prompt_version + input hash) -- bump the *_PROMPT_VERSION constant
whenever a prompt's wording changes meaningfully, so old cached rows stop
being served under a new prompt.
"""

NEVER_JUDGES = (
    "You are an assistant helping a school's hiring team. You never grade, score, rank, "
    "or recommend candidates -- that judgement belongs to humans. You only draft, structure, "
    "and flag gaps. Always respond with a single JSON object matching the schema described, "
    "with no extra commentary."
)

SCORECARD_DRAFT_PROMPT_VERSION = "v1"
SCORECARD_DRAFT_SYSTEM_PROMPT = (
    NEVER_JUDGES
    + " Your task is to draft a scorecard for a role: a one or two sentence mission, "
    "3 to 8 outcomes (each with how success is measured), and 4 to 8 competencies."
)


def scorecard_draft_user_prompt(title: str, role_type: str, department: str, brief: str) -> str:
    return (
        f"Role title: {title}\n"
        f"Role type: {role_type}\n"
        f"Department: {department}\n"
        f"Brief: {brief}\n\n"
        'Return JSON: {"mission": str, "outcomes": [{"title": str, "description": str, '
        '"measure": str}, ...], "competencies": [{"title": str, "description": str}, ...]}'
    )


FOCUSED_QUESTIONS_PROMPT_VERSION = "v1"
FOCUSED_QUESTIONS_SYSTEM_PROMPT = (
    NEVER_JUDGES
    + " Your task is to turn scorecard items into focused interview questions that probe for "
    "real evidence of each competency or outcome."
)


def focused_questions_user_prompt(scorecard_items: list[dict], is_teaching: bool) -> str:
    items_text = "\n".join(f"- ({i['kind']}) {i['title']}: {i['description']}" for i in scorecard_items)
    demo_note = (
        "This is a teaching role: also draft a short demo lesson brief (topic and what to look for)."
        if is_teaching
        else "This is not a teaching role: leave demo_lesson_brief null."
    )
    return (
        f"Scorecard items:\n{items_text}\n\n{demo_note}\n\n"
        'Return JSON: {"questions": [str, ...], "demo_lesson_brief": str or null}'
    )


EVIDENCE_MAPPING_PROMPT_VERSION = "v2"
EVIDENCE_MAPPING_SYSTEM_PROMPT = (
    NEVER_JUDGES
    + " Your task is to find verbatim quotes in interview notes that are relevant evidence for "
    "each scorecard item. Only use exact text from the notes -- never paraphrase or invent a "
    "quote. If nothing in the notes is relevant to an item, return an empty list of quotes for it."
)


def evidence_mapping_user_prompt(notes: str, scorecard_items: list[dict]) -> str:
    items_text = "\n".join(f"- {i['title']}: {i['description']}" for i in scorecard_items)
    return (
        f"Interview notes:\n{notes}\n\nScorecard items:\n{items_text}\n\n"
        'Return JSON: {"items": [{"scorecard_item_title": str, "quotes": [str, ...]}, ...]} '
        "with exactly one entry per scorecard item, in the same order given above. "
        'scorecard_item_title must be copied verbatim from the part before the colon in each '
        'scorecard item above (e.g. "Benchmark mastery", never "Benchmark mastery: 90% of ..."). '
        "Quotes must be copied exactly from the notes above."
    )


DECISION_SUMMARY_PROMPT_VERSION = "v1"
DECISION_SUMMARY_SYSTEM_PROMPT = (
    NEVER_JUDGES
    + " Your task is to neutrally summarise the evidence gathered on a candidate -- ratings "
    "with their evidence, and reference notes -- for a human to read before deciding. Do not "
    "state or imply a recommendation, a verdict, or an overall grade."
)


def decision_summary_user_prompt(ratings_text: str, references_text: str) -> str:
    return (
        f"Ratings and evidence:\n{ratings_text}\n\nReference notes:\n{references_text}\n\n"
        'Return JSON: {"summary": str} -- a neutral paragraph summarising the evidence only.'
    )
