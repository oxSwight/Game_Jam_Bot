import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from pydantic import ValidationError

from app.utils.html import safe

from app.schemas.registration import EmailStep, NicknameStep, RegistrationCreate
from app.services import ServiceContainer
from app.services.application import ActiveApplicationExistsError
from app.states.registration import RegistrationStates
from app.data.catalog import (
    CONSENT_ITEMS,
    EXPERIENCE_LEVELS,
    MAIN_CATEGORIES,
    MAIN_TO_SKILL,
    SKILL_BY_ID,
)
from app.keyboards.registration import (
    blueprint_subcategories_keyboard,
    cancel_keyboard,
    confirm_keyboard,
    consent_keyboard,
    experience_keyboard,
    main_categories_keyboard,
    motivation_keyboard,
    skill_categories_keyboard,
    subcategories_keyboard,
    tools_keyboard,
)

router = Router()
logger = logging.getLogger(__name__)

STATUS_LABELS = {
    "pending_review": "⏳ на ручной проверке",
    "approved": "✅ одобрена",
    "rejected": "❌ отклонена",
}


def _consent_text() -> str:
    items = "\n".join(f"• {item}" for item in CONSENT_ITEMS)
    return (
        "🎮 <b>Регистрация на платформу GameJam</b>\n\n"
        "Перед началом подтвердите, что вы:\n"
        f"{items}\n\n"
        "Нажмите кнопку ниже, чтобы продолжить."
    )


def _build_summary(data: dict) -> str:
    subcats = ", ".join(safe(s) for s in data.get("subcategories", [])) or "—"
    tools = list(data.get("tools", []))
    if data.get("tools_other"):
        # tools_other is free-text — escape it; catalog tool names are safe but escape defensively
        tools = [safe(data["tools_other"]) if t == "Other" else safe(t) for t in tools]
    else:
        tools = [safe(t) for t in tools]
    motivations = ", ".join(safe(m) for m in data.get("motivations", []))

    lines = [
        f"👤 <b>Ник:</b> {safe(data.get('nickname'))}",
        f"📧 <b>Email:</b> {safe(data.get('email'))}",
        f"📂 <b>Категория:</b> {safe(MAIN_CATEGORIES.get(data.get('main_category', ''), data.get('main_category', '')))}",
    ]
    if data.get("blueprint_subcategory"):
        lines.append(f"🔧 <b>Blueprint подкатегория:</b> {safe(data['blueprint_subcategory'])}")
    lines += [
        f"🎯 <b>Направление:</b> {safe(data.get('skill_category_title', '—'))}",
        f"📌 <b>Подкатегории:</b> {subcats}",
        f"📊 <b>Опыт:</b> {safe(EXPERIENCE_LEVELS.get(data.get('experience_level', ''), '—'))}",
        f"🛠 <b>Инструменты:</b> {', '.join(tools)}",
        f"💡 <b>Мотивация:</b> {motivations}",
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
) -> None:
    await state.clear()
    profile = await services.users.get_profile(message.from_user.id)
    if profile:
        status = STATUS_LABELS.get(profile.status, profile.status)
        await message.answer(
            f"Привет, <b>{safe(profile.nickname)}</b>!\n\n"
            f"Ваша заявка уже зарегистрирована.\n"
            f"Статус: {safe(status)}\n"
            f"ID: <code>{profile.id}</code>\n\n"
            "Чтобы подать новую заявку, используйте /register",
        )
        return

    await message.answer(
        "👋 Добро пожаловать в бот регистрации игроков!\n\n"
        "Здесь вы можете подать заявку на участие в платформе.\n\n"
        "Для регистрации: /register",
    )


@router.message(Command("register"))
@router.message(Command("reg"))
async def cmd_register(
    message: Message,
    state: FSMContext,
    services: ServiceContainer,
) -> None:
    await state.clear()
    if await services.applications.has_active_application(message.from_user.id):
        await message.answer(
            "У вас уже есть активная заявка. Дождитесь проверки или обратитесь к администратору.",
        )
        return

    await state.set_state(RegistrationStates.consent)
    await message.answer(_consent_text(), reply_markup=consent_keyboard())


