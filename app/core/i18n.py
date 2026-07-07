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
        "ru": (
            "Все ваши данные удалены: заявка (включая отклонённые), никнейм, "
            "email и настройки. Это действие необратимо.\n\n"
            "Подать новую заявку: /register"
        ),
        "en": (
            "All your data has been erased: applications (including rejected "
            "ones), nickname, email and settings. This cannot be undone.\n\n"
            "To apply again: /register"
        ),
    },
    "withdraw_none": {
        "ru": "О вас ничего не сохранено. Подать заявку: /register",
        "en": "We have no data stored about you. To apply: /register",
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
            "Вот ваша персональная ссылка для вступления в игру:\n{link}\n\n"
            "Перейдите по ней и отправьте запрос на вступление — бот подтвердит "
            "вас автоматически. Ссылка персональная: чужие запросы по ней "
            "отклоняются. Если ссылка не сработала — /invite выдаст новую."
        ),
        "en": (
            "Your application was approved.\n\n"
            "Here is your personal link to join the game:\n{link}\n\n"
            "Open it and send a join request — the bot will confirm you "
            "automatically. The link is personal: anyone else's request through "
            "it is declined. If the link fails, /invite issues a new one."
        ),
    },
    "notify_approved_no_link": {
        "ru": (
            "Ваша заявка одобрена. Пригласительную ссылку не удалось создать "
            "автоматически — попробуйте /invite чуть позже или дождитесь "
            "администратора."
        ),
        "en": (
            "Your application was approved. The invite link could not be created "
            "automatically — try /invite a bit later or wait for an admin."
        ),
    },
    "invite_not_approved": {
        "ru": (
            "Персональная ссылка выдаётся после одобрения заявки.\n"
            "Проверить статус: /status"
        ),
        "en": (
            "A personal invite link is issued once your application is approved.\n"
            "Check your status: /status"
        ),
    },
    "invite_already_member": {
        "ru": "Вы уже состоите в группе — ссылка не нужна.",
        "en": "You are already a member of the group — no link needed.",
    },
    "invite_failed": {
        "ru": "Не удалось создать ссылку. Попробуйте позже: /invite",
        "en": "Could not create the link. Please try again later: /invite",
    },
    "consent_text": {
        "ru": (
            "<b>Правила и политика конфиденциальности (v{version})</b>\n\n"
            "<b>Какие данные мы сохраняем:</b> ваш Telegram ID и username, "
            "никнейм, email и ответы анкеты (категория, роли, опыт, движок, "
            "инструменты, мотивация), язык интерфейса и факт членства в группе.\n\n"
            "<b>Зачем:</b> ручная проверка заявки модераторами, выдача "
            "персонального приглашения в закрытую группу и связь по вопросам "
            "участия. Данные видят только администраторы группы; они не "
            "передаются третьим лицам и не используются для рекламы.\n\n"
            "<b>Хранение и удаление:</b> данные хранятся, пока действует ваша "
            "заявка или членство. Команда /withdraw в любой момент безвозвратно "
            "удаляет всё: заявку (включая отклонённые), ник, email и настройки. "
            "Выход из группы сам по себе данные не удаляет.\n\n"
            "<b>Правила участия:</b>\n"
            "• это MVP-тест — возможны сбои;\n"
            "• заявка проверяется вручную; после отклонения можно подать новую;\n"
            "• ссылки и спам в анкете запрещены — такая заявка сбрасывается;\n"
            "• пригласительная ссылка персональная, передавать её бессмысленно;\n"
            "• будьте готовы подтвердить навыки примерами работ;\n"
            "• в группе — уважительное общение.\n\n"
            "Нажимая «Принимаю условия», вы соглашаетесь с обработкой указанных "
            "данных на этих условиях. Полный текст: docs/PRIVACY.md в репозитории "
            "проекта или по запросу у администратора."
        ),
        "en": (
            "<b>Rules and privacy policy (v{version})</b>\n\n"
            "<b>What we store:</b> your Telegram ID and username, nickname, "
            "email and questionnaire answers (category, roles, experience, "
            "engine, tools, motivation), UI language and group-membership "
            "status.\n\n"
            "<b>Why:</b> manual review of your application by moderators, "
            "issuing a personal invite into the closed group, and contacting "
            "you about participation. Only group administrators can see the "
            "data; it is never shared with third parties or used for ads.\n\n"
            "<b>Storage and deletion:</b> data is kept while your application "
            "or membership is active. The /withdraw command irreversibly "
            "erases everything at any time: applications (including rejected "
            "ones), nickname, email and settings. Leaving the group alone does "
            "not erase data.\n\n"
            "<b>Participation rules:</b>\n"
            "• this is an MVP test — glitches may happen;\n"
            "• applications are reviewed manually; you may re-apply after a "
            "rejection;\n"
            "• links and spam in the form are forbidden — such an application "
            "is reset;\n"
            "• the invite link is personal, sharing it is pointless;\n"
            "• be ready to back up your skills with work samples;\n"
            "• be respectful in the group.\n\n"
            "By tapping \"I accept the terms\" you consent to the processing of "
            "the data above under these terms. Full text: docs/PRIVACY.md in "
            "the project repository or from any administrator on request."
        ),
    },
    "consent_declined": {
        "ru": "Регистрация отменена. Без согласия с условиями подать заявку нельзя.",
        "en": "Registration cancelled. An application requires accepting the terms.",
    },
    "profile_update_failed": {
        "ru": "Не удалось обновить профиль, попробуйте ещё раз: /edit",
        "en": "Could not update the profile, please try again: /edit",
    },
    "admin_new_application": {
        "ru": (
            "🆕 Новая заявка: <b>{nickname}</b> · {category}\n"
            "В очереди: {count}\n"
            "Открыть очередь: /review"
        ),
        "en": (
            "🆕 New application: <b>{nickname}</b> · {category}\n"
            "In queue: {count}\n"
            "Open the queue: /review"
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
