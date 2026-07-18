"""Admin analytics, data export and broadcast.

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
from openpyxl import Workbook

from app.data.catalog import EXPERIENCE_LEVELS
from app.handlers.admin import IsAdminFilter
from app.keyboards.admin import broadcast_confirm_keyboard
from app.services import ServiceContainer
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
    approval_rate = f"{(approved / decided * 100):.0f}%" if decided else "-"

    lines = [
        "<b>Статистика заявок</b>\n",
        f"Всего: <b>{total}</b>",
        f"На проверке: <b>{pending}</b>",
        f"Одобрено: <b>{approved}</b>",
        f"Отклонено: <b>{rejected}</b>",
        f"Процент одобрения: <b>{approval_rate}</b>",
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
# /export - a spreadsheet of every application: .xlsx + .csv (delimiter ";")
# --------------------------------------------------------------------------- #
# Chars that make Excel/LibreOffice treat a cell as a formula. A crafted nickname
# like ``=HYPERLINK("http://evil","click")`` or ``@SUM(...)`` would otherwise run
# when an admin opens the export - classic CSV/formula injection. The same guard
# also covers the .xlsx path: openpyxl stores a string starting with "=" as a
# live formula, so every cell goes through _csv_cell before it reaches either file.
_CSV_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _csv_cell(value: object) -> str:
    """Render a value as a CSV-safe string, neutralising formula injection by
    prefixing a leading trigger char with a quote so it stays inert text."""
    text = "" if value is None else str(value)
    if text[:1] in _CSV_FORMULA_TRIGGERS:
        text = "'" + text
    return text


def _blank_empty_multiselect(value: str) -> str:
    """join_with_other renders an empty engine/tools list as the "-" placeholder;
    a CSV cell should be truly empty instead. Matched by equality (not a substring
    strip) so real hyphens inside names like "Construct-3" survive."""
    return "" if value == "-" else value


_EXPORT_HEADER = [
    "player_code", "id", "status", "is_active",
    "nickname", "email", "telegram_id", "telegram_username",
    "category", "roles", "experience", "engine", "tools",
    "strengths", "motivations",
    "created_at",
]


def _export_rows(applications) -> list[list[str]]:
    """Render every application as a list of already-sanitised cell strings -
    the single source both the .xlsx and the .csv are written from."""
    rows = []
    for app in applications:
        user = app.user
        row = [
            app.player_code or "",
            app.id,
            app.status.value,
            "yes" if (user and user.is_active) else "no",
            # Prefer the per-application snapshot (falls back to the user record).
            (app.nickname or (user.nickname if user else "")) or "",
            (app.email or (user.email if user else "")) or "",
            user.telegram_id if user else "",
            (user.telegram_username if user else "") or "",
            app.skill_category_title,
            "; ".join(app.subcategories),
            EXPERIENCE_LEVELS.get(app.experience_level, app.experience_level),
            _blank_empty_multiselect(join_with_other(app.engine, app.engine_other)),
            _blank_empty_multiselect(join_with_other(app.tools, app.tools_other)),
            "; ".join(app.strengths),
            "; ".join(app.motivations),
            app.created_at.isoformat() if app.created_at else "",
        ]
        rows.append([_csv_cell(cell) for cell in row])
    return rows


def _xlsx_bytes(rows: list[list[str]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "applications"
    ws.append(_EXPORT_HEADER)
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _csv_bytes(rows: list[list[str]]) -> bytes:
    # Delimiter ";" on purpose: multi-selects are joined with "; ", and with the
    # default "," delimiter csv.writer left those cells unquoted - a Russian-locale
    # Excel (list separator ";") then split them across neighbouring columns, a
    # per-row column drift. QUOTE_ALL so even an import wizard set to split on
    # both "," and ";" keeps every cell (incl. ", "-joined engine/tools) intact.
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_ALL)
    writer.writerow(_EXPORT_HEADER)
    writer.writerows(rows)
    # BOM so Excel opens the UTF-8 file with correct Cyrillic encoding.
    return ("﻿" + buffer.getvalue()).encode("utf-8")


@router.message(Command("export"))
async def cmd_export(message: Message, services: ServiceContainer) -> None:
    applications = await services.applications.list_all_with_users()
    if not applications:
        await message.answer("Заявок нет - экспортировать нечего.")
        return

    rows = _export_rows(applications)
    # .xlsx first: cells are typed in the file itself, so no importer has to
    # guess a delimiter and the columns can never drift.
    await message.answer_document(
        BufferedInputFile(_xlsx_bytes(rows), filename="applications.xlsx"),
        caption=f"Экспорт: {len(applications)} заявок",
    )
    await message.answer_document(
        BufferedInputFile(_csv_bytes(rows), filename="applications.csv"),
        caption='CSV для скриптов (разделитель ";")',
    )


# --------------------------------------------------------------------------- #
# /broadcast - message every approved player (FSM: compose → confirm → send)
# --------------------------------------------------------------------------- #
@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext, services: ServiceContainer) -> None:
    approved = await services.applications.list_approved()
    if not approved:
        await message.answer("Нет одобренных игроков для рассылки.")
        return
    await state.set_state(AdminStates.broadcast_message)
    await message.answer(
        f"Введите текст рассылки для <b>{len(approved)}</b> одобренных игроков.\n"
        "HTML-разметка поддерживается. /cancel - отмена."
    )


@router.message(Command("cancel"), AdminStates.broadcast_message)
@router.message(Command("cancel"), AdminStates.broadcast_confirm)
async def cancel_broadcast(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Рассылка отменена.")


@router.message(AdminStates.broadcast_message)
async def broadcast_compose(message: Message, state: FSMContext) -> None:
    text = message.html_text or (message.text or "")
    if (message.text or "").startswith("/"):
        await message.answer("Это команда. Введите текст рассылки или /cancel.")
        return
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
    await callback.message.edit_text(f"Отправляю {len(recipients)} игрокам…")
    await callback.answer()

    sent, failed = await services.notifications.broadcast(recipients, text)
    await callback.message.answer(
        f"Рассылка завершена.\nОтправлено: <b>{sent}</b>, ошибок: <b>{failed}</b>"
    )