@router.message(Command("status"))
async def cmd_status(message: Message, services: ServiceContainer) -> None:
    profile = await services.users.get_profile(message.from_user.id)
    if not profile:
        await message.answer("Заявка не найдена. Используйте /register")
        return

    await message.answer(
        f"📋 <b>Ваш профиль</b>\n\n"
        f"ID: <code>{profile.id}</code>\n"
        f"Ник: {safe(profile.nickname)}\n"
        f"Email: {safe(profile.email)}\n"
        f"Категория: {safe(MAIN_CATEGORIES.get(profile.main_category, profile.main_category))}\n"
        f"Направление: {safe(profile.skill_category_title)}\n"
        f"Подкатегории: {', '.join(safe(s) for s in profile.subcategories) or '—'}\n"
        f"Опыт: {safe(EXPERIENCE_LEVELS.get(profile.experience_level, profile.experience_level))}\n"
        f"Инструменты: {', '.join(safe(t) for t in profile.tools)}\n"
        f"Мотивация: {', '.join(safe(m) for m in profile.motivations)}\n"
        f"Статус: {safe(profile.status)}",
    )


@router.message(Command("cancel"), RegistrationStates())
@router.message(F.text == "❌ Отменить регистрацию", RegistrationStates())
async def cancel_registration(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Регистрация отменена.\nИспользуйте /register, чтобы начать снова.",
        reply_markup=ReplyKeyboardRemove(),
    )


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
    await state.set_state(RegistrationStates.main_category)
    await message.answer(
        "<b>Шаг B — Категория</b>\n\n"
        "Выберите основное направление:",
        reply_markup=main_categories_keyboard(),
    )


