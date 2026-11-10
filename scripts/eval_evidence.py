"""Evaluates the evidence-mapping AI feature against 3 hand-labelled samples.

Run: python scripts/eval_evidence.py
Requires AI_ENABLED=true and at least one provider key configured in .env.
Prints per-item precision/recall plus an overall average.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.services.ai.features import map_evidence  # noqa: E402

SAMPLES = [
    {
        "name": "Maths teacher - focused interview",
        "notes": (
            "She managed a class of 35 and raised benchmark scores by 15 points last term. "
            "She also ran an after-school coding club on Thursdays. When a student was disruptive, "
            "she quietly moved them to the front row rather than calling them out."
        ),
        "items": [
            {"title": "Benchmark mastery", "description": "90% of students pass the term-end benchmark test."},
            {"title": "Classroom management", "description": "Keeps a class of 35 engaged and on task."},
        ],
        "expected": {
            "Benchmark mastery": ["raised benchmark scores by 15 points last term"],
            "Classroom management": ["managed a class of 35", "quietly moved them to the front row"],
        },
    },
    {
        "name": "Librarian - demo lesson",
        "notes": (
            "During the sample storytime, she asked open-ended questions after each page, which kept "
            "all 20 students engaged. Circulation records she shared showed a 30% increase in checkouts "
            "this year. She did not mention how she handles book damage or loss."
        ),
        "items": [
            {"title": "Reading engagement", "description": "Runs engaging reading programs for students."},
            {"title": "Collection management", "description": "Maintains and grows the library collection."},
            {"title": "Budget discipline", "description": "Manages the library's annual materials budget."},
        ],
        "expected": {
            "Reading engagement": ["asked open-ended questions after each page"],
            "Collection management": ["a 30% increase in checkouts this year"],
            "Budget discipline": [],
        },
    },
    {
        "name": "Accounts officer - focused interview",
        "notes": (
            "He walked through last year's month-end close process, which he closed in 3 working days, "
            "down from 7. He flagged a vendor overpayment of 40,000 rupees that he caught during a routine "
            "reconciliation. He was vague about his experience with the school's specific accounting software."
        ),
        "items": [
            {"title": "Month-end close speed", "description": "Closes the books accurately within 5 working days."},
            {"title": "Error detection", "description": "Catches discrepancies before they become losses."},
            {"title": "Systems familiarity", "description": "Comfortable with the school's accounting software."},
        ],
        "expected": {
            "Month-end close speed": ["closed in 3 working days, down from 7"],
            "Error detection": ["flagged a vendor overpayment of 40,000 rupees"],
            "Systems familiarity": [],
        },
    },
]


def _quote_matches(a: str, b: str) -> bool:
    return bool(a) and bool(b) and (a in b or b in a)


def _precision_recall(retrieved: list[str], expected: list[str]) -> tuple[float, float]:
    if not retrieved and not expected:
        return 1.0, 1.0
    precision = (
        sum(1 for r in retrieved if any(_quote_matches(r, e) for e in expected)) / len(retrieved)
        if retrieved
        else 1.0
    )
    recall = (
        sum(1 for e in expected if any(_quote_matches(r, e) for r in retrieved)) / len(expected) if expected else 1.0
    )
    return precision, recall


def main() -> None:
    db = SessionLocal()
    overall: list[tuple[float, float]] = []
    try:
        for sample in SAMPLES:
            print(f"\n=== {sample['name']} ===")
            items = [SimpleNamespace(title=i["title"], description=i["description"]) for i in sample["items"]]
            result = map_evidence(db, sample["notes"], items)
            db.commit()
            # Match by position, not by the model's echoed title text: the prompt guarantees
            # one entry per scorecard item in the same order, but models don't always echo
            # the title verbatim (e.g. sometimes "Title: description").
            retrieved_by_position = [item.quotes for item in result.output.items]
            for position, (title, expected) in enumerate(sample["expected"].items()):
                retrieved = retrieved_by_position[position] if position < len(retrieved_by_position) else []
                precision, recall = _precision_recall(retrieved, expected)
                overall.append((precision, recall))
                print(
                    f"  {title}: precision={precision:.2f} recall={recall:.2f} "
                    f"(retrieved={len(retrieved)}, expected={len(expected)})"
                )
    finally:
        db.close()

    if overall:
        avg_p = sum(p for p, _ in overall) / len(overall)
        avg_r = sum(r for _, r in overall) / len(overall)
        print(f"\nOverall: precision={avg_p:.2f} recall={avg_r:.2f} over {len(overall)} scorecard items")


if __name__ == "__main__":
    main()
