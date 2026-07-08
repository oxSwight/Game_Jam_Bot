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
    option_label,
)

# Reply-keyboard label for aborting registration. Kept as a module constant so the
# handler filter and the keyboard builder can't drift apart.
CANCEL_LABEL = "Отменить регистрацию"


def language_keyboard() -> InlineKeyboardMarkup:
    from app.core.i18n import LANG_TITLES

    builder = InlineKeyboardBuilder()
    for code, title in LANG_TITLES.items():
        builder.button(text=title, callback_data=f"lang:{code}")
    builder.adjust(1)
    return builder.as_markup()


_START_REGISTRATION_LABELS = {
    "ru": "▶️ Начать регистрацию",
    "en": "▶️ Start registration",
}


def start_registration_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """One-tap entry into the sign-up funnel. Offered on the /start and
    post-language landings so a new user isn't left having to discover /register
    on their own (callback fires cb_start_registration)."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=_START_REGISTRATION_LABELS.get(lang, _START_REGISTRATION_LABELS["ru"]),
        callback_data="reg:start",
    )
    return builder.as_markup()


def captcha_keyboard(options: list[str]) -> InlineKeyboardMarkup:
    """Emoji buttons for the anti-bot gate, four per row. Each button carries
    only its index in callback_data (cap:<i>), never the emoji itself."""
    builder = InlineKeyboardBuilder()
    for idx, emoji in enumerate(options):
        builder.button(text=emoji, callback_data=f"cap:{idx}")
    builder.adjust(4)
    return builder.as_markup()


def edit_field_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Никнейм", callback_data="edit:nickname")
    builder.button(text="Email", callback_data="edit:email")
    builder.button(text="Навыки и категория", callback_data="edit:skills")
    builder.button(text="Отмена", callback_data="edit:cancel")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


_CONSENT_LABELS = {
    "ru": ("Принимаю условия", "Отказаться"),
    "en": ("I accept the terms", "Decline"),
}


def consent_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    accept, decline = _CONSENT_LABELS.get(lang, _CONSENT_LABELS["ru"])
    builder = InlineKeyboardBuilder()
    builder.button(text=accept, callback_data="consent:accept")
    builder.button(text=decline, callback_data="consent:decline")
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=CANCEL_LABEL))
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
            InlineKeyboardButton(text="Назад", callback_data=f"role_page:{page - 1}")
        )
    if total_pages > 1:
        nav_row.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data="role:noop",
            )
        )
    if start + page_size < len(items):
        nav_row.append(
            InlineKeyboardButton(text="Далее", callback_data=f"role_page:{page + 1}")
        )
    if nav_row:
        builder.row(*nav_row)

    builder.row(
        InlineKeyboardButton(text="Готово", callback_data="role:done"),
        InlineKeyboardButton(text="К категориям", callback_data="nav:back_category"),
    )
    return builder.as_markup()


def experience_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in EXPERIENCE_LEVELS.items():
        builder.button(text=label, callback_data=f"exp:{key}")
    builder.button(text="Назад", callback_data="nav:back_roles")
    builder.adjust(1)
    return builder.as_markup()


def engine_keyboard(selected: set[str], *, has_other: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for engine in ENGINES:
        prefix = "✓ " if engine in selected else ""
        builder.button(text=f"{prefix}{option_label(engine)}", callback_data=f"engine:{engine}")
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text="Готово", callback_data="engine:done"),
        InlineKeyboardButton(text="Назад", callback_data="nav:back_exp"),
    )
    return builder.as_markup()


def tools_keyboard(selected: set[str], *, has_other: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tool in TOOLS:
        prefix = "✓ " if tool in selected else ""
        builder.button(text=f"{prefix}{option_label(tool)}", callback_data=f"tool:{tool}")
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text="Готово", callback_data="tool:done"),
        InlineKeyboardButton(text="Назад", callback_data="nav:back_engine"),
    )
    return builder.as_markup()


def motivation_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in MOTIVATIONS:
        prefix = "✓ " if item in selected else ""
        builder.button(text=f"{prefix}{item}", callback_data=f"mot:{item}")
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text="Готово", callback_data="mot:done"),
        InlineKeyboardButton(text="Назад", callback_data="nav:back_tools"),
    )
    return builder.as_markup()


def confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Отправить заявку", callback_data="confirm:submit")
    builder.button(text="Начать заново", callback_data="confirm:restart")
    builder.adjust(1)
    return builder.as_markup()
