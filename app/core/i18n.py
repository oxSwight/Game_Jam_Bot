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

# key -> {lang -> template}. Templates use str.format-style {placeholders}.
_MESSAGES: dict[str, dict[str, str]] = {
    "welcome": {
        "ru": (
            "👋 Добро пожаловать в бот регистрации игроков!\n\n"
            "Здесь вы можете подать заявку на участие в платформе.\n\n"
            "Для регистрации: /register"
        ),
        "en": (
            "👋 Welcome to the player registration bot!\n\n"
            "Here you can apply to join the platform.\n\n"
            "To register: /register"
        ),
    },
    "already_registered": {
        "ru": (
            "Привет, <b>{nickname}</b>!\n\n"
            "Ваша заявка уже зарегистрирована.\n"
            "Статус: {status}\n"
            "ID: <code>{id}</code>\n\n"
            "Чтобы подать новую заявку, используйте /register"
        ),
        "en": (
            "Hi, <b>{nickname}</b>!\n\n"
            "Your application is already registered.\n"
            "Status: {status}\n"
            "ID: <code>{id}</code>\n\n"
            "To submit a new application, use /register"
        ),
    },
    "active_application_exists": {
        "ru": "У вас уже есть активная заявка. Дождитесь проверки или обратитесь к администратору.",
        "en": "You already have an active application. Wait for review or contact an admin.",
    },
    "status_not_found": {
        "ru": "Заявка не найдена. Используйте /register",
        "en": "No application found. Use /register",
    },
    "registration_cancelled": {
        "ru": "Регистрация отменена.\nИспользуйте /register, чтобы начать снова.",
        "en": "Registration cancelled.\nUse /register to start again.",
    },
    "withdraw_done": {
        "ru": "🗑 Ваша заявка удалена.\nТеперь можно подать новую: /register",
        "en": "🗑 Your application was deleted.\nYou can now submit a new one: /register",
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
        "ru": "✅ Язык переключён на русский.",
        "en": "✅ Language switched to English.",
    },
    "status_pending_review": {"ru": "⏳ на ручной проверке", "en": "⏳ under manual review"},
    "status_approved": {"ru": "✅ одобрена", "en": "✅ approved"},
    "status_rejected": {"ru": "❌ отклонена", "en": "❌ rejected"},
    "notify_approved": {
        "ru": "🎉 Ваша заявка одобрена!\n\nДобро пожаловать на платформу, <b>{nickname}</b>!",
        "en": "🎉 Your application was approved!\n\nWelcome to the platform, <b>{nickname}</b>!",
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


def assert_catalog_complete() -> None:
    """Test hook: every key must define every supported language."""
    missing: list[str] = []
    for key, variants in _MESSAGES.items():
        for lang in SUPPORTED_LANGS:
            if lang not in variants:
                missing.append(f"{key}:{lang}")
    if missing:
        raise AssertionError(f"i18n catalog incomplete: {', '.join(missing)}")
