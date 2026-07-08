"""Hierarchical role catalog for registration.

Two-tier structure: a small set of parent ``Category`` items, each holding a
flat list of concrete ``Role`` items. The registration FSM walks this as
Category -> Role(s): a user first picks "Programming / Engineering", then the
specific role(s) such as "Java (Backend)".

Role ids are globally unique so a single ``ROLE_BY_ID`` lookup is enough for
validation and display anywhere in the app.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Role:
    id: str
    title: str


@dataclass(frozen=True)
class Category:
    id: str
    title: str
    description: str
    roles: tuple[Role, ...]


def _r(items: tuple[tuple[str, str], ...]) -> tuple[Role, ...]:
    return tuple(Role(id=i, title=t) for i, t in items)


CATEGORIES: tuple[Category, ...] = (
    Category(
        id="programming",
        title="Программирование",
        description="Геймплей, движок, бэкенд, инструменты, интеграция.",
        roles=_r(
            (
                ("gameplay_programmer", "Gameplay Programmer"),
                ("blueprint_developer", "Blueprint Developer"),
                ("technical_designer_prog", "Technical Designer"),
                ("ui_programmer", "UI Programmer"),
                ("tools_programmer", "Tools Programmer"),
                ("ai_programmer", "AI Programmer"),
                ("network_programmer", "Network Programmer"),
                ("general_programmer", "General Programmer"),
            )
        ),
    ),
    Category(
        id="game_design",
        title="Гейм-дизайн",
        description="Механики, уровни, баланс, нарратив, player flow.",
        roles=_r(
            (
                ("game_designer", "Game Designer"),
                ("level_designer", "Level Designer"),
                ("systems_designer", "Systems Designer"),
                ("combat_designer", "Combat Designer"),
                ("quest_designer", "Quest Designer"),
                ("narrative_designer", "Narrative Designer"),
                ("balance_economy_designer", "Balance / Economy Designer"),
                ("technical_designer_gd", "Technical Designer"),
                ("ux_designer", "UX Designer"),
            )
        ),
    ),
    Category(
        id="art_2d",
        title="2D-арт",
        description="Концепты, иллюстрации, UI, пиксель-арт, 2D-анимация.",
        roles=_r(
            (
                ("concept", "Concept Artist"),
                ("character_2d", "Character Artist"),
                ("environment_concept_2d", "Environment Concept Artist"),
                ("prop_concept_2d", "Prop Concept Artist"),
                ("ui_artist", "UI Artist"),
                ("icon_artist", "Icon Artist"),
                ("illustrator", "Illustrator"),
                ("texture_2d", "Texture Artist"),
                ("animator_2d", "2D Animator"),
                ("storyboard_artist", "Storyboard Artist"),
            )
        ),
    ),
    Category(
        id="art_3d",
        title="3D-арт",
        description="Моделинг, персонажи, окружение, скульпт, риг, VFX, свет.",
        roles=_r(
            (
                ("modeler_3d", "3D Modeler"),
                ("character_3d", "Character Artist"),
                ("environment_3d", "Environment Artist"),
                ("prop_3d", "Prop Artist"),
                ("sculptor", "Sculptor"),
                ("texturing_3d", "Texturing / Materials"),
                ("rigging", "Rigging"),
                ("animator_3d", "3D Animator"),
                ("vfx", "VFX Artist"),
                ("lighting", "Lighting Artist"),
            )
        ),
    ),
    Category(
        id="audio",
        title="Аудио",
        description="Музыка, звуковой дизайн, аудио-интеграция, озвучка.",
        roles=_r(
            (
                ("composer", "Composer"),
                ("sound_designer", "Sound Designer"),
                ("audio_impl", "Audio Implementation"),
                ("voice", "Voice / Dialogue"),
                ("adaptive_audio", "Adaptive / Interactive Music"),
                ("audio_generalist", "Audio Generalist"),
            )
        ),
    ),
    Category(
        id="management",
        title="Менеджмент / Продюсирование",
        description="Координация команды, планирование, продюсирование (PM, продюсер, тимлид).",
        roles=_r(
            (
                ("project_manager", "Project Manager"),
                ("producer", "Producer"),
                ("team_lead", "Team Lead"),
                ("coordinator", "Coordinator"),
                ("scrum_master", "Scrum Master"),
                ("community_manager", "Community Manager"),
                ("qa_lead", "QA Lead"),
            )
        ),
    ),
)

CATEGORY_BY_ID: dict[str, Category] = {c.id: c for c in CATEGORIES}

# Leading digit of a player's public id, keyed by category - a "region code" à la
# Genshin, so a glance at the id tells you the discipline (1xxxx = programmer,
# 3xxxx = 2D artist, …). Reorder freely; each digit just needs to stay unique.
CATEGORY_ID_PREFIX: dict[str, int] = {
    "programming": 1,
    "game_design": 2,
    "art_2d": 3,
    "art_3d": 4,
    "audio": 5,
    "management": 6,
}

# Width of the per-category counter; player_code = prefix * 10**PLAYER_CODE_WIDTH + n.
# 6 → seven-digit ids with room for 1,000,000 players per discipline
# (programming 1000001..1999999, game_design 2000001.., …). Bump higher for more
# headroom - BigInteger stores it, and each category's block stays disjoint.
PLAYER_CODE_WIDTH = 6


def category_code_base(category_id: str) -> int:
    """First player_code in a category's block (e.g. programming -> 10000)."""
    prefix = CATEGORY_ID_PREFIX.get(category_id, 9)
    return prefix * (10 ** PLAYER_CODE_WIDTH)

