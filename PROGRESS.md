# Progress

## Done

### Phase 1 - safe foundation
- ✅ Alembic migrations replace `create_all` (async env, initial revision,
  startup auto-upgrade, legacy-DB adoption). Upgrade + downgrade tested.
- ✅ Throttling middleware (per-user in-memory anti-spam). Tested.
- ✅ pytest + pytest-asyncio suite: registration happy-path, duplicate active
  (service + DB partial-unique-index), approve/reject (+reason), withdraw,
  re-register after reject.

### Phase 2 - UX / product
- ✅ Full admin card + audit **history** (`hist:` button, `/history` command,
  reads `Log`).
- ✅ **Reject with reason** (admin FSM → logged + delivered to applicant).
- ✅ **/stats** (status/category/experience counts + approval rate).
- ✅ **/export** CSV (Excel-friendly UTF-8 BOM).
- ✅ **/edit** - self-service nickname/email change (validated, unique-safe).
- ✅ Bug fix: admin card renders `experience_level` as a label, not the key.
- ✅ Bug fix: dead `qdel:` queue-delete button now handled.

### Phase 3 - platform
- ✅ Events & teams subsystem (models, service, admin commands, round-robin
  auto-balance) feeding the five scoring layers.
- ✅ **/leaderboard** ranks approved players by summed layer scores.
- ✅ **/broadcast** to approved players (compose → confirm → paced send).
- ✅ i18n (RU/EN) + **/language**, wired through `User.language`.

### Phase 4 - infra
- ✅ Dockerfile + docker-compose (bot + postgres + redis).
- ✅ GitHub Actions CI (ruff + pytest).
- ✅ README + architecture doc; DECISIONS.md; REVIEW.md.

## Status
- Tests: **78 passed**. Ruff: **clean**. Migrations: upgrade/downgrade + legacy
  adoption verified (now with an automated regression test).
- Audit round 1 caught: `/events` & `/teams` used the wrong repo path
  (`services.teams` → `services.events.teams`).
- Audit round 2 caught: FSM states captured slash-commands as free text
  (fixed with guards + `/cancel`); added wiring smoke test, legacy-adoption
  regression, and LanguageMiddleware resolution tests.

## Next / follow-ups (non-blocking)
- Localize the registration FSM step prompts (currently RU-only).
- Optional: batch `cmd_events` team lookups if event counts grow.
- Optional: handler tests for the FSM flows (reject-reason, broadcast, edit)
  driving full aiogram context.
