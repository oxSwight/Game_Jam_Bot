# Adversarial self-review

Read the diff as a hostile senior reviewer. Each defect is listed with its
resolution. The phase is done only when every item is closed or explicitly
accepted with a reason.

## Defects found & fixed

1. **Long-lived DB transaction during `/broadcast`.**
   `broadcast_send` held the per-request session/transaction open while
   paced-sending to every recipient (hundreds of `sleep`s). → Fixed: commit to
   release the transaction *before* the send loop
   (`handlers/admin_extra.py`).

2. **`LanguageMiddleware` over-fetched on every update.**
   It called `get_by_telegram_id`, which `selectinload`s all of a user's
   applications, only to read one column — an N+1-ish cost on every message.
   → Fixed: added `UserRepository.get_language` (single-column scalar select)
   and used it in the middleware.

3. **Dead `qdel:` button.** `queue_keyboard` emitted 🗑 buttons with no handler
   (pre-existing latent bug). → Fixed: added `cb_queue_delete`.

4. **Admin card rendered `experience_level` as the raw key** (`beginner`)
   instead of the label. → Fixed in `render_application_card`.

5. **No command-level tests.** Service logic was covered but the handler arg
   parsing / happy+error branches were not. → Fixed: `tests/test_handlers.py`
   drives commands via a fake Message (stats, export empty+CSV, leaderboard
   empty+ranked, event_new happy/missing-arg/duplicate, teams no-active-event).

6. **`/events` and `/teams` crashed on the happy path.** `cmd_events` /
   `cmd_teams` referenced `services.teams`, but the teams repo lives at
   `services.events.teams`; the container has no `teams` attribute. The earlier
   `/teams` test only exercised the no-active-event *early return*, masking it.
   → Fixed both call sites; added happy-path handler tests
   (`test_handlers_fsm.py`) that list events/teams and would have caught it.

## DoD closure — per-command happy + error tests

Added `tests/test_handlers_fsm.py`: `/history` (happy/missing-arg/not-found),
`/broadcast` (no-recipients / full compose→confirm→send), `/edit`
(no-application / nickname happy / invalid), `/language`, `/events`,
`/event_activate` + `/team_new` + `/teams`, `/team_new` missing-arg,
`/autoteams` without-teams. Every new command now has a happy and an error test.

## Round 2 — deeper audit

7. **FSM states captured slash-commands as free text.** In `reject_reason`,
   `broadcast_message` and the `edit` states, any in-state message was consumed
   — so typing `/queue` mid-reject silently became the rejection reason.
   → Fixed: leading-`/` guard in the free-text handlers + `/cancel` handlers for
   `reject_reason` and the edit states (previously only inline-button cancel).

8. **`event_from_user` ordering — investigated, no bug.** `LanguageMiddleware`
   relies on `data["event_from_user"]`. Confirmed aiogram registers its
   `UserContextMiddleware` as an *outer* update middleware
   (`dispatcher.py:84`), so it runs before our inner `dp.update.middleware`s and
   the key is populated. Added `test_language_middleware.py` to lock the
   resolution logic (saved lang > client lang > default).

9. **Untested critical paths hardened.** Added a dispatcher/middleware wiring
   smoke test and an automated regression for `_bootstrap_legacy_schema`
   (the data-loss-sensitive legacy-DB adoption), which was previously only
   verified by hand.

## Round 3 — found by actually running the bot

10. **Alembic silenced the bot's logging.** On startup `setup_logging()` runs,
    then `run_migrations()` invokes Alembic, whose `env.py` calls
    `fileConfig(alembic.ini)` with the default `disable_existing_loggers=True`.
    That disabled the app loggers and reset root to WARNING — so after startup
    the bot polled but logged **nothing** ("bot starting", "Start polling",
    errors all suppressed). → Fixed: `run_migrations` sets
    `ALEMBIC_SKIP_LOGGING_CONFIG` so `env.py` skips `fileConfig` when invoked
    in-process (CLI runs still honour alembic.ini). Verified by launching the
    bot: full log stream now continues through migration into "Run polling for
    bot @Game_Jem_bot".

## Accepted trade-offs (documented, not bugs)

- **Throttle also applies to registration multi-select taps** (0.5 s). A user
  toggling several role checkboxes very fast could occasionally see "Не так
  быстро". 0.5 s is a deliberate, gentle default; callback taps still get an
  `answer()` so nothing hangs. Acceptable for the expected tap cadence.
- **`cmd_events` issues one `list_for_event` per event** (N queries). Admin-only
  command over a handful of events — not worth batching.
- **Registration FSM step prompts remain Russian-only.** i18n covers entry
  commands, status, and all user notifications (the messages users receive
  outside the live flow). Full step-prompt localization is a documented
  follow-up, not a regression.
- **Legacy-DB adoption adds `team_id` as a bare column on Postgres** (no FK).
  Only relevant if a pre-Alembic deployment used Postgres (the old default was
  SQLite); the column is functional and the ORM-side relationship still works.

## Verification

- `pytest -q` → 51 passed.
- `ruff check .` → All checks passed.
- Migrations: `alembic upgrade head` + `downgrade base` on a clean SQLite DB
  (test_migrations), and legacy `players.db` adoption preserves existing rows
  (manually verified: 4 users retained, new tables + `team_id` added, stamped).
