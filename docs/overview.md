# Overview

**The problem.** School hiring is high-stakes and easy to make on gut feel: a confident interview,
a nice resume, decision made. "Who: The A Method for Hiring" fixes this with a disciplined
sequence -- Scorecard, Source, Select, Sell -- but it only works if actually followed every time,
under deadline pressure.

**Who it's for.** A private K-12 school's hiring team: a principal who owns openings and
scorecards, interviewers who rate structured interviews, HR who manages references and
safeguarding, and a chairman with final visibility and override authority.

**What was built.** Rubric is a server-rendered FastAPI app (Jinja2, HTMX, Tailwind, one Postgres
database) encoding the Who method as an enforced pipeline: no decision without an approved
scorecard, a passed screening, a Who interview with named references, focused interviews with
graded evidence per scorecard item, completed references including a former manager, and cleared
safeguarding checks. Every blocked gate explains what's missing. An optional AI layer drafts
scorecards, interview questions, and evidence summaries -- never grades or recommends -- cached,
audit-logged, with retry-then-fallback across two providers and a clean failure message if both
are down.

**Why these choices.** Gates are enforced in code, not policy, because policies get skipped under
pressure and code doesn't. Judgement stays human: the schemas AI output must match have no grade
or score field, by construction, not just by prompt instruction. AI is strictly an assistant --
every output is labelled "review before use," and the app works fully with it off, keeping the
default cost at zero. A chairman can override any gate, but only with a logged reason, so
exceptions stay visible instead of quietly eroding the standard.

**Assumptions.** Single school, small staff, no real authentication (a demo role switcher stands
in), and no requirement to support concurrent edits to the same record.
