Build the rest of Rubric end to end. Work autonomously through the phases below, in order. Follow CLAUDE.md at all times.

HOW TO WORK
- First save this prompt verbatim as docs/PROMPT_4.md. Then write docs/PLAN.md listing every phase as a checklist and tick items as you finish them. Re-read PLAN.md and CLAUDE.md whenever you resume or lose context.
- Keep docs/BUILD_LOG.md as you go. For each phase record: what you built, problems you hit and how you fixed them, and a "Decisions I made" list for anything this prompt does not specify. For those, choose the simplest option consistent with CLAUDE.md and keep going; do not stop to ask.
- After each phase: run the full test suite, start the app and smoke-test the new pages (no errors), then make a git commit "Phase N: <name>". Initialise git first if needed; never commit .env.
- Schema changes only through new Alembic migrations; never edit a migration that has been applied.
- Stop and ask me only before something destructive that this prompt does not call for (for example dropping tables or data in Neon other than the demo reset).
- No new dependencies beyond what is in requirements.txt, plus pytest as a dev dependency.

PHASE 0: VERIFY
- Confirm the initial migration is applied on Neon (alembic current) and the top bar shows "Rubric" with the tagline "Every hire, one standard". Fix either if not.

PHASE 1: SCHEMA FIXES, RULES ENGINE, AUDIT, TESTS
A. New migration "cascade and candidate email": Scorecard -> ScorecardItem and RoleOpening -> Scorecard become ON DELETE CASCADE. Application -> RoleOpening and Application -> Candidate stay RESTRICT, because hiring history is never hard-deleted (add this rule to CLAUDE.md). Candidate.email becomes unique; lowercase and strip it before saving with a SQLAlchemy validator.
B. app/services/gates.py: pure functions with no database access. They take an Application with its relationships loaded and return a GateResult dataclass: allowed (bool) and reasons (list of plain-English strings saying what is missing; empty when allowed). Constants at the top: MIN_REFERENCES = 2, MIN_FOCUSED_INTERVIEWS = 1. Stages move strictly forward one step at a time:
  1. sourced -> screening: the opening's scorecard exists, is approved, and has at least one outcome and one competency.
  2. screening -> who_interview: a completed screening interview with screening_outcome = pass.
  3. who_interview -> focused: a completed Who interview, and at least MIN_REFERENCES references named (any status), at least one a former_manager.
  4. focused -> references: at least MIN_FOCUSED_INTERVIEWS completed focused or demo_lesson interviews; every focused or demo_lesson interview is completed or released (released ones need a release_reason); every completed focused or demo_lesson interview has a rating for every scorecard item, each with non-empty evidence.
  5. references -> decision: at least MIN_REFERENCES completed references including a former_manager; at least one safeguarding check exists (an empty list must NOT pass); every check is cleared.
  6. decision -> offer: a Decision exists with outcome = hire and a non-empty rationale.
  7. offer -> hired: no gate.
  Moving to rejected or withdrawn is allowed from any active stage but needs a reason. hired, rejected and withdrawn are final.
C. app/services/audit.py: log_event(db, actor, action, entity_type, entity_id, details=None, is_override=False, override_reason=None). Append-only: no update or delete functions anywhere.
D. app/services/workflow.py:
  - advance_application(db, application, actor, target_stage, reason=None, override_reason=None): checks the move is the next stage (or rejected/withdrawn), runs the gate, applies the change, writes an audit event with the old and new stage, and returns the GateResult. If the gate fails, nothing changes unless override_reason is given AND the actor is a chairman; then the move happens and the audit event has is_override=True with the gate's reasons in details. Anyone else attempting an override is refused.
  - release_interviewer(db, interview, actor, reason): only the opening's hiring manager or the chairman; reason required; logged.
  - approve_scorecard and assert_scorecard_editable: an approved scorecard cannot be edited; both logged.
  - create_default_safeguarding_checks(db, application) from a DEFAULT_SAFEGUARDING_CHECKS list in config: Identity verification; Criminal record / police check; Previous employer verification; Safeguarding declaration signed.
