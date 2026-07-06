import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.i18n import t
from app.data.captcha import build_captcha
from app.data.catalog import (
    CATEGORY_BY_ID,
    CONSENT_ITEMS,
    EXPERIENCE_LEVELS,
    MAIN_CATEGORIES,
    role_ids_from_titles,
    role_titles,
)
from app.keyboards.registration import (
    CANCEL_LABEL,
    cancel_keyboard,
    captcha_keyboard,
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
from app.utils.validation import contains_url

router = Router()
logger = logging.getLogger(__name__)

# Upper bound for the free-text "Other" engine/tool inputs. The rest of the form
# is pick-from-list; these two are the only open text fields a regular user can
# submit, so we cap them to keep stored data (and rendered messages) sane.
OTHER_TEXT_MAX = 64


def not_command(message: Message) -> bool:
    """Filter: a message that is NOT a slash-command. Applied to free-text FSM
    steps so a command (e.g. /language) typed mid-flow isn't swallowed as input —
    the handler doesn't match, and the message falls through to its command
    handler instead. /cancel still works: its handler is registered first."""
    return not (message.text or "").startswith("/")


async def _reset_on_url(message: Message, state: FSMContext, lang: str) -> bool:
    """Anti-spam guard for every free-text step: if the answer carries a link,
    wipe the whole FSM and tell the user to start over. Returns True when it
    tripped, so callers bail out immediately."""
    if contains_url(message.text):
        await state.clear()
        await message.answer(t("url_forbidden", lang), reply_markup=ReplyKeyboardRemove())
        return True
    return False


def _status_label(status: str, lang: str) -> str:
    return t(f"status_{status}", lang) if status in {
        "pending_review", "approved", "rejected"
    } else status


def _consent_text() -> str:
    items = "\n".join(f"• {item}" for item in CONSENT_ITEMS)
    return (
        "<b>Регистрация в игровую группу</b>\n\n"
        "Перед началом подтвердите, что вы:\n"
        f"{items}\n\n"
        "Нажмите кнопку ниже, чтобы продолжить."
    )


def _build_summary(data: dict) -> str:
    roles = ", ".join(safe(title) for title in role_titles(data.get("roles", []))) or "—"
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
    data = await state.get_data()
    # Fresh registration starts with nothing selected; an edit keeps the current
    # picks so they come pre-checked and the player only changes what they want.
    if not data.get("edit_mode"):
        await state.update_data(motivations=[])
        data = await state.get_data()
    await state.set_state(RegistrationStates.motivation)
    await message.answer(
        "<b>Шаг G — Мотивация</b>\n\n"
        "Что вас привлекает? (можно несколько):",
        reply_markup=motivation_keyboard(set(data.get("motivations", []))),
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
                id=safe(str(profile.player_code) if profile.player_code else profile.id),
            )
        )
        return

    # Known returning player (registered before, no active application now) — the
    # bot remembers them even if they left the group. Greet them back by name.
    user = await services.users.get_by_telegram_id(message.from_user.id)
    if user and user.nickname:
        await message.answer(t("welcome_back", lang, nickname=safe(user.nickname)))
        return

    # First contact: greet in the region-detected language, and offer an explicit
    # RU/EN switch so anyone the auto-detection guessed wrong can fix it in a tap.
    # Returning users who already chose a language aren't nagged with the picker.
    saved_lang = await services.users.get_language(message.from_user.id)
    if saved_lang:
        await message.answer(t("welcome", lang))
    else:
        await message.answer(t("welcome", lang), reply_markup=language_keyboard())


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

    # Queue cap: refuse new sign-ups once the pending backlog is full, so a flood
    # can't grow the review queue without bound.
    pending = await services.applications.count_pending()
    if pending >= get_settings().pending_cap:
        await message.answer(t("queue_full", lang))
        return

    # Anti-bot gate: the user must tap the named emoji before the form opens.
    options, target_index = build_captcha()
    await state.set_state(RegistrationStates.captcha)
    await state.update_data(captcha_answer=target_index)
    await message.answer(
        t("captcha_prompt", lang, target=options[target_index]),
        reply_markup=captcha_keyboard(options),
    )


