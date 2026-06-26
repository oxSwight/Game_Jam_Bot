from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillCategory:
    id: str
    title: str
    description: str
    subcategories: tuple[str, ...]
    battle_roles: tuple[str, ...] = ()


EXPERIENCE_LEVELS: dict[str, str] = {
    "beginner": "Beginner (0–1 года)",
    "intermediate": "Intermediate (1–3 года)",
    "game_jam": "Game jam experience (3–9)",
    "commercial": "Commercial experience (9+)",
}

MAIN_CATEGORIES: dict[str, str] = {
    "environment_art": "Environment Art",
    "props_3d": "Props / 3D Modeling",
    "blueprint_programming": "Blueprint / Programming",
    "pm_coordination": "PM / Coordination",
    "other": "Other",
}

BLUEPRINT_SUBCATEGORIES: tuple[str, ...] = (
    "Level Design",
    "Lighting",
    "UI/UX",
    "QA",
)

TOOLS: tuple[str, ...] = (
    "Unreal Engine",
    "Unity",
    "Blender",
    "ZBrush",
    "Substance Painter / Designer",
    "Photoshop",
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

SKILL_CATEGORIES: tuple[SkillCategory, ...] = (
    SkillCategory(
        id="environment_art",
        title="1. Environment Art",
        description="Окружение, сцены, пропсы, материалы, локации.",
        subcategories=(
            "Environment Artist",
            "Level Artist",
            "Props Artist",
            "Hard Surface Props",
            "Modular Assets",
            "Set Dressing",
            "Materials / Texturing",
            "Foliage / Nature",
            "Terrain / Landscape",
            "Trim Sheets",
        ),
        battle_roles=(
            "Room Blockout",
            "Prop Modeling",
            "Scene Assembly",
            "Material Setup",
            "Environment Dressing",
            "Collision Setup",
            "Asset Optimization",
        ),
    ),
    SkillCategory(
        id="character_art",
        title="2. Character Art",
        description="Персонажи, существа, одежда, анатомия, sculpt.",
        subcategories=(
            "Character Artist",
            "Creature Artist",
            "Sculpting",
            "Anatomy Sculpting",
            "Clothes / Outfit",
            "Hair / Groom",
            "Retopology",
            "UV",
            "Baking",
            "Character Texturing",
        ),
        battle_roles=(
            "Character Sculpt",
            "Creature Blockout",
            "Outfit Modeling",
            "Retopology",
            "Texture Paint",
            "Character Presentation",
        ),
    ),
    SkillCategory(
        id="animation_rigging",
        title="3. Animation / Rigging",
        description="Движение, скелеты, rig, skinning, object animation.",
        subcategories=(
            "3D Animation",
            "Character Animation",
            "Object Animation",
            "Rigging",
            "Skinning",
            "Technical Animation",
            "Cinematic Animation",
        ),
        battle_roles=(
            "Door Animation",
            "Lamp Animation",
            "Character Idle",
            "Simple Interaction Animation",
            "Rig Setup",
            "Animation Import",
        ),
    ),
    SkillCategory(
        id="game_design",
        title="4. Game Design / Level Design",
        description="Правила, механики, структура уровня, player flow, puzzle logic.",
        subcategories=(
            "Game Designer",
            "Level Designer",
            "Puzzle Designer",
            "Mission Designer",
            "Encounter Designer",
            "Mechanics Designer",
            "Balance",
            "Documentation",
        ),
        battle_roles=(
            "Define Core Interaction",
            "Room Flow",
            "Puzzle Logic",
            "Player Path",
            "Rules Description",
            "Task Brief",
            "Design Constraints",
        ),
    ),
    SkillCategory(
        id="programming",
        title="5. Programming / Blueprints",
        description="Gameplay logic, interactions, Blueprints, C++, Unity C#, integration.",
        subcategories=(
            "Unreal Blueprints",
            "Unreal C++",
            "Unity C#",
            "Gameplay Programming",
            "Interaction Systems",
            "UI Logic",
            "Tools",
            "Integration",
            "Debugging",
            "Beginner / Learning",
        ),
        battle_roles=(
            "Button Interaction",
            "Lamp State Change",
            "Trigger Setup",
            "Gameplay Logic",
            "UI Hook",
            "Bug Fixing",
            "Build Preparation",
        ),
    ),
    SkillCategory(
        id="technical_art",
        title="6. Technical Art",
        description="Связь между art и tech: materials, shaders, optimization, tools, pipeline.",
        subcategories=(
            "Materials / Shaders",
            "Optimization",
            "Tools",
            "Procedural Setup",
            "VFX Technical Setup",
            "Rigging Support",
            "Engine Integration",
            "Performance",
            "Blueprint Utility",
        ),
        battle_roles=(
            "Master Material Setup",
            "Shader Setup",
            "Optimization Pass",
            "Asset Integration",
            "Technical Validation",
            "Pipeline Support",
        ),
    ),
    SkillCategory(
        id="lighting_vfx",
        title="7. Lighting / VFX / Presentation",
        description="Свет, эффекты, атмосфера, финальная подача, camera/presentation.",
        subcategories=(
            "Lighting Artist",
            "VFX Artist",
            "Post Process",
            "Cinematic Presentation",
            "Camera",
            "Atmosphere",
            "Particles",
            "Niagara",
            "Render / Screenshot Setup",
        ),
        battle_roles=(
            "Basic Lighting Pass",
            "Mood Lighting",
            "Lamp VFX",
            "Interaction Feedback",
            "Final Screenshot Setup",
            "Camera Flythrough",
            "Presentation Polish",
        ),
    ),
    SkillCategory(
        id="ui_ux",
        title="8. UI / UX",
        description="Интерфейсы, HUD, меню, подсказки, пользовательский опыт.",
        subcategories=(
            "UI Designer",
            "UX Designer",
            "HUD",
            "Menu Design",
            "Interaction Feedback",
            "Icons",
            "Wireframes",
            "UI Implementation",
        ),
        battle_roles=(
            "Interaction Prompt",
            "Simple HUD",
            "Button Hint",
            "Win / Fail Screen",
            "UI Layout",
            "UX Feedback",
        ),
    ),
    SkillCategory(
        id="sound_music",
        title="9. Sound / Music",
        description="Звук, музыка, ambient, feedback sounds, audio implementation.",
        subcategories=(
            "Sound Design",
            "Music",
            "Ambient Sound",
            "UI Sounds",
            "Interaction Sounds",
            "Voice",
            "Audio Implementation",
        ),
        battle_roles=(
            "Button Click Sound",
            "Lamp Turn On Sound",
            "Ambient Loop",
            "Success Sound",
            "Audio Integration",
        ),
    ),
    SkillCategory(
        id="pm_coordination",
        title="10. PM / Coordination",
        description="Координация команды, планирование, коммуникация.",
        subcategories=(
            "Project Manager",
            "Team Lead",
            "Scrum Master",
            "Producer",
            "Documentation",
            "Task Coordination",
        ),
        battle_roles=(),
    ),
    SkillCategory(
        id="undecided",
        title="11. Пока не знаю / хочу попробовать",
        description="Для новичков, которые ещё не понимают своё направление.",
        subcategories=(
            "Хочу попробовать 3D",
            "Хочу попробовать код",
            "Хочу попробовать дизайн",
            "Хочу помогать команде",
            "Не знаю, с чего начать",
            "Нужна вводная консультация",
        ),
        battle_roles=(
            "Assistant / Helper",
            "QA Beginner",
            "Simple Task Support",
            "Documentation Helper",
            "Evidence Helper",
            "Learning Participant",
        ),
    ),
)

SKILL_BY_ID: dict[str, SkillCategory] = {c.id: c for c in SKILL_CATEGORIES}

MAIN_TO_SKILL: dict[str, str] = {
    "environment_art": "environment_art",
    "props_3d": "environment_art",
    "blueprint_programming": "programming",
    "pm_coordination": "pm_coordination",
    "other": "undecided",
}
