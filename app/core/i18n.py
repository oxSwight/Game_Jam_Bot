"""Minimal, dependency-free i18n.

A flat ``{key: {lang: text}}`` catalog plus a ``t(key, lang, **kwargs)`` lookup.
Keeps translation data in one place and lets handlers stay declarative:

    await message.answer(t("welcome", lang))

Design choices:
- No gettext/.po tooling - the string set is small and Python-native is easier
  to grep, test, and keep in sync with the code that uses it.
- Unknown keys raise in tests (via ``assert_catalog_complete``) but degrade to
  the key name at runtime so a missing translation never crashes a handler.
- ``DEFAULT_LANG`` is the fallback whenever a language lacks a given key.
"""

from __future__ import annotations

SUPPORTED_LANGS: tuple[str, ...] = ("ru", "en")
DEFAULT_LANG = "ru"

LANG_TITLES: dict[str, str] = {"ru": "🇷🇺 Русский", "en": "🇬🇧 English"}

# Telegram never gives a bot the user's country - only the client's UI language
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
            "Перейдите по ней и отправьте запрос на вступление - бот подтвердит "
            "вас автоматически. Ссылка персональная: чужие запросы по ней "
            "отклоняются. Если ссылка не сработала - /invite выдаст новую."
        ),
        "en": (
            "Your application was approved.\n\n"
            "Here is your personal link to join the game:\n{link}\n\n"
            "Open it and send a join request - the bot will confirm you "
            "automatically. The link is personal: anyone else's request through "
            "it is declined. If the link fails, /invite issues a new one."
        ),
    },
    "notify_approved_no_link": {
        "ru": (
            "Ваша заявка одобрена. Пригласительную ссылку не удалось создать "
            "автоматически - попробуйте /invite чуть позже или дождитесь "
            "администратора."
        ),
        "en": (
            "Your application was approved. The invite link could not be created "
            "automatically - try /invite a bit later or wait for an admin."
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
        "ru": "Вы уже состоите в группе - ссылка не нужна.",
        "en": "You are already a member of the group - no link needed.",
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
            "• это MVP-тест - возможны сбои;\n"
            "• заявка проверяется вручную; после отклонения можно подать новую;\n"
            "• ссылки и спам в анкете запрещены - такая заявка сбрасывается;\n"
            "• пригласительная ссылка персональная, передавать её бессмысленно;\n"
            "• будьте готовы подтвердить навыки примерами работ;\n"
            "• в группе - уважительное общение.\n\n"
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
            "• this is an MVP test - glitches may happen;\n"
            "• applications are reviewed manually; you may re-apply after a "
            "rejection;\n"
            "• links and spam in the form are forbidden - such an application "
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
    # ---------------- registration funnel (steps A-G) ---------------- #
    "reg_step_a": {
        "ru": (
            "<b>Шаг A - Базовая информация</b>\n\n"
            "Введите ваш <b>никнейм</b> (отображаемое имя в группе):\n\n"
            "<i>Можно отменить в любой момент - кнопка ниже.</i>"
        ),
        "en": (
            "<b>Step A - Basic info</b>\n\n"
            "Enter your <b>nickname</b> (the name shown in the group):\n\n"
            "<i>You can cancel any time - button below.</i>"
        ),
    },
    "reg_email_prompt": {
        "ru": "Введите ваш <b>email</b> для связи:",
        "en": "Enter your <b>email</b> for contact:",
    },
    "reg_step_b": {
        "ru": "<b>Шаг B - Категория</b>\n\nВыберите основное направление:",
        "en": "<b>Step B - Category</b>\n\nPick your main discipline:",
    },
    "reg_roles_instruction": {
        "ru": "Выберите роль(и) (можно несколько), затем нажмите «Готово»:",
        "en": "Select your role(s) (you can pick several), then tap \"Done\":",
    },
    "reg_step_c": {
        "ru": "<b>Шаг C - Уровень опыта</b>\n\nВыберите ваш уровень:",
        "en": "<b>Step C - Experience level</b>\n\nChoose your level:",
    },
    "reg_step_g": {
        "ru": "<b>Шаг G - Мотивация</b>\n\nЧто вас привлекает? (можно несколько):",
        "en": "<b>Step G - Motivation</b>\n\nWhat draws you in? (you can pick several):",
    },
    "reg_strengths_prompt": {
        "ru": (
            "<b>Шаг F - Сильные стороны</b>\n\n"
            "Что вы умеете делать лучше всего? (можно несколько):"
        ),
        "en": (
            "<b>Step F - Strengths</b>\n\n"
            "What are you best at? (you can pick several):"
        ),
    },
    "reg_engine_prompt_default": {
        "ru": (
            "<b>Шаг D - Движок</b>\n\n"
            "Выберите движок(и), с которыми работали (можно несколько). "
            "Если ещё не пробовали - отметьте «Пока не работал(а)»:"
        ),
        "en": (
            "<b>Step D - Engine</b>\n\n"
            "Pick the engine(s) you've worked with (you can select several). "
            "If you haven't tried any yet, mark \"Haven't worked with any yet\":"
        ),
    },
    "reg_engine_prompt_game_design": {
        "ru": (
            "<b>Шаг D - Движок или рабочий контекст</b>\n\n"
            "Выберите, где вы уже пробовали реализовывать или описывать игровые идеи "
            "(можно несколько). Если ещё не пробовали - отметьте «Пока не работал(а)»:"
        ),
        "en": (
            "<b>Step D - Engine or working context</b>\n\n"
            "Pick where you've already tried to build or describe game ideas "
            "(several allowed). If you haven't yet, mark \"Haven't worked with any yet\":"
        ),
    },
    "reg_engine_prompt_art_2d": {
        "ru": (
            "<b>Шаг D - Движок или формат интеграции</b>\n\n"
            "Выберите, работали ли вы с игровыми движками или готовили 2D-графику "
            "для игры (можно несколько). Если ещё не пробовали - отметьте «Пока не работал(а)»:"
        ),
        "en": (
            "<b>Step D - Engine or integration format</b>\n\n"
            "Pick whether you've worked with game engines or prepared 2D art for a "
            "game (several allowed). If you haven't yet, mark \"Haven't worked with any yet\":"
        ),
    },
    "reg_tools_prompt_default": {
        "ru": (
            "<b>Шаг E - Инструменты</b>\n\n"
            "Выберите инструменты, с которыми работали (можно несколько). "
            "Если ещё не пробовали - отметьте «Пока не работал(а)»:"
        ),
        "en": (
            "<b>Step E - Tools</b>\n\n"
            "Pick the tools you've worked with (several allowed). "
            "If you haven't tried any yet, mark \"Haven't worked with any yet\":"
        ),
    },
    "reg_tools_prompt_programming": {
        "ru": (
            "<b>Шаг E - Языки и инструменты</b>\n\n"
            "Выберите языки, технологии и инструменты, с которыми вы работали "
            "(можно несколько). Если ещё не пробовали - отметьте «Пока не работал»:"
        ),
        "en": (
            "<b>Step E - Languages and tools</b>\n\n"
            "Pick the languages, tech and tools you've worked with "
            "(several allowed). If you haven't yet, mark \"Haven't worked with any yet\":"
        ),
    },
    "reg_tools_prompt_game_design": {
        "ru": (
            "<b>Шаг E - Инструменты и формат работы</b>\n\n"
            "Выберите инструменты, с которыми вы работали (можно несколько). "
            "Если ещё не пробовали - отметьте «Пока не работал»:"
        ),
        "en": (
            "<b>Step E - Tools and working format</b>\n\n"
            "Pick the tools you've worked with (several allowed). "
            "If you haven't yet, mark \"Haven't worked with any yet\":"
        ),
    },
    "reg_engine_other_prompt": {
        "ru": "Укажите другой движок (текстом):",
        "en": "Type in the other engine:",
    },
    "reg_tools_other_prompt": {
        "ru": "Укажите другие инструменты (текстом):",
        "en": "Type in the other tools:",
    },
    "reg_engine_other_short": {
        "ru": "Укажите движок:",
        "en": "Name the engine:",
    },
    "reg_tools_other_short": {
        "ru": "Укажите хотя бы один инструмент:",
        "en": "Name at least one tool:",
    },
    "reg_too_long": {
        "ru": "Слишком длинно (максимум {max} символов). Короче:",
        "en": "Too long (max {max} characters). Shorter, please:",
    },
    "reg_pick_role": {
        "ru": "Выберите хотя бы одну роль",
        "en": "Select at least one role",
    },
    "reg_pick_engine": {
        "ru": "Выберите хотя бы один движок",
        "en": "Select at least one engine",
    },
    "reg_pick_tool": {
        "ru": "Выберите хотя бы один инструмент",
        "en": "Select at least one tool",
    },
    "reg_pick_one": {
        "ru": "Выберите хотя бы один пункт",
        "en": "Select at least one option",
    },
    "reg_session_expired": {
        "ru": "Сессия устарела. Начните заново: /register",
        "en": "Session expired. Start again: /register",
    },
    "reg_unknown_category": {
        "ru": "Неизвестная категория.",
        "en": "Unknown category.",
    },
    "reg_confirm_header": {
        "ru": "<b>Проверьте данные перед отправкой:</b>",
        "en": "<b>Check your details before submitting:</b>",
    },
    "reg_summary": {
        "ru": (
            "<b>Ник:</b> {nickname}\n"
            "<b>Email:</b> {email}\n"
            "<b>Категория:</b> {category}\n"
            "<b>Роли:</b> {roles}\n"
            "<b>Опыт:</b> {experience}\n"
            "<b>Движок:</b> {engine}\n"
            "<b>Инструменты:</b> {tools}\n"
            "{strengths_block}"
            "<b>Мотивация:</b> {motivations}"
        ),
        "en": (
            "<b>Nickname:</b> {nickname}\n"
            "<b>Email:</b> {email}\n"
            "<b>Category:</b> {category}\n"
            "<b>Roles:</b> {roles}\n"
            "<b>Experience:</b> {experience}\n"
            "<b>Engine:</b> {engine}\n"
            "<b>Tools:</b> {tools}\n"
            "{strengths_block}"
            "<b>Motivation:</b> {motivations}"
        ),
    },
    "reg_sum_strengths_line": {
        "ru": "<b>Сильные стороны:</b> {strengths}\n",
        "en": "<b>Strengths:</b> {strengths}\n",
    },
    "reg_submitted": {
        "ru": (
            "<b>Заявка отправлена.</b>\n\n"
            "Ваш ID: <code>{id}</code>\n\n"
            "Статус: на ручной проверке.\n"
            "После одобрения вы получите персональную ссылку на вступление в группу.\n\n"
            "Проверить статус: /status"
        ),
        "en": (
            "<b>Application submitted.</b>\n\n"
            "Your ID: <code>{id}</code>\n\n"
            "Status: pending manual review.\n"
            "Once approved you'll get a personal invite link to join the group.\n\n"
            "Check your status: /status"
        ),
    },
    "reg_done": {
        "ru": "Регистрация завершена.",
        "en": "Registration complete.",
    },
    "reg_active_exists_alert": {
        "ru": "У вас уже есть активная заявка.",
        "en": "You already have an active application.",
    },
    "reg_dup_contact_alert": {
        "ru": "Такой ник или email уже заняты. Введите их заново.",
        "en": "That nickname or email is taken. Please enter them again.",
    },
    "reg_enter_other_nick": {
        "ru": "Введите другой <b>никнейм</b>:",
        "en": "Enter a different <b>nickname</b>:",
    },
    "reg_status": {
        "ru": (
            "<b>Ваш профиль</b>\n\n"
            "ID игрока: <code>{code}</code>\n"
            "Ник: {nickname}\n"
            "Email: {email}\n"
            "Категория: {category}\n"
            "Роли: {roles}\n"
            "Опыт: {experience}\n"
            "Движок: {engine}\n"
            "Инструменты: {tools}\n"
            "{strengths_block}"
            "Мотивация: {motivations}\n"
            "Статус заявки: {status}\n"
            "Членство: {membership}"
        ),
        "en": (
            "<b>Your profile</b>\n\n"
            "Player ID: <code>{code}</code>\n"
            "Nickname: {nickname}\n"
            "Email: {email}\n"
            "Category: {category}\n"
            "Roles: {roles}\n"
            "Experience: {experience}\n"
            "Engine: {engine}\n"
            "Tools: {tools}\n"
            "{strengths_block}"
            "Motivation: {motivations}\n"
            "Application status: {status}\n"
            "Membership: {membership}"
        ),
    },
    "reg_status_strengths_line": {
        "ru": "Сильные стороны: {strengths}\n",
        "en": "Strengths: {strengths}\n",
    },
    "reg_status_member": {"ru": "в группе", "en": "in the group"},
    "reg_status_not_member": {"ru": "не в группе", "en": "not in the group"},
    "reg_help_user": {
        "ru": (
            "<b>Команды</b>\n\n"
            "/register - подать заявку\n"
            "/status - статус вашей заявки\n"
            "/edit - изменить ник, email, навыки и категорию\n"
            "/invite - получить ссылку в группу (после одобрения)\n"
            "/withdraw - безвозвратно удалить все свои данные\n"
            "/language - сменить язык"
        ),
        "en": (
            "<b>Commands</b>\n\n"
            "/register - submit an application\n"
            "/status - your application status\n"
            "/edit - change nickname, email, skills and category\n"
            "/invite - get the group link (after approval)\n"
            "/withdraw - permanently erase all your data\n"
            "/language - change language"
        ),
    },
    # ---------------- edit flow (/edit) ---------------- #
    "edit_no_active": {
        "ru": "У вас нет активной заявки. /register",
        "en": "You have no active application. /register",
    },
    "edit_prompt": {
        "ru": (
            "Что изменить?\n"
            "Текущий ник: <b>{nickname}</b>\n"
            "Текущий email: <b>{email}</b>"
        ),
        "en": (
            "What would you like to change?\n"
            "Current nickname: <b>{nickname}</b>\n"
            "Current email: <b>{email}</b>"
        ),
    },
    "edit_cancelled": {
        "ru": "Изменение отменено.",
        "en": "Editing cancelled.",
    },
    "edit_enter_nickname": {
        "ru": "Введите новый <b>никнейм</b>:",
        "en": "Enter a new <b>nickname</b>:",
    },
    "edit_enter_email": {
        "ru": "Введите новый <b>email</b>:",
        "en": "Enter a new <b>email</b>:",
    },
    "edit_not_found_alert": {
        "ru": "Активная заявка не найдена.",
        "en": "No active application found.",
    },
    "edit_dup_contact": {
        "ru": "Такой ник или email уже заняты. Попробуйте другой.",
        "en": "That nickname or email is taken. Try another.",
    },
    "edit_saved": {
        "ru": "Данные обновлены. /status - посмотреть профиль.",
        "en": "Details updated. /status - view your profile.",
    },
    "edit_no_active_walk": {
        "ru": "Активная заявка не найдена.",
        "en": "No active application found.",
    },
    "edit_profile_intro": {
        "ru": (
            "<b>Изменение профиля</b>\n\n"
            "Пройдите анкету заново - текущие ответы уже отмечены. Меняйте что нужно "
            "и жмите «Готово» на каждом шаге.\n\n"
            "<b>Шаг B - Категория</b>\nВыберите основное направление:"
        ),
        "en": (
            "<b>Edit profile</b>\n\n"
            "Walk through the form again - your current answers are pre-selected. "
            "Change what you need and tap \"Done\" on each step.\n\n"
            "<b>Step B - Category</b>\nPick your main discipline:"
        ),
    },
    "edit_profile_updated": {
        "ru": "<b>Профиль обновлён.</b>",
        "en": "<b>Profile updated.</b>",
    },
    "edit_profile_updated_hint": {
        "ru": "Готово. /status - посмотреть профиль.",
        "en": "Done. /status - view your profile.",
    },
    "edit_profile_not_found": {
        "ru": "Активная заявка не найдена. /register",
        "en": "No active application found. /register",
    },
    # ---------------- shared button labels ---------------- #
    "btn_done": {"ru": "Готово", "en": "Done"},
    "btn_back": {"ru": "Назад", "en": "Back"},
    "btn_next": {"ru": "Далее", "en": "Next"},
    "btn_to_categories": {"ru": "К категориям", "en": "To categories"},
    "btn_send_application": {"ru": "Отправить заявку", "en": "Submit application"},
    "btn_restart": {"ru": "Начать заново", "en": "Start over"},
    "btn_cancel_registration": {"ru": "Отменить регистрацию", "en": "Cancel registration"},
    "btn_edit_nickname": {"ru": "Никнейм", "en": "Nickname"},
    "btn_edit_email": {"ru": "Email", "en": "Email"},
    "btn_edit_skills": {"ru": "Навыки и категория", "en": "Skills & category"},
    "btn_cancel": {"ru": "Отмена", "en": "Cancel"},
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

    Rules (default only - a saved preference wins over this):
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