ROLE_BY_ID: dict[str, Role] = {
    role.id: role for category in CATEGORIES for role in category.roles
}

# Maps a role id back to the id of the category that owns it.
CATEGORY_OF_ROLE: dict[str, str] = {
    role.id: category.id for category in CATEGORIES for role in category.roles
}

# Backward-compatible id -> human title map used by status/summary rendering.
# These stay the canonical (Russian) titles - what admins see and what's stored
# in skill_category_title. User-facing display is localized via category_title().
MAIN_CATEGORIES: dict[str, str] = {c.id: c.title for c in CATEGORIES}

# English display titles/descriptions, keyed by category id. Only the button and
# status/summary text is localized; the stored skill_category_title stays RU.
CATEGORY_TITLE_EN: dict[str, str] = {
    "programming": "Programming",
    "game_design": "Game Design",
    "art_2d": "2D Art",
    "art_3d": "3D Art",
    "audio": "Audio",
    "management": "Management / Production",
}
CATEGORY_DESC_EN: dict[str, str] = {
    "programming": "Gameplay, engine, backend, tools, integration.",
    "game_design": "Mechanics, levels, balance, narrative, player flow.",
    "art_2d": "Concepts, illustration, UI, pixel art, 2D animation.",
    "art_3d": "Modeling, characters, environments, sculpting, rigging, VFX, lighting.",
    "audio": "Music, sound design, audio integration, voice.",
    "management": "Team coordination, planning, production (PM, producer, team lead).",
}


def category_title(category_id: str | None, lang: str = "ru") -> str:
    """Localized category title (falls back to the canonical RU title / id)."""
    if lang == "en":
        return CATEGORY_TITLE_EN.get(category_id or "", MAIN_CATEGORIES.get(category_id or "", category_id or "-"))
    return MAIN_CATEGORIES.get(category_id or "", category_id or "-")


def category_description(category_id: str | None, lang: str = "ru") -> str:
    """Localized category description (falls back to the catalog RU description)."""
    category = CATEGORY_BY_ID.get(category_id or "")
    ru = category.description if category else ""
    if lang == "en":
        return CATEGORY_DESC_EN.get(category_id or "", ru)
    return ru


def role_titles(role_ids: list[str]) -> list[str]:
    """Resolve a list of role ids to their human titles (skips unknown ids)."""
    return [ROLE_BY_ID[r].title for r in role_ids if r in ROLE_BY_ID]


# Reverse title -> id map, used to pre-select current roles when a player edits
# their profile. Titles are unique WITHIN a category but not always across them
# (e.g. "Technical Designer" lives under both programming and game_design), so we
# key by category; callers that know the owning category pass it to disambiguate.
ROLE_ID_BY_TITLE_BY_CATEGORY: dict[str, dict[str, str]] = {
    category.id: {role.title: role.id for role in category.roles}
    for category in CATEGORIES
}

# Flat fallback for when the category isn't known. An ambiguous title resolves to
# its last-defined owner, so prefer passing a category to role_ids_from_titles.
ROLE_ID_BY_TITLE: dict[str, str] = {
    role.title: role.id for category in CATEGORIES for role in category.roles
}


