"""Admin analytics, data export, broadcast, events/teams and leaderboard.

Split out from admin.py to keep each file focused; shares the same IsAdminFilter
so every route here is admin-only.
"""

import csv
import io
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.data.catalog import EXPERIENCE_LEVELS
from app.handlers.admin import IsAdminFilter
from app.keyboards.admin import broadcast_confirm_keyboard
from app.models.event import EventStatus
from app.services import ServiceContainer
from app.services.event import EventError
from app.states.admin import AdminStates
from app.utils.html import join_with_other, safe

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())


# --------------------------------------------------------------------------- #
# /stats
# --------------------------------------------------------------------------- #
@router.message(Command("stats"))
async def cmd_stats(message: Message, services: ServiceContainer) -> None:
    by_status = await services.applications.count_by_status()
    by_category = await services.applications.count_by_category()
    by_experience = await services.applications.count_by_experience()

    total = sum(by_status.values())
    approved = by_status.get("approved", 0)
    rejected = by_status.get("rejected", 0)
    pending = by_status.get("pending_review", 0)
    decided = approved + rejected
    approval_rate = f"{(approved / decided * 100):.0f}%" if decided else "—"

    lines = [
        "📊 <b>Статистика заявок</b>\n",
        f"Всего: <b>{total}</b>",
        f"⏳ На проверке: <b>{pending}</b>",
        f"✅ Одобрено: <b>{approved}</b>",
        f"❌ Отклонено: <b>{rejected}</b>",
        f"📈 Процент одобрения: <b>{approval_rate}</b>",
    ]

    if by_category:
        lines.append("\n<b>По категориям:</b>")
        for title, count in by_category:
            lines.append(f"• {safe(title)}: {count}")

    if by_experience:
        lines.append("\n<b>По опыту:</b>")
        for level, count in by_experience:
            label = EXPERIENCE_LEVELS.get(level, level)
            lines.append(f"• {safe(label)}: {count}")

    await message.answer("\n".join(lines))


# --------------------------------------------------------------------------- #
# /export — CSV of every application
# --------------------------------------------------------------------------- #
@router.message(Command("export"))
async def cmd_export(message: Message, services: ServiceContainer) -> None:
    applications = await services.applications.list_all_with_users()
    if not applications:
        await message.answer("Заявок нет — экспортировать нечего.")
        return

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id", "status", "nickname", "email", "telegram_id", "telegram_username",
            "category", "roles", "experience", "engine", "tools", "motivations",
            "team_id", "total_score", "created_at",
        ]
    )
    for app in applications:
        user = app.user
        writer.writerow(
            [
                app.id,
                app.status.value,
                (user.nickname if user else "") or "",
                (user.email if user else "") or "",
                user.telegram_id if user else "",
                (user.telegram_username if user else "") or "",
                app.skill_category_title,
                "; ".join(app.subcategories),
                EXPERIENCE_LEVELS.get(app.experience_level, app.experience_level),
                join_with_other(app.engine, app.engine_other).replace("—", ""),
                join_with_other(app.tools, app.tools_other).replace("—", ""),
                "; ".join(app.motivations),
                app.team_id or "",
                app.total_score,
                app.created_at.isoformat() if app.created_at else "",
            ]
        )

    # BOM so Excel opens the UTF-8 file with correct Cyrillic encoding.
    data = ("﻿" + buffer.getvalue()).encode("utf-8")
    document = BufferedInputFile(data, filename="applications.csv")
    await message.answer_document(
        document, caption=f"📄 Экспорт: {len(applications)} заявок"
    )


# --------------------------------------------------------------------------- #
# /leaderboard — approved players ranked by summed layer scores
# --------------------------------------------------------------------------- #
@router.message(Command("leaderboard"))
@router.message(Command("top"))
async def cmd_leaderboard(message: Message, services: ServiceContainer) -> None:
    apps = await services.applications.leaderboard(limit=10)
    if not apps:
        await message.answer(
            "🏆 Лидерборд пуст. Выставьте баллы через /setlayer, чтобы игроки появились."
        )
        return

    medals = {0: "🥇", 1: "🥈", 2: "🥉"}
    lines = ["🏆 <b>Лидерборд</b>\n"]
    for idx, app in enumerate(apps):
        marker = medals.get(idx, f"{idx + 1}.")
        nickname = (app.user.nickname if app.user else None) or "—"
        team = f" · {safe(app.team.name)}" if app.team else ""
        lines.append(f"{marker} <b>{safe(nickname)}</b> — {app.total_score:g}{team}")
    await message.answer("\n".join(lines))


# --------------------------------------------------------------------------- #
# /broadcast — message every approved player (FSM: compose → confirm → send)
# --------------------------------------------------------------------------- #
@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext, services: ServiceContainer) -> None:
    approved = await services.applications.list_approved()
    if not approved:
        await message.answer("Нет одобренных игроков для рассылки.")
        return
    await state.set_state(AdminStates.broadcast_message)
    await message.answer(
        f"📣 Введите текст рассылки для <b>{len(approved)}</b> одобренных игроков.\n"
        "HTML-разметка поддерживается. /cancel — отмена."
    )