@router.callback_query(RegistrationStates.captcha, F.data.startswith("cap:"))
async def process_captcha(
    callback: CallbackQuery, state: FSMContext, lang: str = "ru"
) -> None:
    chosen = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    target = data.get("captcha_answer")
    if target is None or chosen != target:
        # Wrong emoji = fail closed: abandon the whole registration.
        await state.clear()
        await callback.message.edit_text(t("captcha_failed", lang))
        await callback.answer()
        return

    await state.set_state(RegistrationStates.consent)
    await state.update_data(captcha_answer=None)
    await callback.message.edit_text(_consent_text(), reply_markup=consent_keyboard())
    await callback.answer()


@router.message(Command("status"))
async def cmd_status(message: Message, services: ServiceContainer, lang: str = "ru") -> None:
    profile = await services.users.get_profile(message.from_user.id)
    if not profile:
        await message.answer(t("status_not_found", lang))
        return

    membership = "в группе" if profile.is_active else "не в группе"
    await message.answer(
        f"<b>Ваш профиль</b>\n\n"
        f"ID игрока: <code>{profile.player_code or '—'}</code>\n"
        f"Ник: {safe(profile.nickname)}\n"
        f"Email: {safe(profile.email)}\n"
        f"Категория: {safe(MAIN_CATEGORIES.get(profile.main_category, profile.skill_category_title))}\n"
        f"Роли: {', '.join(safe(s) for s in profile.subcategories) or '—'}\n"
        f"Опыт: {safe(EXPERIENCE_LEVELS.get(profile.experience_level, profile.experience_level))}\n"
        f"Движок: {join_with_other(profile.engine, profile.engine_other)}\n"
        f"Инструменты: {join_with_other(profile.tools, profile.tools_other)}\n"
        f"Мотивация: {', '.join(safe(m) for m in profile.motivations)}\n"
        f"Статус заявки: {safe(_status_label(profile.status, lang))}\n"
        f"Членство: {membership}",
    )