def role_ids_from_titles(titles: list[str], category_id: str | None = None) -> list[str]:
    """Resolve stored role titles back to their ids (skips unknown titles). Pass
    ``category_id`` to resolve within that category, so a title shared across
    categories maps to the role that category actually owns."""
    mapping = ROLE_ID_BY_TITLE_BY_CATEGORY.get(category_id) or ROLE_ID_BY_TITLE
    return [mapping[title] for title in titles if title in mapping]


EXPERIENCE_LEVELS: dict[str, str] = {
    "beginner": "Beginner · 0-6 мес.",
    "intermediate": "Junior · 6-18 мес.",
    "game_jam": "Middle · 18-36 мес.",
    "commercial": "Senior · 36+ мес.",
}

# English display labels for the experience levels (stored value is the key).
EXPERIENCE_LEVELS_EN: dict[str, str] = {
    "beginner": "Beginner · 0-6 mo.",
    "intermediate": "Junior · 6-18 mo.",
    "game_jam": "Middle · 18-36 mo.",
    "commercial": "Senior · 36+ mo.",
}


def experience_label(key: str, lang: str = "ru") -> str:
    """Localized experience-level label (falls back to the key)."""
    table = EXPERIENCE_LEVELS_EN if lang == "en" else EXPERIENCE_LEVELS
    return table.get(key, key)

# The experience level that unlocks the beginner branch: an extra "strengths"
# step (F, see STRENGTHS) shown only to applicants who mark themselves beginners
# at step C. Every other level goes straight from tools to motivation.
BEGINNER_EXPERIENCE = "beginner"

# Sentinel option offered on the engine/tools multi-selects: the player hasn't
# worked with any yet. It's a real stored value (so the schema whitelist accepts
# a "none yet" answer and admins see it on the card) but is EXCLUSIVE with real
# picks - see toggle_engine/toggle_tool.
NO_EXPERIENCE_OPTION = "Пока не работал(а)"

# The free-text catch-all keeps the stable internal value "Other" (referenced by
# the engine_other/tools_other gates and join_with_other), but is shown to users
# under a friendlier label via OPTION_LABELS.
OTHER_OPTION = "Other"
OPTION_LABELS: dict[str, str] = {OTHER_OPTION: "Свой вариант"}

# English display labels for values whose stored form is Russian (or the internal
# "Other" token). Brand names like Unity/Blender/Figma are already English and
# aren't listed - option_label falls back to the value itself. Stored values never
# change; only the button/summary text is localized.
OPTION_LABELS_EN: dict[str, str] = {
    OTHER_OPTION: "Custom / other",
    NO_EXPERIENCE_OPTION: "Haven't worked with any yet",
    "Roblox / UEFN / другой редактор": "Roblox / UEFN / other editor",
    "Tabletop / бумажные прототипы": "Tabletop / paper prototypes",
    "Только документация": "Documentation only",
    "Придумывать механику": "Inventing mechanics",
    "Описывать правила": "Writing rules",
    "Делать уровни": "Building levels",
    "Балансировать": "Balancing",
    "Писать квесты": "Writing quests",
    "Прототипировать": "Prototyping",
}


def option_label(value: str, lang: str = "ru") -> str:
    """Human-facing button/summary text for a multi-select value (the value
    itself if no friendlier label is defined for the language)."""
    if lang == "en":
        return OPTION_LABELS_EN.get(value, value)
    return OPTION_LABELS.get(value, value)


# Step D (engine) and Step E (tools) offer different option lists per category:
# a programmer sees languages, a game designer sees production tools, etc. A
# category without its own list falls back to DEFAULT_ENGINES / DEFAULT_TOOLS.
# Every list ends with the two sentinels (NO_EXPERIENCE_OPTION, OTHER_OPTION),
# which carry special selection semantics in the handlers.
DEFAULT_ENGINES: tuple[str, ...] = (
    "Unreal Engine",
    "Unity",
    "Godot",
    "GameMaker",
    "CryEngine",
    NO_EXPERIENCE_OPTION,
    OTHER_OPTION,
)

DEFAULT_TOOLS: tuple[str, ...] = (
    "Blender",
    "Maya",
    "3ds Max",
    "ZBrush",
    "Substance Painter / Designer",
    "Photoshop",
    "Houdini",
    "Krita",
    "Aseprite",
    NO_EXPERIENCE_OPTION,
    OTHER_OPTION,
)

