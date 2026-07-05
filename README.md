# GameJam Registration Bot

Telegram bot (aiogram 3) for registering players onto a GameJam platform, with an
admin review workflow, event/team management, and a five-layer scoring system.

## Features

**For players**
- Guided registration FSM: consent → nickname → email → category → role(s) →
  experience → engine → tools → motivation → confirm.
- `/status` — view your application, `/edit` — change nickname/email,
  `/withdraw` — delete and re-apply, `/language` — switch RU/EN UI.

**For admins**
- New-application notifications with inline **Approve / Reject / Reject+reason / History**.
- `/queue` — interactive paginated review queue (approve/reject/delete in place).
- `/pending`, `/approve`, `/reject`, `/history`, `/delete` — text commands.
- `/stats` — counts by status/category/experience + approval rate.
- `/export` — CSV of all applications (Excel-friendly UTF-8 BOM).
- `/leaderboard` — approved players ranked by summed layer scores.
- `/broadcast` — flood-safe message to all approved players (compose → confirm → send).
- **Events & teams**: `/event_new`, `/events`, `/event_activate`, `/team_new`,
  `/teams`, `/autoteams` (round-robin balance), `/setlayer` to score.

## Architecture

Layered, with dependency injection via middleware:

```
Telegram Update
  → ThrottlingMiddleware   (per-user anti-spam)
  → DbSessionMiddleware    (one AsyncSession per update, commit/rollback)
  → ServicesMiddleware     (builds ServiceContainer)
  → LanguageMiddleware     (resolves UI language → data["lang"])
  → AdminMiddleware        (stamps is_admin)
  → handlers → services → repositories → SQLAlchemy models
```

- **handlers/** — aiogram routers (thin; formatting + flow only).
- **services/** — business logic; own the unit of work, emit audit `Log`s.
- **repositories/** — query objects over the ORM models.
- **models/** — SQLAlchemy 2.0 mapped classes.
- **schemas/** — Pydantic validation for every registration step.
- **data/** — static catalog (roles, engines, tools) and scoring layers.
- **core/** — config, database, i18n, redis, logging, instance lock.

Key correctness guarantees:
- **One active application per user** is enforced by a partial unique index
  (`status != 'rejected'`), closing the check-then-insert race at the DB level.
- **Commit-before-notify**: applications are durably persisted before admins are
  pinged, so a send failure never leaves a phantom notification.

## Setup

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                # fill in BOT_TOKEN and ADMIN_IDS
python -m app.main
```

`FSM_STORAGE=memory` runs without Redis (state is lost on restart). For
production set `REDIS_URL` and leave `FSM_STORAGE=redis`.

### Docker

```bash
cp .env.example .env    # set BOT_TOKEN, ADMIN_IDS
docker compose up -d    # bot + postgres + redis
```

## Database migrations

Schema is managed by **Alembic**. Migrations run automatically on startup
(`run_migrations()` → `alembic upgrade head`). A pre-Alembic `players.db` created
by the old `create_all` path is detected and adopted (new tables/columns added,
then stamped) without data loss.

Create a new migration after changing models:

```bash
alembic revision --autogenerate -m "describe change"
```

## Tests

```bash
pytest -q          # full suite
ruff check .       # lint
```

Tests run against an in-memory SQLite database and cover schemas, repositories,
services, the one-active-application constraint, i18n, and the throttle.

## Configuration

| Variable       | Default                              | Purpose                          |
|----------------|--------------------------------------|----------------------------------|
| `BOT_TOKEN`    | —                                    | Telegram bot token (required)    |
| `ADMIN_IDS`    | —                                    | Comma-separated admin Telegram IDs |
| `DATABASE_URL` | `sqlite+aiosqlite:///./players.db`   | SQLAlchemy async URL             |
| `REDIS_URL`    | —                                    | Redis for FSM storage            |
| `FSM_STORAGE`  | `redis`                              | `redis` or `memory`              |
| `LOG_LEVEL`    | `INFO`                               | Logging level                    |
| `LOG_JSON`     | `false`                              | JSON structured logs             |