E. app/services/visibility.py: can_view_ratings(user, interview). An interviewer sees other interviewers' ratings on an application only after submitting their own; chairman, hr and the opening's hiring manager always can.
F. Pytest tests with in-memory model objects, no database: every gate passing and failing, plus: one reference only (blocked); two references but no former manager (blocked); zero safeguarding checks (blocked); a released interviewer without a reason (blocked); an override by a principal (refused); an override by the chairman without a reason (refused); an override by the chairman with a reason (allowed).

PHASE 2: DEMO IDENTITY AND PERMISSIONS
- Make the role switcher work: a dropdown of seeded users (name and role); choosing one sets a "rubric_user_id" cookie. A get_current_user dependency reads it and defaults to the chairman. Show a small "Demo mode: no real logins" badge.
- app/services/permissions.py (never in templates):
  chairman: everything, including overrides, the dashboard and the audit log.
  principal: create openings; edit and approve scorecards for openings they manage; add candidates; assign interviewers; record decisions and sell plans for their openings.
  hr: add candidates; manage references and safeguarding checks; view everything.
  interviewer: only their assigned interviews and rating forms.
  Hide actions a user cannot take, and enforce the same checks server-side.

PHASE 3: CORE WORKFLOW SCREENS (Jinja + HTMX + Tailwind, clean and readable on laptop and phone)
Shared UI: a stage tracker (Scorecard, Screening, Who interview, Focused, References, Decision, Offer) on every application page; a collapsible "Why this step" note on each stage explaining in 2-3 sentences what the Who method says and why the gate exists; a gate panel listing the reasons from gates.py when a move is blocked; flash messages for success and errors. Every state change goes through app/services and is audit-logged.
1. Openings list (filter by status and type) and a Create opening form.
2. Opening detail: scorecard editor (mission; add, edit, reorder and delete outcomes with measures, and competencies) with an Approve button; read-only once approved, showing "Approved by X on <date>". Candidate pipeline for the opening, grouped by stage.
3. Add a candidate to an opening; reuse the existing candidate when the email matches; record the source.
4. Application page: stage tracker, gate panel, Advance button, Reject and Withdraw with a reason, and a chairman-only Override form (reason required) that appears only when the gate is blocked.
5. Interviews: assign interviewers by type. Screening form (notes, pass or fail). Who interview form showing the book's chronological questions as a guide for each job: What were you hired to do? What accomplishments are you most proud of? What were some low points? Who were the people you worked with, and how would your boss rate you? Why did you leave? Notes field, plus a way to add the references the candidate names. Focused and demo lesson form: notes plus an A/B/C grade and required evidence for every scorecard item. Release interviewer action with a reason (hiring manager or chairman).
6. Ratings matrix on the application page (scorecard items by interviewer), respecting can_view_ratings.
7. References: named referees with their relationship; a reference interview form showing the book's questions as a guide: In what context did you work with the person? What were their biggest strengths? What were their biggest areas for improvement back then? How would you rate their overall performance on a 1-10 scale, and why? The candidate mentioned they struggled with ___; can you tell me more? Notes, then mark completed.
8. Safeguarding checklist: created automatically when an application enters the references stage; each check can be cleared or flagged, with notes and who verified it.
9. Decision form: outcome, overall grade A/B/C, rationale (required), with the ratings matrix and reference notes shown beside it.
10. Sell plan: five text areas (Fit, Family, Freedom, Fortune, Fun) with a one-line hint each.
11. Decision record: a printable page compiling the scorecard, every interview, ratings with evidence, references, safeguarding checks, the decision and rationale, and the application's audit trail. This is what the Chairman reads to explain any hire.
12. "My interviews" page for interviewers.

PHASE 4: CHAIRMAN DASHBOARD
- Openings with candidate counts per stage; hires to date; average days from opening to hire.
- Compliance panel: every override (who, when, which gate, the reasons it bypassed, the stated reason); released interviewers with reasons; applications with no activity for 14+ days.
- Audit log page with filters (opening, user, action, overrides only).

