from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.core.i18n import t
from app.data.catalog import (
    CATEGORIES,
    CATEGORY_BY_ID,
    EXPERIENCE_LEVELS,
    MOTIVATIONS,
    NO_EXPERIENCE_OPTION,
    STRENGTHS,
    category_title,
    engine_none_label,
    engines_for,
    experience_label,
    option_label,
    tools_for,
    tools_none_label,
)

# Reply-keyboard labels for aborting registration, one per language. The handler
# filter matches against CANCEL_LABEL_VALUES so a user who switched language can
# still tap "Cancel" and be understood regardless of which label they see.
CANCEL_LABELS: dict[str, str] = {
    "ru": "Отменить регистрацию",
    "en": "Cancel registration",
}
CANCEL_LABEL_VALUES: frozenset[str] = frozenset(CANCEL_LABELS.values())


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


def edit_field_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_edit_nickname", lang), callback_data="edit:nickname")
    builder.button(text=t("btn_edit_email", lang), callback_data="edit:email")
    builder.button(text=t("btn_edit_skills", lang), callback_data="edit:skills")
    builder.button(text=t("btn_cancel", lang), callback_data="edit:cancel")
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


def cancel_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=CANCEL_LABELS.get(lang, CANCEL_LABELS["ru"])))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=False)


def categories_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Tier 1 - parent categories."""
    builder = InlineKeyboardBuilder()
    for category in CATEGORIES:
        builder.button(text=category_title(category.id, lang), callback_data=f"cat:{category.id}")
    builder.adjust(1)
    return builder.as_markup()


def roles_keyboard(
    category_id: str,
    selected: set[str],
    *,
    page: int = 0,
    page_size: int = 6,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    """Tier 2 - paginated, multi-select roles within a category. Role titles stay
    English in both languages (that's how they're stored and displayed)."""
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
            InlineKeyboardButton(text=t("btn_back", lang), callback_data=f"role_page:{page - 1}")
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
            InlineKeyboardButton(text=t("btn_next", lang), callback_data=f"role_page:{page + 1}")
        )
    if nav_row:
        builder.row(*nav_row)

    builder.row(
        InlineKeyboardButton(text=t("btn_done", lang), callback_data="role:done"),
        InlineKeyboardButton(text=t("btn_to_categories", lang), callback_data="nav:back_category"),
    )
    return builder.as_markup()


def experience_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key in EXPERIENCE_LEVELS:
        builder.button(text=experience_label(key, lang), callback_data=f"exp:{key}")
    builder.button(text=t("btn_back", lang), callback_data="nav:back_roles")
    builder.adjust(1)
    return builder.as_markup()


def _option_text(value: str, none_label: str, lang: str) -> str:
    """Button label for a multi-select value: the context-specific label for the
    "haven't worked" sentinel, otherwise the localized friendly/self label."""
    if value == NO_EXPERIENCE_OPTION:
        return none_label
    return option_label(value, lang)


def engine_keyboard(
    selected: set[str], *, category_id: str | None = None, has_other: bool = False,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    none_label = engine_none_label(category_id, lang)
    builder = InlineKeyboardBuilder()
    for engine in engines_for(category_id):
        prefix = "✓ " if engine in selected else ""
        builder.button(
            text=f"{prefix}{_option_text(engine, none_label, lang)}",
            callback_data=f"engine:{engine}",
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text=t("btn_done", lang), callback_data="engine:done"),
        InlineKeyboardButton(text=t("btn_back", lang), callback_data="nav:back_exp"),
    )
    return builder.as_markup()


def tools_keyboard(
    selected: set[str], *, category_id: str | None = None, has_other: bool = False,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    none_label = tools_none_label(category_id, lang)
    builder = InlineKeyboardBuilder()
    for tool in tools_for(category_id):
        prefix = "✓ " if tool in selected else ""
        builder.button(
            text=f"{prefix}{_option_text(tool, none_label, lang)}",
            callback_data=f"tool:{tool}",
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text=t("btn_done", lang), callback_data="tool:done"),
        InlineKeyboardButton(text=t("btn_back", lang), callback_data="nav:back_engine"),
    )
    return builder.as_markup()


def strengths_keyboard(selected: set[str], lang: str = "ru") -> InlineKeyboardMarkup:
    """Step F (beginner branch): multi-select of what the applicant is best at.
    Its "Back" returns to the tools step, the step right before it."""
    builder = InlineKeyboardBuilder()
    for item in STRENGTHS:
        prefix = "✓ " if item in selected else ""
        builder.button(text=f"{prefix}{option_label(item, lang)}", callback_data=f"strg:{item}")
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text=t("btn_done", lang), callback_data="strg:done"),
        InlineKeyboardButton(text=t("btn_back", lang), callback_data="nav:back_tools"),
    )
    return builder.as_markup()


def motivation_keyboard(
    selected: set[str], *, beginner: bool = False, lang: str = "ru"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in MOTIVATIONS:
        prefix = "✓ " if item in selected else ""
        builder.button(text=f"{prefix}{item}", callback_data=f"mot:{item}")
    builder.adjust(1)
    # Beginners have the extra strengths step (F) between tools and motivation,
    # so their "Back" returns there; everyone else goes back to tools.
    back = "nav:back_strengths" if beginner else "nav:back_tools"
    builder.row(
        InlineKeyboardButton(text=t("btn_done", lang), callback_data="mot:done"),
        InlineKeyboardButton(text=t("btn_back", lang), callback_data=back),
    )
    return builder.as_markup()


def confirm_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_send_application", lang), callback_data="confirm:submit")
    builder.button(text=t("btn_restart", lang), callback_data="confirm:restart")
    builder.adjust(1)
    return builder.as_markup()