@router.callback_query(F.data.startswith("main_cat:"))
async def process_main_category(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("email") or not data.get("nickname"):
        await callback.answer("Сессия устарела. Начните заново: /register", show_alert=True)
        return
    await state.set_state(RegistrationStates.main_category)

    key = callback.data.split(":", 1)[1]
    if key == "detailed":
        await state.set_state(RegistrationStates.skill_category)
        await callback.message.edit_text(
            "<b>Выберите детальное направление:</b>",
            reply_markup=skill_categories_keyboard(),
        )
        await callback.answer()
        return

    await state.update_data(main_category=key)
    if key == "blueprint_programming":
        await state.set_state(RegistrationStates.blueprint_subcategory)
        await callback.message.edit_text(
            "<b>Blueprint / Programming</b>\n\n"
            "Выберите подкатегорию:",
            reply_markup=blueprint_subcategories_keyboard(),
        )
    else:
        skill_id = MAIN_TO_SKILL.get(key, "undecided")
        skill = SKILL_BY_ID[skill_id]
        await state.update_data(
            skill_category_id=skill.id,
            skill_category_title=skill.title,
            subcategories=[],
            subcat_page=0,
        )
        await state.set_state(RegistrationStates.subcategories)
        await callback.message.edit_text(
            f"<b>{skill.title}</b>\n<i>{skill.description}</i>\n\n"
            "Выберите подкатегории (можно несколько), затем нажмите «Готово»:",
            reply_markup=subcategories_keyboard(skill.id, set()),
        )
    await callback.answer()


@router.callback_query(RegistrationStates.blueprint_subcategory, F.data.startswith("bp_sub:"))
async def process_blueprint_sub(callback: CallbackQuery, state: FSMContext) -> None:
    sub = callback.data.split(":", 1)[1]
    await state.update_data(blueprint_subcategory=sub)

    skill_map = {
        "Level Design": "game_design",
        "Lighting": "lighting_vfx",
        "UI/UX": "ui_ux",
        "QA": "undecided",
    }
    skill_id = skill_map.get(sub, "programming")
    skill = SKILL_BY_ID[skill_id]
    await state.update_data(
        skill_category_id=skill.id,
        skill_category_title=skill.title,
        subcategories=[],
        subcat_page=0,
    )
    await state.set_state(RegistrationStates.subcategories)
    await callback.message.edit_text(
        f"<b>{skill.title}</b>\n<i>{skill.description}</i>\n\n"
        "Выберите подкатегории (можно несколько), затем нажмите «Готово»:",
        reply_markup=subcategories_keyboard(skill.id, set()),
    )
    await callback.answer()


@router.callback_query(RegistrationStates.skill_category, F.data.startswith("skill:"))
async def process_skill_category(callback: CallbackQuery, state: FSMContext) -> None:
    skill_id = callback.data.split(":", 1)[1]
    skill = SKILL_BY_ID[skill_id]
    await state.update_data(
        main_category=skill_id if skill_id in MAIN_CATEGORIES else "other",
        skill_category_id=skill.id,
        skill_category_title=skill.title,
        subcategories=[],
        subcat_page=0,
    )
    await state.set_state(RegistrationStates.subcategories)
    await callback.message.edit_text(
        f"<b>{skill.title}</b>\n<i>{skill.description}</i>\n\n"
        "Выберите подкатегории (можно несколько), затем нажмите «Готово»:",
        reply_markup=subcategories_keyboard(skill.id, set()),
    )
    await callback.answer()


@router.callback_query(RegistrationStates.subcategories, F.data.startswith("subcat_page:"))
async def subcat_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    skill_id = data["skill_category_id"]
    selected = set(data.get("subcategories", []))
    await state.update_data(subcat_page=page)
    await callback.message.edit_reply_markup(
        reply_markup=subcategories_keyboard(skill_id, selected, page=page),
    )
    await callback.answer()


@router.callback_query(RegistrationStates.subcategories, F.data.startswith("subcat:"))
async def toggle_subcategory(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":", 1)[1]
    if action == "noop":
        await callback.answer()
        return

    data = await state.get_data()
    skill_id = data["skill_category_id"]
    selected: list[str] = list(data.get("subcategories", []))

    if action == "done":
        if not selected:
            await callback.answer("Выберите хотя бы одну подкатегорию", show_alert=True)
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
    await state.update_data(subcategories=selected)
    page = data.get("subcat_page", 0)
    await callback.message.edit_reply_markup(
        reply_markup=subcategories_keyboard(skill_id, set(selected), page=page),
    )
    await callback.answer()


@router.callback_query(RegistrationStates.experience, F.data.startswith("exp:"))
async def process_experience(callback: CallbackQuery, state: FSMContext) -> None:
    level = callback.data.split(":", 1)[1]
    await state.update_data(experience_level=level, tools=[], tools_other=None)
    await state.set_state(RegistrationStates.tools)
    await callback.message.edit_text(
        "<b>Шаг D — Инструменты</b>\n\n"
        "Выберите инструменты, с которыми работаете (можно несколько):",
        reply_markup=tools_keyboard(set(), has_other=False),
    )
    await callback.answer()


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

    await state.clear()
    await callback.message.edit_text(
        "✅ <b>Заявка отправлена!</b>\n\n"
        f"Ваш ID: <code>{application.id}</code>\n\n"
        "Статус: <b>на ручной проверке</b>\n"
        "Мы свяжемся с вами по email после проверки.\n\n"
        "Проверить статус: /status",
    )
    await callback.message.answer("Регистрация завершена.", reply_markup=ReplyKeyboardRemove())

    if services.notifications:
        await services.notifications.notify_admins_new_application(application)

    logger.info(
        "application submitted",
        extra={"extra_fields": {"application_id": application.id, "telegram_id": callback.from_user.id}},
    )
    await callback.answer("Заявка принята!")


@router.callback_query(F.data == "nav:back_main_cat")
async def nav_back_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RegistrationStates.main_category)
    await callback.message.edit_text(
        "<b>Шаг B — Категория</b>\n\nВыберите основное направление:",
        reply_markup=main_categories_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "nav:back_skill")
async def nav_back_skill(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RegistrationStates.skill_category)
    await callback.message.edit_text(
        "<b>Выберите детальное направление:</b>",
        reply_markup=skill_categories_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "nav:back_subcat")
async def nav_back_subcat(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    skill_id = data["skill_category_id"]
    skill = SKILL_BY_ID[skill_id]
    await state.set_state(RegistrationStates.subcategories)
    await callback.message.edit_text(
        f"<b>{skill.title}</b>\n<i>{skill.description}</i>\n\n"
        "Выберите подкатегории:",
        reply_markup=subcategories_keyboard(skill_id, set(data.get("subcategories", []))),
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


@router.callback_query(F.data == "nav:back_tools")
async def nav_back_tools(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(RegistrationStates.tools)
    await callback.message.edit_text(
        "<b>Шаг D — Инструменты</b>\n\nВыберите инструменты:",
        reply_markup=tools_keyboard(set(data.get("tools", [])), has_other=False),
    )
    await callback.answer()