@router.message(Command("cancel"), AdminStates.broadcast_message)
@router.message(Command("cancel"), AdminStates.broadcast_confirm)
async def cancel_broadcast(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Рассылка отменена.")


@router.message(AdminStates.broadcast_message)
async def broadcast_compose(message: Message, state: FSMContext) -> None:
    text = message.html_text or (message.text or "")
    if len(text.strip()) < 2:
        await message.answer("Текст слишком короткий. Введите сообщение для рассылки.")
        return
    await state.update_data(broadcast_text=text)
    await state.set_state(AdminStates.broadcast_confirm)
    await message.answer(
        "Предпросмотр:\n\n" + text + "\n\nОтправить всем одобренным игрокам?",
        reply_markup=broadcast_confirm_keyboard(),
    )


@router.callback_query(AdminStates.broadcast_confirm, F.data == "bcast:cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Рассылка отменена.")
    await callback.answer()


@router.callback_query(AdminStates.broadcast_confirm, F.data == "bcast:send")
async def broadcast_send(
    callback: CallbackQuery, state: FSMContext, services: ServiceContainer
) -> None:
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    await state.clear()
    if not text or not services.notifications:
        await callback.answer("Нечего отправлять.", show_alert=True)
        return

    approved = await services.applications.list_approved()
    recipients = [a.user.telegram_id for a in approved if a.user]
    # Release the request transaction before the (potentially long) send loop so
    # we don't hold an idle DB transaction open while paced-sending to everyone.
    await services.session.commit()
    await callback.message.edit_text(f"📣 Отправляю {len(recipients)} игрокам…")
    await callback.answer()

    sent, failed = await services.notifications.broadcast(recipients, text)
    await callback.message.answer(
        f"✅ Рассылка завершена.\nОтправлено: <b>{sent}</b>, ошибок: <b>{failed}</b>"
    )


# --------------------------------------------------------------------------- #
# Events & teams
# --------------------------------------------------------------------------- #
@router.message(Command("event_new"))
async def cmd_event_new(message: Message, services: ServiceContainer) -> None:
    name = (message.text or "").split(maxsplit=1)
    if len(name) < 2:
        await message.answer("Использование: /event_new &lt;название&gt;")
        return
    try:
        event = await services.events.create_event(name[1])
    except EventError as exc:
        await message.answer(str(exc))
        return
    await services.session.commit()
    await message.answer(
        f"🎪 Событие создано: <b>{safe(event.name)}</b> (id={event.id}, статус: {event.status.value}).\n"
        f"Активируйте: /event_activate {event.id}"
    )


@router.message(Command("events"))
async def cmd_events(message: Message, services: ServiceContainer) -> None:
    events = await services.events.list_events()
    if not events:
        await message.answer("Событий пока нет. Создайте: /event_new &lt;название&gt;")
        return
    lines = ["🎪 <b>События</b>\n"]
    for event in events:
        teams = await services.events.teams.list_for_event(event.id)
        members = sum(len(t.members) for t in teams)
        active = " ⭐" if event.status == EventStatus.ACTIVE else ""
        lines.append(
            f"• <b>{safe(event.name)}</b> (id={event.id}, {event.status.value}){active}"
            f"\n   команд: {len(teams)}, участников: {members}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("event_activate"))
async def cmd_event_activate(message: Message, services: ServiceContainer) -> None:
    event = await _resolve_event(message, services)
    if event is None:
        return
    await services.events.set_status(event, EventStatus.ACTIVE)
    await services.session.commit()
    await message.answer(f"⭐ Событие <b>{safe(event.name)}</b> активно.")


@router.message(Command("team_new"))
async def cmd_team_new(message: Message, services: ServiceContainer) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Использование: /team_new &lt;event_id&gt; &lt;название команды&gt;")
        return
    event = await _lookup_event(parts[1], services)
    if event is None:
        await message.answer("Событие не найдено.")
        return
    try:
        team = await services.events.create_team(event, parts[2])
    except EventError as exc:
        await message.answer(str(exc))
        return
    await services.session.commit()
    await message.answer(
        f"👥 Команда <b>{safe(team.name)}</b> создана в «{safe(event.name)}» (id={team.id})."
    )


@router.message(Command("autoteams"))
async def cmd_autoteams(message: Message, services: ServiceContainer) -> None:
    event = await _resolve_event(message, services)
    if event is None:
        return
    try:
        assigned, team_count = await services.events.auto_balance(event)
    except EventError as exc:
        await message.answer(str(exc))
        return
    await services.session.commit()
    await message.answer(
        f"🤝 Распределено <b>{assigned}</b> игроков по <b>{team_count}</b> командам "
        f"события «{safe(event.name)}»."
    )


@router.message(Command("teams"))
async def cmd_teams(message: Message, services: ServiceContainer) -> None:
    event = await _resolve_event(message, services)
    if event is None:
        return
    teams = await services.events.teams.list_for_event(event.id)
    if not teams:
        await message.answer("В событии пока нет команд. Создайте: /team_new")
        return
    lines = [f"👥 <b>Команды события «{safe(event.name)}»</b>\n"]
    for team in teams:
        members = ", ".join(
            safe((m.user.nickname if m.user else None) or "—") for m in team.members
        ) or "—"
        lines.append(f"<b>{safe(team.name)}</b> ({len(team.members)}): {members}")
    await message.answer("\n".join(lines))


async def _resolve_event(message: Message, services: ServiceContainer):
    """Resolve the event from the command's first arg, or fall back to the
    single active event when no id is given."""
    parts = (message.text or "").split()
    if len(parts) >= 2:
        event = await _lookup_event(parts[1], services)
        if event is None:
            await message.answer("Событие не найдено.")
        return event
    event = await services.events.events.get_active()
    if event is None:
        await message.answer("Нет активного события. Укажите id или активируйте событие.")
    return event


async def _lookup_event(token: str, services: ServiceContainer):
    if token.isdigit():
        return await services.events.events.get_by_id(int(token))
    return await services.events.events.find_by_name_prefix(token)
