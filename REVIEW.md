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
