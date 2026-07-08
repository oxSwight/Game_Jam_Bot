# GameJam Gateway Bot

Telegram bot (aiogram 3) that acts as a hardened **gateway** into a closed game
group. It vets applicants through a structured skills questionnaire and, on
approval, mints a **personal join-request invite link** into the private group -
the join is auto-approved only for the vetted applicant, so a leaked link admits
nobody else. All the actual gameplay and team-forming happen inside the group -
this bot is only the door and its lock.

## Features

**For players**
- Anti-bot **emoji CAPTCHA** before the form opens.
- Explicit **rules & privacy consent** (docs/PRIVACY.md, versioned; the accepted
  version is recorded in the audit log).
- Guided registration FSM: consent → nickname → email → category → role(s) →
  experience → engine → tools → motivation → confirm.
- On approval: a personal join-request invite link is delivered by DM; the bot
  confirms the join automatically. `/invite` re-issues a lost link.
- `/status` - view your application, `/edit` - change nickname/email/skills,
  `/withdraw` - **irreversibly erase all your data** (right to erasure),
  `/language` - switch RU/EN UI.

**For admins**
- `/review` - one card at a time, swipe-through queue. **Approve** / **Reject**
  inline; acting on a card edits it in place to the next pending application. No
  per-application push notifications (that would blow Telegram's rate limits).
- `/stats` - counts by status/category/experience + approval rate.
- `/export` - CSV of all applications (Excel-friendly UTF-8 BOM, formula-injection safe).
- `/broadcast` - flood-safe message to all approved players (compose → confirm → send).

## Defense echelons (anti-bot / anti-spam)

1. **Throttling** - one action per second per user; sustained flooding earns a
   silent 5-minute **shadowban** (every update dropped, no feedback at all).
2. **CAPTCHA** - a scripted client can't know which named emoji to tap; a wrong
   tap cancels registration.
3. **Queue cap** - `/register` is refused once `PENDING_CAP` (default 300)
   applications are awaiting review.
4. **Link ban** - any http/https/`t.me` link in a free-text answer instantly
   resets the whole registration flow.

## Architecture

Layered, with dependency injection via middleware:

```
Telegram Update
  → ThrottlingMiddleware   (per-user rate limit + shadowban)
  → DbSessionMiddleware    (one AsyncSession per update, commit/rollback)
  → ServicesMiddleware     (builds ServiceContainer)
  → LanguageMiddleware     (resolves UI language → data["lang"])
  → AdminMiddleware        (stamps is_admin)
  → handlers → services → repositories → SQLAlchemy models
```

- **handlers/** - aiogram routers (thin; formatting + flow only).
- **services/** - business logic; own the unit of work, emit audit `Log`s, and
  mint invite links via the Bot API.
- **repositories/** - query objects over the ORM models.
- **models/** - SQLAlchemy 2.0 mapped classes (`User`, `Application`, `Log`).
- **schemas/** - Pydantic validation for every registration step.
- **data/** - static catalog (roles, engines, tools) and the CAPTCHA pool.
- **core/** - config, database, i18n, redis, logging, instance lock.

Key correctness guarantees:
- **One active application per user** is enforced by a partial unique index
  (`status != 'rejected'`), closing the check-then-insert race at the DB level.
- **Commit-before-invite**: an approval is durably persisted before the invite
  link is minted and DMed.
- **Atomic decisions**: approve/reject is a conditional
  `UPDATE … WHERE status='pending_review'`, so two admins racing on the same
  card produce exactly one decision and one invite.
- **Race-free player codes**: public ids come from per-category counter rows
  (`UPDATE … RETURNING`), not a `max()+1` scan.
- **Identity-checked joins**: invite links only file a join *request*; the bot
  approves it iff that user's application is APPROVED.
- **Single instance**: a local file lock plus a PostgreSQL advisory lock (two
  containers on different hosts can't double-poll the same bot).

## Setup

Database is **PostgreSQL** (production). The bot must be an **admin of the target
group** with permission to invite/add members, and `GROUP_CHAT_ID` must point at
that group.

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                # BOT_TOKEN, ADMIN_IDS, GROUP_CHAT_ID, DATABASE_URL
python -m app.main
```

### Docker

```bash
cp .env.example .env    # set BOT_TOKEN, ADMIN_IDS, GROUP_CHAT_ID, POSTGRES_PASSWORD
docker compose up -d    # bot + postgres + redis
```

`POSTGRES_PASSWORD` has **no default** - compose refuses to start without it.
The bot container has a heartbeat-file healthcheck (stale > 90 s → unhealthy).

## Privacy

The consent step shows a versioned rules & privacy document
([docs/PRIVACY.md](docs/PRIVACY.md)); the accepted version is recorded in the
application's audit log. `/withdraw` implements the right to erasure: it hard-
deletes the user row (nickname, email, username, language) and every
application - including rejected ones - with their audit logs. Audit log
entries never store contact values, and Telegram ids are kept out of INFO-level
logs.

## Database migrations

Schema is managed by **Alembic**; migrations run automatically on startup
(`run_migrations()` → `alembic upgrade head`).

Create a new migration after changing models:

```bash
alembic revision --autogenerate -m "describe change"
```

## Tests

```bash
pytest -q          # full suite
ruff check .       # lint
```

Tests run against an in-memory SQLite database (a dev-only convenience) and cover
schemas, repositories, services, the one-active-application constraint, the
CAPTCHA/queue-cap/link-ban gates, the /review flow, i18n, and the throttle.

## Configuration

| Variable       | Default                                              | Purpose                              |
|----------------|------------------------------------------------------|--------------------------------------|
| `BOT_TOKEN`    | -                                                    | Telegram bot token (required)        |
| `ADMIN_IDS`    | -                                                    | Comma-separated admin Telegram IDs   |
| `GROUP_CHAT_ID`| -                                                    | Gated group id (for invite links)    |
| `PENDING_CAP`  | `300`                                                | Max applications in the review queue |
| `DATABASE_URL` | `postgresql+asyncpg://gamejam:gamejam@localhost/...` | SQLAlchemy async URL (PostgreSQL)    |
| `POSTGRES_PASSWORD` | - (required for compose)                        | DB password, interpolated by compose |
| `REDIS_URL`    | -                                                    | Redis for FSM storage                |
| `FSM_STORAGE`  | `redis`                                              | `redis` or `memory`                  |
| `LOG_LEVEL`    | `INFO`                                               | Logging level                        |
| `LOG_JSON`     | `false`                                              | JSON structured logs                 |
