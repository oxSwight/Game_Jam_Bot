import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from pydantic import ValidationError

from app.core.i18n import t
from app.data.catalog import (
    CATEGORY_BY_ID,
    CONSENT_ITEMS,
    EXPERIENCE_LEVELS,
    MAIN_CATEGORIES,
    role_titles,
)
from app.keyboards.registration import (
    cancel_keyboard,
    categories_keyboard,
    confirm_keyboard,
    consent_keyboard,
    edit_field_keyboard,
    engine_keyboard,
    experience_keyboard,
    language_keyboard,
    motivation_keyboard,
    roles_keyboard,
    tools_keyboard,
)
from app.schemas.registration import EmailStep, NicknameStep, RegistrationCreate
from app.services import ServiceContainer
from app.services.application import ActiveApplicationExistsError
from app.states.admin import EditStates
from app.states.registration import RegistrationStates
from app.utils.html import join_with_other, safe

router = Router()
logger = logging.getLogger(__name__)


def _status_label(status: str, lang: str) -> str:
    return t(f"status_{status}", lang) if status in {
        "pending_review", "approved", "rejected"
    } else status


def _consent_text() -> str:
    items = "\n".join(f"• {item}" for item in CONSENT_ITEMS)
    return (
        "🎮 <b>Регистрация на платформу GameJam</b>\n\n"
        "Перед началом подтвердите, что вы:\n"
        f"{items}\n\n"
        "Нажмите кнопку ниже, чтобы продолжить."
    )


def _build_summary(data: dict) -> str:
    roles = ", ".join(safe(t) for t in role_titles(data.get("roles", []))) or "—"
    engine = join_with_other(data.get("engine", []), data.get("engine_other"))
    tools = join_with_other(data.get("tools", []), data.get("tools_other"))
    motivations = ", ".join(safe(m) for m in data.get("motivations", []))

    lines = [
        f"<b>Ник:</b> {safe(data.get('nickname'))}",
        f"<b>Email:</b> {safe(data.get('email'))}",
        f"<b>Категория:</b> {safe(data.get('category_title', '—'))}",
        f"<b>Роли:</b> {roles}",
        f"<b>Опыт:</b> {safe(EXPERIENCE_LEVELS.get(data.get('experience_level', ''), '—'))}",
        f"<b>Движок:</b> {engine}",
        f"<b>Инструменты:</b> {tools}",
        f"<b>Мотивация:</b> {motivations}",
    ]
    return "\n".join(lines)


async def _go_to_motivation(message: Message, state: FSMContext) -> None:
    await state.update_data(motivations=[])
    await state.set_state(RegistrationStates.motivation)
    await message.answer(
        "<b>Шаг G — Мотивация</b>\n\n"
        "Что вас привлекает? (можно несколько):",
        reply_markup=motivation_keyboard(set()),
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    services: ServiceContainer,
    lang: str = "ru",
) -> None:
    await state.clear()
    profile = await services.users.get_profile(message.from_user.id)
    if profile:
        status = _status_label(profile.status, lang)
        await message.answer(
            t(
                "already_registered",
                lang,
                nickname=safe(profile.nickname),
                status=safe(status),
                id=profile.id,
            )
        )
        return

    await message.answer(t("welcome", lang))


@router.message(Command("register"))
@router.message(Command("reg"))
async def cmd_register(
    message: Message,
    state: FSMContext,
    services: ServiceContainer,
    lang: str = "ru",
) -> None:
    await state.clear()
    if await services.applications.has_active_application(message.from_user.id):
        await message.answer(t("active_application_exists", lang))
        return

    await state.set_state(RegistrationStates.consent)
    await message.answer(_consent_text(), reply_markup=consent_keyboard())


@router.message(Command("status"))
async def cmd_status(message: Message, services: ServiceContainer, lang: str = "ru") -> None:
    profile = await services.users.get_profile(message.from_user.id)
    if not profile:
        await message.answer(t("status_not_found", lang))
        return

    await message.answer(
        f"<b>Ваш профиль</b>\n\n"
        f"ID: <code>{profile.id}</code>\n"
        f"Ник: {safe(profile.nickname)}\n"
        f"Email: {safe(profile.email)}\n"
        f"Категория: {safe(MAIN_CATEGORIES.get(profile.main_category, profile.skill_category_title))}\n"
        f"Роли: {', '.join(safe(s) for s in profile.subcategories) or '—'}\n"
        f"Опыт: {safe(EXPERIENCE_LEVELS.get(profile.experience_level, profile.experience_level))}\n"
        f"Движок: {join_with_other(profile.engine, profile.engine_other)}\n"
        f"Инструменты: {join_with_other(profile.tools, profile.tools_other)}\n"
        f"Мотивация: {', '.join(safe(m) for m in profile.motivations)}\n"
        f"Статус: {safe(_status_label(profile.status, lang))}",
    )


