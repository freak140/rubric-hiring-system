# Rubric build plan (docs/PROMPT_4.md)

Re-read this file and CLAUDE.md whenever resuming work or recovering from lost context.

## Phase 0: Verify
- [x] `alembic current` shows initial migration applied on Neon
- [x] Top bar shows "Rubric" + tagline "Every hire, one standard"

## Phase 1: Schema fixes, rules engine, audit, tests
- [x] Migration "cascade and candidate email" (Scorecard->ScorecardItem CASCADE, RoleOpening->Scorecard CASCADE, Candidate.email unique)
- [x] CLAUDE.md rule: hiring history (Application->RoleOpening, Application->Candidate) is never hard-deleted (RESTRICT)
- [x] Candidate email validator (lowercase + strip) on the model
- [x] app/services/gates.py: GateResult dataclass + 6 forward gates + reject/withdraw rule
- [x] app/services/audit.py: log_event, append-only
- [x] app/services/workflow.py: advance_application, release_interviewer, approve_scorecard/assert_scorecard_editable, create_default_safeguarding_checks
- [x] app/services/visibility.py: can_view_ratings
- [x] DEFAULT_SAFEGUARDING_CHECKS in app/config.py
- [x] pytest tests for gates + workflow overrides (no DB)
- [x] Run full test suite, smoke test app, commit "Phase 1: ..."

## Phase 2: Demo identity and permissions
- [x] Working role switcher (cookie rubric_user_id), get_current_user dependency (defaults to chairman)
- [x] "Demo mode: no real logins" badge
- [x] app/services/permissions.py with per-role capability checks
- [x] Server-side enforcement + UI hiding of disallowed actions (groundwork now; applied as each Phase 3 screen is built)
- [x] Tests, smoke test, commit "Phase 2: ..."

## Phase 3: Core workflow screens
- [x] Shared UI: stage tracker, "Why this step" notes, gate panel, flash messages
- [x] Openings list + filters + create form
- [x] Opening detail: scorecard editor + approve + pipeline by stage
- [x] Add candidate to opening (dedupe by email)
- [x] Application page: tracker, gate panel, advance/reject/withdraw, chairman override
- [x] Interview assignment + screening/who/focused/demo forms + release action
- [x] Ratings matrix (visibility-aware)
- [x] References: named referees + reference interview form + complete
- [x] Safeguarding checklist (auto-created at references stage)
- [x] Decision form (outcome/grade/rationale) w/ ratings+references shown
- [x] Sell plan form (Fit/Family/Freedom/Fortune/Fun)
- [x] Decision record (printable)
- [x] My interviews page
- [x] Tests, smoke test, commit "Phase 3: ..."

## Phase 4: Chairman dashboard
- [x] Openings + stage counts, hires to date, avg days to hire
- [x] Compliance panel: overrides, released interviewers, stale applications (14+ days)
- [x] Audit log page with filters
- [x] Tests, smoke test, commit "Phase 4: ..."

## Phase 5: AI assistance
- [ ] app/services/ai/client.py: Groq -> Gemini fallback, retry/backoff, JSON validation retry, clear failure error
- [ ] AIOutput caching by (task, sha256 input, prompt_version)
- [ ] app/services/ai/prompts.py: versioned prompts, "never grades/scores/ranks/recommends"
- [ ] Feature: draft scorecard
- [ ] Feature: focused interview questions (+ demo lesson brief)
- [ ] Feature: evidence mapping (quote verification against notes, no grade field)
- [ ] Feature: decision summary (neutral, no recommendation)
- [ ] AI_ENABLED gating in UI, audit log on every use, "AI draft: review before use" label
- [ ] Tests with mocked API: quote guard, cache hit, provider fallback
- [ ] scripts/eval_evidence.py with 3 sample notes + precision/recall
- [ ] Tests, smoke test, commit "Phase 5: ..."

## Phase 6: Demo data, reset and demo guide
- [ ] scripts/seed.py: idempotent TRUNCATE + realistic seed (users, 3 openings, 4+ candidates per spec)
- [ ] Pre-generated AIOutput rows for seeded AI features (no live calls)
- [ ] POST /demo/reset with confirmation step
- [ ] Home page becomes demo guide with 5-step tour + direct links
- [ ] Tests, smoke test, commit "Phase 6: ..."

## Phase 7: Deployment prep (no deploy)
- [ ] render.yaml (web service, singapore, free, build/start commands, health check, env vars sync:false)
- [ ] Confirm postgresql+psycopg:// + sslmode=require works
- [ ] README: setup, tests, seeding, Render deploy steps, env var table
- [ ] Commit "Phase 7: ..."

## Phase 8: Submission docs and final check
- [ ] docs/architecture.md with Mermaid diagram + explanations
- [ ] docs/overview.md (<=300 words)
- [ ] Final pass: full tests, reseed, walk 5-step tour via HTTP, fix issues
- [ ] BUILD_LOG.md: what works / limitations / what's next
- [ ] Commit "Phase 8: ..."