ENGINES_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "programming": (
        "Unreal Engine",
        "Unity",
        "Godot",
        "Roblox / UEFN",
        "Custom engine",
        NO_EXPERIENCE_OPTION,
        OTHER_OPTION,
    ),
    "game_design": (
        "Unreal Engine",
        "Unity",
        "Godot",
        "Roblox / UEFN / другой редактор",
        "Tabletop / бумажные прототипы",
        "Только документация",
        NO_EXPERIENCE_OPTION,
        OTHER_OPTION,
    ),
    "art_2d": (
        "Unreal Engine",
        "Unity",
        "Godot",
        "Roblox / UEFN",
        "Custom engine",
        NO_EXPERIENCE_OPTION,
        OTHER_OPTION,
    ),
}

TOOLS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "programming": (
        "C++",
        "C#",
        "Blueprints",
        "Python",
        "JavaScript / TypeScript",
        "Lua",
        "GDScript",
        "Visual Scripting",
        "Git / GitHub",
        "Perforce",
        "Rider",
        "Visual Studio",
        "VS Code",
        NO_EXPERIENCE_OPTION,
        OTHER_OPTION,
    ),
    "game_design": (
        "Miro",
        "Figma / FigJam",
        "Google Docs",
        "Notion",
        "Trello",
        "Jira",
        "Confluence",
        "Excel / Google Sheets",
        "Machinations",
        "Draw.io / diagrams",
        "Twine",
        NO_EXPERIENCE_OPTION,
        OTHER_OPTION,
    ),
}


def engines_for(category_id: str | None) -> tuple[str, ...]:
    """Step D options for a category (falls back to DEFAULT_ENGINES)."""
    return ENGINES_BY_CATEGORY.get(category_id or "", DEFAULT_ENGINES)


def tools_for(category_id: str | None) -> tuple[str, ...]:
    """Step E options for a category (falls back to DEFAULT_TOOLS)."""
    return TOOLS_BY_CATEGORY.get(category_id or "", DEFAULT_TOOLS)


# Display label for the "haven't worked with any" sentinel. Its STORED value is
# always NO_EXPERIENCE_OPTION; only the button text differs per step/language so
# it reads naturally. Categories on the default list use the generic label.
def engine_none_label(category_id: str | None, lang: str = "ru") -> str:
    if category_id in ENGINES_BY_CATEGORY:
        return "Haven't used any engines yet" if lang == "en" else "Пока не работал(а) с движками"
    return option_label(NO_EXPERIENCE_OPTION, lang)


def tools_none_label(category_id: str | None, lang: str = "ru") -> str:
    if category_id in TOOLS_BY_CATEGORY:
        return "Haven't used any tools yet" if lang == "en" else "Пока не работал"
    return option_label(NO_EXPERIENCE_OPTION, lang)


# Anti-forgery whitelist for the final payload: the union of every engine / tool
# value across all categories. The per-category buttons only ever surface a
# subset, but any real catalog value is accepted regardless of the category the
# applicant picked (keeps validation simple and category-independent).
ALL_ENGINES: frozenset[str] = frozenset(
    value for group in (DEFAULT_ENGINES, *ENGINES_BY_CATEGORY.values()) for value in group
)
ALL_TOOLS: frozenset[str] = frozenset(
    value for group in (DEFAULT_TOOLS, *TOOLS_BY_CATEGORY.values()) for value in group
)

MOTIVATIONS: tuple[str, ...] = (
    "Learning",
    "Portfolio",
    "Team experience",
    "Finding work",
    "Interest in the project",
    "Testing the idea",
)

# Step F (Сильные стороны) - beginner branch only. Multi-select: what the
# applicant is best at. Persisted on the application like motivations; stays
# empty for every other experience level (they never reach this step).
STRENGTHS: tuple[str, ...] = (
    "Придумывать механику",
    "Описывать правила",
    "Делать уровни",
    "Балансировать",
    "Писать квесты",
    "Прототипировать",
)

# Version of the rules & privacy policy the consent step shows (docs/PRIVACY.md).
# Bump it whenever the policy text changes: the accepted version is recorded in
# the application's audit log, so we can always tell which terms a player agreed to.
PRIVACY_VERSION = 1