@router.message(Command("cancel"), RegistrationStates())
@router.message(F.text == CANCEL_LABEL, RegistrationStates())
async def cancel_registration(message: Message, state: FSMContext, lang: str = "ru") -> None:
    await state.clear()
    await message.answer(
        t("registration_cancelled", lang),
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(Command("withdraw"))
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


@router.callback_query(EditStates.field, F.data == "edit:skills")
async def edit_pick_skills(
    callback: CallbackQuery, state: FSMContext, services: ServiceContainer
) -> None:
    """Re-run the questionnaire to update skills/category on an existing
    application. We seed the current answers into FSM state and set edit_mode, so
    every existing registration step is reused as-is (roles/engine/tools/… come
    pre-selected); on confirm, confirm_submit updates the row instead of inserting
    a new one (see the edit_mode branch there)."""
    profile = await services.users.get_profile(callback.from_user.id)
    if not profile:
        await callback.answer("Активная заявка не найдена.", show_alert=True)
        await state.clear()
        return

    await state.set_state(RegistrationStates.category)
    await state.update_data(
        edit_mode=True,
        edit_app_id=profile.id,
        # nickname/email are needed by the category-step guard and by the final
        # payload; they're edited separately, so we carry the current values.
        nickname=profile.nickname,
        email=profile.email,
        category_id=profile.main_category,
        category_title=profile.skill_category_title,
        roles=role_ids_from_titles(profile.subcategories),
        role_page=0,
        experience_level=profile.experience_level,
        engine=list(profile.engine),
        engine_other=profile.engine_other,
        tools=list(profile.tools),
        tools_other=profile.tools_other,
        motivations=list(profile.motivations),
        consent=True,
    )
    await callback.message.edit_text(
        "<b>Изменение профиля</b>\n\n"
        "Пройдите анкету заново — текущие ответы уже отмечены. Меняйте что нужно "
        "и жмите «Готово» на каждом шаге.\n\n"
        "<b>Шаг B — Категория</b>\nВыберите основное направление:",
        reply_markup=categories_keyboard(),
    )
    await callback.answer()


@router.message(Command("cancel"), EditStates.field)
@router.message(Command("cancel"), EditStates.nickname)
@router.message(Command("cancel"), EditStates.email)
async def cancel_edit(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Изменение отменено.")


@router.message(EditStates.nickname, not_command)
async def edit_apply_nickname(
    message: Message, state: FSMContext, services: ServiceContainer, lang: str = "ru"
) -> None:
    if await _reset_on_url(message, state, lang):
        return
    try:
        step = NicknameStep(nickname=message.text or "")
    except ValidationError as exc:
        await message.answer(services.users.format_validation_error(exc))
        return
    await _apply_edit(message, state, services, nickname=step.nickname)


@router.message(EditStates.email, not_command)
async def edit_apply_email(
    message: Message, state: FSMContext, services: ServiceContainer, lang: str = "ru"
) -> None:
    if await _reset_on_url(message, state, lang):
        return
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
        await message.answer("Данные обновлены. /status — посмотреть профиль.")
    else:
        await message.answer("Активная заявка не найдена.")


@router.message(Command("help"))
async def cmd_help(message: Message, is_admin: bool = False) -> None:
    lines = [
        "<b>Команды</b>\n",
        "/register — подать заявку",
        "/status — статус вашей заявки",
        "/edit — изменить ник, email, навыки и категорию",
        "/withdraw — удалить свою заявку и подать заново",
        "/language — сменить язык",
    ]
    if is_admin:
        lines += [
            "\n<b>Админ:</b>",
            "/review — очередь заявок: одобрение и отклонение",
            "/stats — статистика",
            "/export — выгрузка CSV",
            "/broadcast — рассылка одобренным",
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
        "<b>Шаг A — Базовая информация</b>\n\n"
        "Введите ваш <b>никнейм</b> (отображаемое имя в группе):\n\n"
        "<i>Можно отменить в любой момент — кнопка ниже.</i>",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(RegistrationStates.nickname, not_command)
async def process_nickname(
    message: Message,
    state: FSMContext,
    services: ServiceContainer,
    lang: str = "ru",
) -> None:
    if await _reset_on_url(message, state, lang):
        return
    try:
        step = NicknameStep(nickname=message.text or "")
    except ValidationError as exc:
        await message.answer(services.users.format_validation_error(exc))
        return

    await state.update_data(nickname=step.nickname)
    await state.set_state(RegistrationStates.email)
    await message.answer("Введите ваш <b>email</b> для связи:")


@router.message(RegistrationStates.email, not_command)
async def process_email(
    message: Message,
    state: FSMContext,
    services: ServiceContainer,
    lang: str = "ru",
) -> None:
    if await _reset_on_url(message, state, lang):
        return
    try:
        step = EmailStep(email=message.text or "")
    except ValidationError as exc:
        await message.answer(services.users.format_validation_error(exc))
        return

    await state.update_data(email=str(step.email))

    data = await state.get_data()
    if data.get("awaiting_contact_fix"):
        # Coming back from a duplicate nickname/email collision: they've now
        # re-entered both, so jump straight back to confirm instead of making
        # them re-walk category → roles → engine → tools → motivation.
        await state.update_data(awaiting_contact_fix=False)
        await state.set_state(RegistrationStates.confirm)
        await message.answer(
            "<b>Проверьте данные перед отправкой:</b>\n\n" + _build_summary(data),
            reply_markup=confirm_keyboard(),
        )
        return

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

    # Roles belong to a category, so switching category always clears them. When
    # editing and re-confirming the SAME category, keep the current selection so
    # the player doesn't have to re-pick roles just to tweak a later step.
    keep_roles = data.get("edit_mode") and data.get("category_id") == category.id
    await state.update_data(
        category_id=category.id,
        category_title=category.title,
        roles=data.get("roles", []) if keep_roles else [],
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
    data = await state.get_data()
    # Editing keeps the current engine selection (pre-checked); registration clears it.
    if data.get("edit_mode"):
        await state.update_data(experience_level=level)
        engine = list(data.get("engine", []))
    else:
        await state.update_data(experience_level=level, engine=[], engine_other=None)
        engine = []
    await state.set_state(RegistrationStates.engine)
    await callback.message.edit_text(
        "<b>Шаг D — Движок</b>\n\n"
        "Выберите движок, в котором работаете (можно несколько):",
        reply_markup=engine_keyboard(set(engine), has_other="Other" in engine),
    )
    await callback.answer()


async def _go_to_tools(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    # Editing keeps the current tools selection (pre-checked); registration clears it.
    if not data.get("edit_mode"):
        await state.update_data(tools=[], tools_other=None)
        data = await state.get_data()
    selected = set(data.get("tools", []))
    await state.set_state(RegistrationStates.tools)
    await message.answer(
        "<b>Шаг E — Инструменты</b>\n\n"
        "Выберите инструменты, с которыми работаете (можно несколько):",
        reply_markup=tools_keyboard(selected, has_other="Other" in selected),
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


@router.message(RegistrationStates.engine_other, not_command)
async def process_engine_other(
    message: Message, state: FSMContext, lang: str = "ru"
) -> None:
    if await _reset_on_url(message, state, lang):
        return
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Укажите движок:")
        return
    if len(text) > OTHER_TEXT_MAX:
        await message.answer(f"Слишком длинно (максимум {OTHER_TEXT_MAX} символов). Короче:")
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


@router.message(RegistrationStates.tools_other, not_command)
async def process_tools_other(
    message: Message, state: FSMContext, lang: str = "ru"
) -> None:
    if await _reset_on_url(message, state, lang):
        return
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Укажите хотя бы один инструмент:")
        return
    if len(text) > OTHER_TEXT_MAX:
        await message.answer(f"Слишком длинно (максимум {OTHER_TEXT_MAX} символов). Короче:")
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

    if data.get("edit_mode"):
        # Editing an existing profile: update the row in place (status preserved),
        # don't create a new application.
        updated = await services.applications.update_profile(callback.from_user.id, payload)
        await services.session.commit()
        await state.clear()
        if updated:
            await callback.message.edit_text(
                "<b>Профиль обновлён.</b>\n\n" + _build_summary(data)
            )
            await callback.message.answer("Готово. /status — посмотреть профиль.")
            await callback.answer("Обновлено")
        else:
            await callback.message.edit_text("Активная заявка не найдена. /register")
            await callback.answer()
        return

    try:
        application = await services.applications.submit_registration(payload)
        await services.session.commit()
    except ActiveApplicationExistsError:
        await callback.answer("У вас уже есть активная заявка.", show_alert=True)
        return
    except IntegrityError:
        # nickname and email are UNIQUE — someone already took the one they chose.
        # Roll back the failed unit of work and route them back to re-enter their
        # contact details rather than dead-ending on the confirm screen with a
        # cryptic error they can only repeat. Their category/roles/engine/etc. stay
        # in FSM data, so re-entering nickname+email returns them straight to
        # confirm (see the awaiting_contact_fix branch in process_email).
        await services.session.rollback()
        await state.update_data(awaiting_contact_fix=True)
        await state.set_state(RegistrationStates.nickname)
        await callback.answer(
            "Такой ник или email уже заняты. Введите их заново.", show_alert=True
        )
        await callback.message.answer("Введите другой <b>никнейм</b>:")
        return

    await state.clear()
    # Admins are NOT pushed a message per application (that would burn Telegram's
    # rate limits under a flood). They pull the queue on demand via /review.
    await callback.message.edit_text(
        "<b>Заявка отправлена.</b>\n\n"
        f"Ваш ID: <code>{application.id}</code>\n\n"
        "Статус: на ручной проверке.\n"
        "После одобрения вы получите персональную ссылку на вступление в группу.\n\n"
        "Проверить статус: /status",
    )
    await callback.message.answer("Регистрация завершена.", reply_markup=ReplyKeyboardRemove())

    logger.info(
        "application submitted",
        extra={"extra_fields": {"application_id": application.id, "telegram_id": callback.from_user.id}},
    )
    await callback.answer("Заявка принята")


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
