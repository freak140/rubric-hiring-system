# Build log

## Phase 0: Verify

- `alembic current` on the Neon database: confirmed at `14c255d65204 (head)`, the "initial schema" migration from the previous session. No fix needed.
- Top bar already reads "Rubric" with tagline "Every hire, one standard" (done in the previous session). No fix needed.
- Initialised git in the project root (no repo existed yet) and set a local (repo-scoped, not global) `user.name`/`user.email` so commits can be made.

Decisions I made:
- Used the account owner's own name/email for local git commit identity, scoped to this repo only, since no git identity existed anywhere on the machine and the prompt requires per-phase commits.
