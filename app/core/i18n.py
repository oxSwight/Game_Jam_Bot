"""Minimal, dependency-free i18n.

A flat ``{key: {lang: text}}`` catalog plus a ``t(key, lang, **kwargs)`` lookup.
Keeps translation data in one place and lets handlers stay declarative:

    await message.answer(t("welcome", lang))

Design choices:
- No gettext/.po tooling — the string set is small and Python-native is easier
  to grep, test, and keep in sync with the code that uses it.
- Unknown keys raise in tests (via ``assert_catalog_complete``) but degrade to
  the key name at runtime so a missing translation never crashes a handler.
- ``DEFAULT_LANG`` is the fallback whenever a language lacks a given key.
"""

from __future__ import annotations

SUPPORTED_LANGS: tuple[str, ...] = ("ru", "en")
DEFAULT_LANG = "ru"

LANG_TITLES: dict[str, str] = {"ru": "🇷🇺 Русский", "en": "🇬🇧 English"}

# Telegram never gives a bot the user's country — only the client's UI language
# (language_code). We use it as a region proxy: post-Soviet / CIS locales default
# to Russian, everyone else to English. This is only the *default*; a saved
# /language choice always overrides it, and /start offers an explicit RU/EN pick.
CIS_LANG_CODES: frozenset[str] = frozenset(
    {"ru", "uk", "be", "kk", "ky", "uz", "tg", "tk", "hy", "az"}
)

# key -> {lang -> template}. Templates use str.format-style {placeholders}.
_MESSAGES: dict[str, dict[str, str]] = {
    "welcome": {
        "ru": (
            "Добро пожаловать в бот регистрации.\n\n"
            "Здесь вы подаёте заявку на вступление в закрытую игровую группу.\n\n"
            "Для регистрации: /register"
        ),
        "en": (
            "Welcome to the registration bot.\n\n"
            "Here you apply to join the closed game group.\n\n"
            "To register: /register"
        ),
    },
    "already_registered": {
        "ru": (
            "Здравствуйте, <b>{nickname}</b>.\n\n"
            "Ваша заявка уже зарегистрирована.\n"
            "Статус: {status}\n"
            "ID: <code>{id}</code>\n\n"
            "Чтобы подать новую заявку, используйте /register"
        ),
        "en": (
            "Hello, <b>{nickname}</b>.\n\n"
            "Your application is already registered.\n"
            "Status: {status}\n"
            "ID: <code>{id}</code>\n\n"
            "To submit a new application, use /register"
        ),
    },
    "active_application_exists": {
        "ru": "У вас уже есть активная заявка. Дождитесь проверки или обратитесь к администратору.",
        "en": "You already have an application. Wait for review or contact an admin.",
    },
    "welcome_back": {
        "ru": (
            "С возвращением, <b>{nickname}</b>! Мы вас помним.\n\n"
            "Чтобы подать новую заявку: /register\n"
            "Ваш статус: /status"
        ),
        "en": (
            "Welcome back, <b>{nickname}</b>! We remember you.\n\n"
            "To submit a new application: /register\n"
            "Your status: /status"
        ),
    },
    "welcome_back_group": {
        "ru": "С возвращением в игру, <b>{nickname}</b>! Рады видеть вас снова.",
        "en": "Welcome back to the game, <b>{nickname}</b>! Great to see you again.",
    },
    "queue_full": {
        "ru": "Очередь переполнена. Попробуйте позже.",
        "en": "The queue is full. Please try again later.",
    },
    "status_not_found": {
        "ru": "Заявка не найдена. Используйте /register",
        "en": "No application found. Use /register",
    },
    "registration_cancelled": {
        "ru": "Регистрация отменена.\nИспользуйте /register, чтобы начать снова.",
        "en": "Registration cancelled.\nUse /register to start again.",
    },
    "captcha_prompt": {
        "ru": "Подтвердите, что вы человек.\n\nНажмите на {target}",
        "en": "Confirm that you are human.\n\nTap the {target}",
    },
    "captcha_failed": {
        "ru": "Проверка не пройдена. Регистрация отменена. Начните заново: /register",
        "en": "Verification failed. Registration cancelled. Start again: /register",
    },
    "url_forbidden": {
        "ru": "Ссылки запрещены. Регистрация сброшена. Начните заново: /register",
        "en": "Links are not allowed. Registration was reset. Start again: /register",
    },
    "withdraw_done": {
        "ru": "Ваша заявка удалена.\nТеперь можно подать новую: /register",
        "en": "Your application was deleted.\nYou can now submit a new one: /register",
    },
    "withdraw_none": {
        "ru": "Активная заявка не найдена. Можно подать новую: /register",
        "en": "No active application found. You can submit a new one: /register",
    },
    "language_prompt": {
        "ru": "Выберите язык / Choose your language:",
        "en": "Choose your language / Выберите язык:",
    },
    "language_set": {
        "ru": "Язык переключён на русский.",
        "en": "Language switched to English.",
    },
    "status_pending_review": {"ru": "на ручной проверке", "en": "under manual review"},
    "status_approved": {"ru": "одобрена", "en": "approved"},
    "status_rejected": {"ru": "отклонена", "en": "rejected"},
    "notify_approved": {
        "ru": (
            "Ваша заявка одобрена.\n\n"
            "Вот ваша персональная ссылка на вступление в игру:\n{link}\n\n"
            "Ссылка одноразовая — не передавайте её другим."
        ),
        "en": (
            "Your application was approved.\n\n"
            "Here is your personal invite link to join the game:\n{link}\n\n"
            "The link is single-use — do not share it."
        ),
    },
    "notify_approved_no_link": {
        "ru": (
            "Ваша заявка одобрена. Пригласительную ссылку не удалось создать "
            "автоматически — с вами свяжется администратор."
        ),
        "en": (
            "Your application was approved. The invite link could not be created "
            "automatically — an admin will contact you."
        ),
    },
    "notify_rejected": {
        "ru": "Ваша заявка не прошла проверку. Вы можете подать новую через /register",
        "en": "Your application did not pass review. You can submit a new one via /register",
    },
    "notify_rejected_reason": {
        "ru": "Ваша заявка не прошла проверку.\n\n<b>Причина:</b> {reason}\n\nВы можете подать новую через /register",
        "en": "Your application did not pass review.\n\n<b>Reason:</b> {reason}\n\nYou can submit a new one via /register",
    },
}


