from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.data.catalog import (
    BLUEPRINT_SUBCATEGORIES,
    EXPERIENCE_LEVELS,
    MAIN_CATEGORIES,
    MOTIVATIONS,
    SKILL_BY_ID,
    SKILL_CATEGORIES,
    TOOLS,
)


def consent_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Принимаю все условия", callback_data="consent:accept")
    builder.button(text="❌ Отмена", callback_data="consent:decline")
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="❌ Отменить регистрацию"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=False)


def main_categories_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in MAIN_CATEGORIES.items():
        builder.button(text=label, callback_data=f"main_cat:{key}")
    builder.button(text="📋 Все направления (детально)", callback_data="main_cat:detailed")
    builder.adjust(1)
    return builder.as_markup()


def blueprint_subcategories_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in BLUEPRINT_SUBCATEGORIES:
        builder.button(text=item, callback_data=f"bp_sub:{item}")
    builder.button(text="⬅️ Назад", callback_data="nav:back_main_cat")
    builder.adjust(2)
    return builder.as_markup()


def skill_categories_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in SKILL_CATEGORIES:
        builder.button(text=category.title, callback_data=f"skill:{category.id}")
    builder.button(text="⬅️ Назад", callback_data="nav:back_main_cat")
    builder.adjust(1)
    return builder.as_markup()


def subcategories_keyboard(
    category_id: str,
    selected: set[str],
    *,
    page: int = 0,
    page_size: int = 5,
) -> InlineKeyboardMarkup:
    items = list(SKILL_BY_ID[category_id].subcategories)
    start = page * page_size
    chunk = items[start : start + page_size]
    total_pages = max(1, (len(items) + page_size - 1) // page_size)

    builder = InlineKeyboardBuilder()
    for item in chunk:
        prefix = "✓ " if item in selected else ""
        builder.button(text=f"{prefix}{item}", callback_data=f"subcat:{item}")

    builder.adjust(1)

    nav_row: list[InlineKeyboardButton] = []
    if start > 0:
        nav_row.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"subcat_page:{page - 1}")
        )
    if total_pages > 1:
        nav_row.append(
            InlineKeyboardButton(
                text=f"· {page + 1}/{total_pages} ·",
                callback_data="subcat:noop",
            )
        )
    if start + page_size < len(items):
        nav_row.append(
            InlineKeyboardButton(text="Далее ▶️", callback_data=f"subcat_page:{page + 1}")
        )
    if nav_row:
        builder.row(*nav_row)

    builder.row(
        InlineKeyboardButton(text="✅ Готово", callback_data="subcat:done"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back_skill"),
    )
    return builder.as_markup()


def experience_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in EXPERIENCE_LEVELS.items():
        builder.button(text=label, callback_data=f"exp:{key}")
    builder.button(text="⬅️ Назад", callback_data="nav:back_subcat")
    builder.adjust(1)
    return builder.as_markup()


def tools_keyboard(selected: set[str], *, has_other: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tool in TOOLS:
        prefix = "✓ " if tool in selected else ""
        builder.button(text=f"{prefix}{tool}", callback_data=f"tool:{tool}")
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text="✅ Готово", callback_data="tool:done"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back_exp"),
    )
    return builder.as_markup()


def motivation_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in MOTIVATIONS:
        prefix = "✓ " if item in selected else ""
        builder.button(text=f"{prefix}{item}", callback_data=f"mot:{item}")
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text="✅ Готово", callback_data="mot:done"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back_tools"),
    )
    return builder.as_markup()


def confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Отправить заявку", callback_data="confirm:submit")
    builder.button(text="🔄 Начать заново", callback_data="confirm:restart")
    builder.adjust(1)
    return builder.as_markup()
