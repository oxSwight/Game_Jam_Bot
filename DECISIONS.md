# Decisions & assumptions

Reasonable defaults chosen while working autonomously, recorded here so they can
be revisited.

- **Alembic on startup.** `run_migrations()` runs `alembic upgrade head` in a
  worker thread (env.py drives the async engine via `asyncio.run`, which can't
  nest in the bot's loop). A pre-Alembic `players.db` (created by the old
  `create_all`) is detected and *adopted* — missing tables created, `team_id`
  added, then `alembic stamp head` — instead of failing on "table exists".
  `init_db()` (create_all) is kept for the test fixtures only.

- **Enums stay `(str, Enum)` with `values_callable`.** Ruff's UP042 suggests
  `StrEnum`; declined and ignored the rule. The existing value-serialization
  (lowercase values matching the partial unique index + server_default) is
  delicate and already correct — not worth disturbing.

- **Scoring model.** `total_score` = sum of the five layer columns, treating
  unset layers as 0; `/leaderboard` excludes applications with no score at all
  (`has_any_score`). Sorting is done in Python because the "unset = 0" rule is
  awkward in portable SQL across SQLite/Postgres.

- **Teams belong to events; `Application.team_id` is a nullable FK.** One active
  event at a time (`set_status(ACTIVE)` finishes the previous active event) so
  the leaderboard context is unambiguous. `auto_balance` is round-robin seeded
  by current team sizes, so re-runs stay balanced.

- **i18n scope.** A flat Python catalog (`app/core/i18n.py`), not gettext. RU/EN
  cover entry commands, status labels and user notifications; `User.language`
  (previously unused) now drives them, resolved per-update by `LanguageMiddleware`
  with fallback to the Telegram client language then `DEFAULT_LANG` (ru).

- **Throttling is in-memory, per-process.** InstanceLock guarantees a single
  polling process, so a distributed limiter is unnecessary. Default rate 0.5 s.

- **`/broadcast` pacing.** ~20 msg/s with `TelegramRetryAfter` back-off, sent
  after committing the request transaction.

- **Reject-reason actor id** is taken from the admin's private chat id
  (`message.chat.id`), which equals their Telegram user id for a DM with the bot.
