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
                ("programmer", "Programmer"),
                ("frontend", "Frontend"),
                ("gameplay", "Gameplay"),
                ("backend_other", "Backend"),
                ("tools_engine", "Tools / Engine"),
                ("graphics", "Graphics / Shaders"),
                ("network", "Networking / Multiplayer"),
                ("qa_automation", "QA / Automation"),
                ("devops", "DevOps / Build"),
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
                ("economy_designer", "Economy / Balance"),
                ("narrative", "Narrative / Writer"),
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
                ("illustrator", "Illustrator"),
                ("character_2d", "2D Character Artist"),
                ("environment_2d", "2D Environment Artist"),
                ("ui_artist", "UI Artist"),
                ("pixel", "Pixel Artist"),
                ("animator_2d", "2D Animator"),
                ("texture_2d", "Texture Artist"),
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
MAIN_CATEGORIES: dict[str, str] = {c.id: c.title for c in CATEGORIES}


def role_titles(role_ids: list[str]) -> list[str]:
    """Resolve a list of role ids to their human titles (skips unknown ids)."""
    return [ROLE_BY_ID[r].title for r in role_ids if r in ROLE_BY_ID]


# Reverse of ROLE_BY_ID's title view: titles are globally unique, so we can map a
# stored role title back to its id - used to pre-select current roles when a
# player edits their profile.
ROLE_ID_BY_TITLE: dict[str, str] = {
    role.title: role.id for category in CATEGORIES for role in category.roles
}


def role_ids_from_titles(titles: list[str]) -> list[str]:
    """Resolve stored role titles back to their ids (skips unknown titles)."""
    return [ROLE_ID_BY_TITLE[title] for title in titles if title in ROLE_ID_BY_TITLE]


EXPERIENCE_LEVELS: dict[str, str] = {
    "beginner": "Beginner · 0-6 мес.",
    "intermediate": "Junior · 6-18 мес.",
    "game_jam": "Middle · 18-36 мес.",
    "commercial": "Senior · 36+ мес.",
}

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


def option_label(value: str) -> str:
    """Human-facing button text for a multi-select value (value itself if no
    friendlier label is defined)."""
    return OPTION_LABELS.get(value, value)


ENGINES: tuple[str, ...] = (
    "Unreal Engine",
    "Unity",
    "Godot",
    "GameMaker",
    "CryEngine",
    NO_EXPERIENCE_OPTION,
    OTHER_OPTION,
)

TOOLS: tuple[str, ...] = (
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

MOTIVATIONS: tuple[str, ...] = (
    "Learning",
    "Portfolio",
    "Team experience",
    "Finding work",
    "Interest in the project",
    "Testing the idea",
)

# Version of the rules & privacy policy the consent step shows (docs/PRIVACY.md).
# Bump it whenever the policy text changes: the accepted version is recorded in
# the application's audit log, so we can always tell which terms a player agreed to.
PRIVACY_VERSION = 1
