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
        title="Programming / Engineering",
        description="Геймплей, движок, бэкенд, инструменты, интеграция.",
        roles=_r(
            (
                ("programmer", "Programmer"),
                ("frontend", "Frontend"),
                ("gameplay", "Gameplay Programmer"),
                ("backend_other", "Backend"),
                ("tools_engine", "Tools / Engine Programmer"),
                ("graphics", "Graphics / Shaders"),
                ("network", "Networking / Multiplayer"),
                ("qa_automation", "QA / Automation"),
                ("devops", "DevOps / Build"),
            )
        ),
    ),
    Category(
        id="game_design",
        title="Game Design",
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
        title="2D Art",
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
        title="3D Art",
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
        title="Audio",
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
        title="Management / PM",
        description="Координация команды, планирование, продюсирование.",
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


EXPERIENCE_LEVELS: dict[str, str] = {
    "beginner": "Beginner",
    "intermediate": "Intermediate",
    "game_jam": "Game jam experience",
    "commercial": "Commercial experience",
}

TOOLS: tuple[str, ...] = (
    "Unreal Engine",
    "Unity",
    "Godot",
    "Blender",
    "ZBrush",
    "Substance Painter / Designer",
    "Photoshop",
    "JetBrains IDE",
    "VS Code / Visual Studio",
    "Other",
)

MOTIVATIONS: tuple[str, ...] = (
    "Learning",
    "Portfolio",
    "Team experience",
    "Finding work",
    "Interest in the project",
    "Testing the idea",
)

CONSENT_ITEMS: tuple[str, ...] = (
    "Понимаю, что это MVP-тест",
    "Согласен с базовыми правилами",
    "Готов предоставить evidence работы",
    "Понимаю, что следующий шаг — ручная проверка",
)