PHASE 5: AI ASSISTANCE (app/services/ai/)
- client.py: one function that calls an OpenAI-compatible chat API with the openai package, trying providers in order: Groq (base_url https://api.groq.com/openai/v1, GROQ_API_KEY, GROQ_MODEL), then Gemini (base_url https://generativelanguage.googleapis.com/v1beta/openai/, GEMINI_API_KEY, GEMINI_MODEL). Never hard-code model names. On a rate-limit or server error, back off and retry once, then move to the next provider. Request JSON output, validate it with a Pydantic schema, and retry once with the validation error if invalid. If everything fails, raise a clear error the UI shows as "AI is unavailable right now. Please continue manually."
- Caching: before calling, look up AIOutput by task plus a sha256 of the normalised input and prompt version; store every successful result with provider, model and prompt_version.
- prompts.py: versioned prompt templates with PROMPT_VERSION constants. Every system prompt states that the model never grades, scores, ranks or recommends candidates.
- Features, each a button shown only when AI_ENABLED is true, output labelled "AI draft: review before use", and each use audit-logged:
  1. Draft scorecard: from the opening's title, type, department and a short brief, produce a mission, 3-8 outcomes each with a measure, and 4-8 competencies, inserted as draft items the principal edits and approves.
  2. Focused interview questions generated from the scorecard items (plus a demo lesson brief for teaching roles).
  3. Evidence mapping: from an interview's notes and the scorecard items, return for each item the verbatim quotes from the notes that are relevant, or "no evidence found". Shown beside the rating form. The code must discard any quote that is not an exact substring of the notes, and the schema has no grade or score field.
  4. Decision summary: a neutral summary of the evidence, ratings and references for the decision page, with no recommendation.
- Tests with the API mocked: the quote-verification guard, the cache-hit path, and provider fallback.
- scripts/eval_evidence.py: runs evidence mapping on 3 sample interview notes with hand-labelled expected items and prints per-item precision and recall.

PHASE 6: DEMO DATA, RESET AND DEMO GUIDE
- scripts/seed.py: wipes all tables (TRUNCATE ... RESTART IDENTITY CASCADE) and seeds a realistic school. Running it twice gives the same result.
  Users: a chairman, a principal (the hiring manager), 3 interviewers including a senior teacher, and an HR coordinator, with realistic Indian names.
  Openings:
  - Grade 8 Mathematics Teacher (teaching), approved scorecard, four candidates: one hired with a complete record (all interviews, ratings with evidence, 2 completed references including a former manager, all checks cleared, decision, sell plan); one at the references stage blocked with only one completed reference; one at the Who interview stage; one rejected at screening with notes.
  - School Bus Driver (non-teaching): scorecard in draft, awaiting approval.
  - Accounts Officer (non-teaching): a completed hire where the chairman overrode the screening gate for an internal transfer candidate, with the reason logged.
  Write realistic interview notes and reference notes. Insert pre-generated AIOutput rows for the seeded AI features, written by you rather than by calling the API, so the demo works with no live AI calls.
- A "Reset demo data" button (POST /demo/reset, with a confirmation step) that reruns the seed.
- The home page becomes the demo guide: what Rubric is, the four Who stages in one line each, and a 5-step tour with direct links: (1) as the principal, open the Maths opening and try to advance the candidate with one reference; (2) as an interviewer, submit ratings and see the others' ratings appear; (3) create a new opening and draft its scorecard with AI; (4) as the chairman, open the dashboard and find the override; (5) open a full decision record.

PHASE 7: DEPLOYMENT PREP (do not deploy)
- render.yaml: one Python web service, region singapore, plan free, build "pip install -r requirements.txt", start "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT", health check path /health, env vars listed with sync: false for secrets.
- Make sure the database connection works with the postgresql+psycopg:// prefix and Neon's SSL requirement.
- README: local setup, running tests, seeding, step-by-step deployment to Render, and every env var.

PHASE 8: SUBMISSION DOCS AND FINAL CHECK
- docs/architecture.md: a Mermaid diagram of the components (browser; FastAPI routes; services: permissions, gates, workflow, audit, visibility, AI; Postgres on Neon; Groq; Gemini; Render) with a short explanation of each.
- docs/overview.md: a draft overview of at most 300 words covering the problem, who it is for, what was built, why these choices (enforced gates, human-only judgement, AI as assistant, fail-soft AI, sustainability), and the stated assumptions.
- Final pass: run all tests, run the seed, walk through the 5-step tour yourself with HTTP requests, and fix anything broken. Finish BUILD_LOG.md with: what works, known limitations, and what you would do with more time.