@router.message(Command("cancel"), RegistrationStates())
@router.message(F.text == "❌ Отменить регистрацию", RegistrationStates())
async def cancel_registration(message: Message, state: FSMContext, lang: str = "ru") -> None:
    await state.clear()
    await message.answer(
        t("registration_cancelled", lang),
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(Command("withdraw"))
@router.message(Command("reset"))
async def cmd_withdraw(
    message: Message,
    state: FSMContext,
    services: ServiceContainer,
    lang: str = "ru",
) -> None:
    """Self-service: delete your own active application so you can register anew."""
    await state.clear()
    removed = await services.applications.withdraw_active(message.from_user.id)
    if removed:
        await message.answer(t("withdraw_done", lang), reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer(t("withdraw_none", lang))


# --------------------------------------------------------------------------- #
# Language selection
# --------------------------------------------------------------------------- #
@router.message(Command("language"))
@router.message(Command("lang"))
async def cmd_language(message: Message, lang: str = "ru") -> None:
    await message.answer(t("language_prompt", lang), reply_markup=language_keyboard())


@router.callback_query(F.data.startswith("lang:"))
async def set_language(callback: CallbackQuery, services: ServiceContainer) -> None:
    code = callback.data.split(":", 1)[1]
    await services.users.set_language(callback.from_user.id, code)
    await callback.message.edit_text(t("language_set", code))
    await callback.answer()


# --------------------------------------------------------------------------- #
# Self-service edit of nickname / email
# --------------------------------------------------------------------------- #
@router.message(Command("edit"))
async def cmd_edit(message: Message, state: FSMContext, services: ServiceContainer) -> None:
    profile = await services.users.get_profile(message.from_user.id)
    if not profile:
        await message.answer("У вас нет активной заявки. /register")
        return
    await state.set_state(EditStates.field)
    await message.answer(
        "Что изменить?\n"
        f"Текущий ник: <b>{safe(profile.nickname)}</b>\n"
        f"Текущий email: <b>{safe(profile.email)}</b>",
        reply_markup=edit_field_keyboard(),
    )


@router.callback_query(EditStates.field, F.data == "edit:cancel")
async def edit_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Изменение отменено.")
    await callback.answer()


@router.callback_query(EditStates.field, F.data == "edit:nickname")
async def edit_pick_nickname(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditStates.nickname)
    await callback.message.edit_text("Введите новый <b>никнейм</b>:")
    await callback.answer()


@router.callback_query(EditStates.field, F.data == "edit:email")
async def edit_pick_email(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditStates.email)
    await callback.message.edit_text("Введите новый <b>email</b>:")
    await callback.answer()


@router.message(EditStates.nickname)
async def edit_apply_nickname(
    message: Message, state: FSMContext, services: ServiceContainer
) -> None:
    try:
        step = NicknameStep(nickname=message.text or "")
    except ValidationError as exc:
        await message.answer(services.users.format_validation_error(exc))
        return
    await _apply_edit(message, state, services, nickname=step.nickname)


@router.message(EditStates.email)
async def edit_apply_email(
    message: Message, state: FSMContext, services: ServiceContainer
) -> None:
    try:
        step = EmailStep(email=message.text or "")
    except ValidationError as exc:
        await message.answer(services.users.format_validation_error(exc))
        return
    await _apply_edit(message, state, services, email=str(step.email))


async def _apply_edit(
    message: Message,
    state: FSMContext,
    services: ServiceContainer,
    *,
    nickname: str | None = None,
    email: str | None = None,
) -> None:
    from sqlalchemy.exc import IntegrityError

    try:
        ok = await services.applications.update_contact(
            message.from_user.id, nickname=nickname, email=email
        )
        await services.session.commit()
    except IntegrityError:
        await services.session.rollback()
        await message.answer("Такой ник или email уже заняты. Попробуйте другой.")
        return
    await state.clear()
    if ok:
        await message.answer("✅ Данные обновлены. /status — посмотреть профиль.")
    else:
        await message.answer("Активная заявка не найдена.")


@router.message(Command("whoami"))
@router.message(Command("id"))
async def cmd_whoami(message: Message, is_admin: bool = False) -> None:
    lines = [
        "🪪 <b>Кто вы</b>\n",
        f"Telegram ID: <code>{message.from_user.id}</code>",
        f"Username: @{safe(message.from_user.username) or '—'}",
    ]
    # Admin status is internal — only surface it (and admin tools) to admins.
    if is_admin:
        lines.append("Роль: 👑 администратор")
        lines.append("\nАдмин-команды: /queue, /pending, /approve, /reject, /delete")
    await message.answer("\n".join(lines))


@router.message(Command("help"))
async def cmd_help(message: Message, is_admin: bool = False) -> None:
    lines = [
        "🤖 <b>Команды</b>\n",
        "/register — подать заявку",
        "/status — статус вашей заявки",
        "/edit — изменить ник или email",
        "/withdraw — удалить свою заявку и подать заново",
        "/language — сменить язык",
        "/whoami — ваш ID и роль",
    ]
    if is_admin:
        lines += [
            "\n<b>👑 Админ:</b>",
            "/queue — интерактивная очередь заявок",
            "/pending — счётчик заявок на проверке",
            "/approve &lt;id&gt; — одобрить",
            "/reject &lt;id&gt; — отклонить",
            "/history &lt;id&gt; — история заявки",
            "/delete &lt;id&gt; — удалить заявку (тестовые данные)",
            "/setlayer &lt;id&gt; &lt;1-5&gt; &lt;score&gt; — выставить score",
            "/stats — статистика · /export — CSV",
            "/leaderboard — топ игроков",
            "/broadcast — рассылка одобренным",
            "/events, /event_new, /event_activate — события",
            "/team_new, /teams, /autoteams — команды",
        ]
    await message.answer("\n".join(lines))


@router.callback_query(F.data == "consent:decline")
async def consent_decline(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Регистрация отменена.")
    await callback.answer()


@router.callback_query(F.data == "consent:accept")
async def consent_accept(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(consent=True)
    await state.set_state(RegistrationStates.nickname)
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        # Message may be too old to delete; fall back to removing the keyboard
        logger.debug("could not delete consent message, removing keyboard instead")
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "✅ Отлично!\n\n"
        "<b>Шаг A — Базовая информация</b>\n\n"
        "Введите ваш <b>никнейм</b> (отображаемое имя на платформе):\n\n"
        "<i>Можно отменить в любой момент — кнопка ниже.</i>",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(RegistrationStates.nickname)
async def process_nickname(
    message: Message,
    state: FSMContext,
    services: ServiceContainer,
) -> None:
    try:
        step = NicknameStep(nickname=message.text or "")
    except ValidationError as exc:
        await message.answer(services.users.format_validation_error(exc))
        return

    await state.update_data(nickname=step.nickname)
    await state.set_state(RegistrationStates.email)
    await message.answer("Введите ваш <b>email</b> для связи:")


@router.message(RegistrationStates.email)
async def process_email(
    message: Message,
    state: FSMContext,
    services: ServiceContainer,
) -> None:
    try:
        step = EmailStep(email=message.text or "")
    except ValidationError as exc:
        await message.answer(services.users.format_validation_error(exc))
        return

    await state.update_data(email=str(step.email))
    await state.set_state(RegistrationStates.category)
    await message.answer(
        "<b>Шаг B — Категория</b>\n\n"
        "Выберите основное направление:",
        reply_markup=categories_keyboard(),
    )


def _roles_prompt(category) -> str:
    return (
        f"<b>{safe(category.title)}</b>\n<i>{safe(category.description)}</i>\n\n"
        "Выберите роль(и) (можно несколько), затем нажмите «Готово»:"
    )


@router.callback_query(RegistrationStates.category, F.data.startswith("cat:"))
async def process_category(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("email") or not data.get("nickname"):
        await callback.answer("Сессия устарела. Начните заново: /register", show_alert=True)
        return

    category_id = callback.data.split(":", 1)[1]
    category = CATEGORY_BY_ID.get(category_id)
    if category is None:
        await callback.answer("Неизвестная категория.", show_alert=True)
        return

    await state.update_data(
        category_id=category.id,
        category_title=category.title,
        roles=[],
        role_page=0,
    )
    await state.set_state(RegistrationStates.roles)
    await callback.message.edit_text(
        _roles_prompt(category),
        reply_markup=roles_keyboard(category.id, set()),
    )
    await callback.answer()


@router.callback_query(RegistrationStates.roles, F.data.startswith("role_page:"))
async def role_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    category_id = data["category_id"]
    selected = set(data.get("roles", []))
    await state.update_data(role_page=page)
    await callback.message.edit_reply_markup(
        reply_markup=roles_keyboard(category_id, selected, page=page),
    )
    await callback.answer()


@router.callback_query(RegistrationStates.roles, F.data.startswith("role:"))
async def toggle_role(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":", 1)[1]
    if action == "noop":
        await callback.answer()
        return

    data = await state.get_data()
    category_id = data["category_id"]
    selected: list[str] = list(data.get("roles", []))

    if action == "done":
        if not selected:
            await callback.answer("Выберите хотя бы одну роль", show_alert=True)
            return
        await state.set_state(RegistrationStates.experience)
        await callback.message.edit_text(
            "<b>Шаг C — Уровень опыта</b>\n\n"
            "Выберите ваш уровень:",
            reply_markup=experience_keyboard(),
        )
        await callback.answer()
        return

    if action in selected:
        selected.remove(action)
    else:
        selected.append(action)
    await state.update_data(roles=selected)
    page = data.get("role_page", 0)
    await callback.message.edit_reply_markup(
        reply_markup=roles_keyboard(category_id, set(selected), page=page),
    )
    await callback.answer()


@router.callback_query(RegistrationStates.experience, F.data.startswith("exp:"))
async def process_experience(callback: CallbackQuery, state: FSMContext) -> None:
    level = callback.data.split(":", 1)[1]
    await state.update_data(experience_level=level, engine=[], engine_other=None)
    await state.set_state(RegistrationStates.engine)
    await callback.message.edit_text(
        "<b>Шаг D — Движок</b>\n\n"
        "Выберите движок, в котором работаете (можно несколько):",
        reply_markup=engine_keyboard(set(), has_other=False),
    )
    await callback.answer()


async def _go_to_tools(message: Message, state: FSMContext) -> None:
    await state.update_data(tools=[], tools_other=None)
    await state.set_state(RegistrationStates.tools)
    await message.answer(
        "<b>Шаг E — Инструменты</b>\n\n"
        "Выберите инструменты, с которыми работаете (можно несколько):",
        reply_markup=tools_keyboard(set(), has_other=False),
    )


@router.callback_query(RegistrationStates.engine, F.data.startswith("engine:"))
async def toggle_engine(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected: list[str] = list(data.get("engine", []))

    if action == "done":
        if not selected:
            await callback.answer("Выберите хотя бы один движок", show_alert=True)
            return
        if "Other" in selected and not data.get("engine_other"):
            await state.set_state(RegistrationStates.engine_other)
            await callback.message.edit_text("Укажите другой движок (текстом):")
            await callback.answer()
            return
        await _go_to_tools(callback.message, state)
        await callback.answer()
        return

    if action in selected:
        selected.remove(action)
    else:
        selected.append(action)
    await state.update_data(engine=selected)
    await callback.message.edit_reply_markup(
        reply_markup=engine_keyboard(set(selected), has_other="Other" in selected),
    )
    await callback.answer()


@router.message(RegistrationStates.engine_other)
async def process_engine_other(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Укажите движок:")
        return
    await state.update_data(engine_other=text)
    await _go_to_tools(message, state)


@router.callback_query(RegistrationStates.tools, F.data.startswith("tool:"))
async def toggle_tool(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected: list[str] = list(data.get("tools", []))

    if action == "done":
        if not selected:
            await callback.answer("Выберите хотя бы один инструмент", show_alert=True)
            return
        if "Other" in selected and not data.get("tools_other"):
            await state.set_state(RegistrationStates.tools_other)
            await callback.message.edit_text("Укажите другие инструменты (текстом):")
            await callback.answer()
            return
        await _go_to_motivation(callback.message, state)
        await callback.answer()
        return

    if action in selected:
        selected.remove(action)
    else:
        selected.append(action)
    await state.update_data(tools=selected)
    await callback.message.edit_reply_markup(
        reply_markup=tools_keyboard(set(selected), has_other="Other" in selected),
    )
    await callback.answer()


@router.message(RegistrationStates.tools_other)
async def process_tools_other(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Укажите хотя бы один инструмент:")
        return
    await state.update_data(tools_other=text)
    await _go_to_motivation(message, state)


@router.callback_query(RegistrationStates.motivation, F.data.startswith("mot:"))
async def toggle_motivation(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected: list[str] = list(data.get("motivations", []))

    if action == "done":
        if not selected:
            await callback.answer("Выберите хотя бы один пункт", show_alert=True)
            return
        await state.set_state(RegistrationStates.confirm)
        summary = _build_summary(data | {"motivations": selected})
        await callback.message.edit_text(
            "<b>Проверьте данные перед отправкой:</b>\n\n" + summary,
            reply_markup=confirm_keyboard(),
        )
        await callback.answer()
        return

    if action in selected:
        selected.remove(action)
    else:
        selected.append(action)
    await state.update_data(motivations=selected)
    await callback.message.edit_reply_markup(
        reply_markup=motivation_keyboard(set(selected)),
    )
    await callback.answer()


@router.callback_query(RegistrationStates.confirm, F.data == "confirm:restart")
async def confirm_restart(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(RegistrationStates.consent)
    await callback.message.edit_text(_consent_text(), reply_markup=consent_keyboard())
    await callback.answer()


@router.callback_query(RegistrationStates.confirm, F.data == "confirm:submit")
async def confirm_submit(
    callback: CallbackQuery,
    state: FSMContext,
    services: ServiceContainer,
) -> None:
    data = await state.get_data()

    try:
        payload = RegistrationCreate.from_fsm_data(
            data=data,
            telegram_id=callback.from_user.id,
            telegram_username=callback.from_user.username,
        )
    except ValidationError as exc:
        await callback.answer(services.users.format_validation_error(exc), show_alert=True)
        return

    try:
        application = await services.applications.submit_registration(payload)
    except ActiveApplicationExistsError:
        await callback.answer("У вас уже есть активная заявка.", show_alert=True)
        return

    # Commit explicitly here so the application is durably persisted BEFORE we
    # notify admins. The DbSessionMiddleware would otherwise only commit after
    # this handler returns — meaning a notification failure (or a crash mid-send)
    # could leave admins pinged about an un-persisted row, or vice versa.
    await services.session.commit()

    await state.clear()
    await callback.message.edit_text(
        "✅ <b>Заявка отправлена!</b>\n\n"
        f"Ваш ID: <code>{application.id}</code>\n\n"
        "Статус: <b>на ручной проверке</b>\n"
        "Мы свяжемся с вами по email после проверки.\n\n"
        "Проверить статус: /status",
    )
    await callback.message.answer("Регистрация завершена.", reply_markup=ReplyKeyboardRemove())

    logger.info(
        "application submitted",
        extra={"extra_fields": {"application_id": application.id, "telegram_id": callback.from_user.id}},
    )

    if services.notifications:
        logger.debug("dispatching admin notification for application %s", application.id)
        await services.notifications.notify_admins_new_application(application)
        logger.debug("admin notification dispatch returned for application %s", application.id)
    else:
        logger.warning(
            "notification service unavailable — admins NOT notified about application %s",
            application.id,
        )

    await callback.answer("Заявка принята!")


@router.callback_query(F.data == "nav:back_category")
async def nav_back_category(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RegistrationStates.category)
    await callback.message.edit_text(
        "<b>Шаг B — Категория</b>\n\nВыберите основное направление:",
        reply_markup=categories_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "nav:back_roles")
async def nav_back_roles(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    category = CATEGORY_BY_ID[data["category_id"]]
    await state.set_state(RegistrationStates.roles)
    await callback.message.edit_text(
        _roles_prompt(category),
        reply_markup=roles_keyboard(
            category.id,
            set(data.get("roles", [])),
            page=data.get("role_page", 0),
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "nav:back_exp")
async def nav_back_exp(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RegistrationStates.experience)
    await callback.message.edit_text(
        "<b>Шаг C — Уровень опыта</b>\n\nВыберите ваш уровень:",
        reply_markup=experience_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "nav:back_engine")
async def nav_back_engine(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(RegistrationStates.engine)
    selected = set(data.get("engine", []))
    await callback.message.edit_text(
        "<b>Шаг D — Движок</b>\n\nВыберите движок:",
        reply_markup=engine_keyboard(selected, has_other="Other" in selected),
    )
    await callback.answer()


@router.callback_query(F.data == "nav:back_tools")
async def nav_back_tools(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(RegistrationStates.tools)
    selected = set(data.get("tools", []))
    await callback.message.edit_text(
        "<b>Шаг E — Инструменты</b>\n\nВыберите инструменты:",
        reply_markup=tools_keyboard(selected, has_other="Other" in selected),
    )
    await callback.answer()