def t(key: str, lang: str | None = None, /, **kwargs: object) -> str:
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    variants = _MESSAGES.get(key)
    if variants is None:
        return key
    template = variants.get(lang) or variants.get(DEFAULT_LANG) or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template


def normalize_lang(lang: str | None) -> str:
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def resolve_ui_lang(language_code: str | None) -> str:
    """Choose RU or EN from a Telegram client ``language_code``, region-aware.

    Rules (default only — a saved preference wins over this):
    - no code at all → RU (no signal; historical default, and /start lets them pick);
    - explicit ``ru``/``en`` (incl. regional variants like ``en-US``) → that language;
    - any other CIS locale (``uk``, ``kk``, ``hy``, …) → RU;
    - everything else (``fr``, ``de``, ``es``, ``pt-BR``, …) → EN.
    """
    if not language_code:
        return DEFAULT_LANG
    base = language_code.split("-", 1)[0].strip().lower()
    if base in SUPPORTED_LANGS:
        return base
    return DEFAULT_LANG if base in CIS_LANG_CODES else "en"


def assert_catalog_complete() -> None:
    """Test hook: every key must define every supported language."""
    missing: list[str] = []
    for key, variants in _MESSAGES.items():
        for lang in SUPPORTED_LANGS:
            if lang not in variants:
                missing.append(f"{key}:{lang}")
    if missing:
        raise AssertionError(f"i18n catalog incomplete: {', '.join(missing)}")
