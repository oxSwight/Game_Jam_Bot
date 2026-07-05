from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.data.catalog import (
    CATEGORIES,
    CATEGORY_BY_ID,
    ENGINES,
    EXPERIENCE_LEVELS,
    MOTIVATIONS,
    TOOLS,
)


def language_keyboard() -> InlineKeyboardMarkup:
    from app.core.i18n import LANG_TITLES

    builder = InlineKeyboardBuilder()
    for code, title in LANG_TITLES.items():
        builder.button(text=title, callback_data=f"lang:{code}")
    builder.adjust(1)
    return builder.as_markup()


def edit_field_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Никнейм", callback_data="edit:nickname")
    builder.button(text="✏️ Email", callback_data="edit:email")
    builder.button(text="✖️ Отмена", callback_data="edit:cancel")
    builder.adjust(2, 1)
    return builder.as_markup()


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


def categories_keyboard() -> InlineKeyboardMarkup:
    """Tier 1 — parent categories."""
    builder = InlineKeyboardBuilder()
    for category in CATEGORIES:
        builder.button(text=category.title, callback_data=f"cat:{category.id}")
    builder.adjust(1)
    return builder.as_markup()


def roles_keyboard(
    category_id: str,
    selected: set[str],
    *,
    page: int = 0,
    page_size: int = 6,
) -> InlineKeyboardMarkup:
    """Tier 2 — paginated, multi-select roles within a category."""
    items = list(CATEGORY_BY_ID[category_id].roles)
    start = page * page_size
    chunk = items[start : start + page_size]
    total_pages = max(1, (len(items) + page_size - 1) // page_size)

    builder = InlineKeyboardBuilder()
    for role in chunk:
        prefix = "✓ " if role.id in selected else ""
        builder.button(text=f"{prefix}{role.title}", callback_data=f"role:{role.id}")
    builder.adjust(1)

    nav_row: list[InlineKeyboardButton] = []
    if start > 0:
        nav_row.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"role_page:{page - 1}")
        )
    if total_pages > 1:
        nav_row.append(
            InlineKeyboardButton(
                text=f"· {page + 1}/{total_pages} ·",
                callback_data="role:noop",
            )
        )
    if start + page_size < len(items):
        nav_row.append(
            InlineKeyboardButton(text="Далее ▶️", callback_data=f"role_page:{page + 1}")
        )
    if nav_row:
        builder.row(*nav_row)

    builder.row(
        InlineKeyboardButton(text="✅ Готово", callback_data="role:done"),
        InlineKeyboardButton(text="⬅️ К категориям", callback_data="nav:back_category"),
    )
    return builder.as_markup()


def experience_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in EXPERIENCE_LEVELS.items():
        builder.button(text=label, callback_data=f"exp:{key}")
    builder.button(text="⬅️ Назад", callback_data="nav:back_roles")
    builder.adjust(1)
    return builder.as_markup()


def engine_keyboard(selected: set[str], *, has_other: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for engine in ENGINES:
        prefix = "✓ " if engine in selected else ""
        builder.button(text=f"{prefix}{engine}", callback_data=f"engine:{engine}")
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text="✅ Готово", callback_data="engine:done"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back_exp"),
    )
    return builder.as_markup()


def tools_keyboard(selected: set[str], *, has_other: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tool in TOOLS:
        prefix = "✓ " if tool in selected else ""
        builder.button(text=f"{prefix}{tool}", callback_data=f"tool:{tool}")
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text="✅ Готово", callback_data="tool:done"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back_engine"),
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
