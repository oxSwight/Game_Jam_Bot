from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.data.catalog import (
    ALL_ENGINES,
    ALL_TOOLS,
    CATEGORY_BY_ID,
    EXPERIENCE_LEVELS,
    MOTIVATIONS,
    role_titles,
)


class TelegramIdentity(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    telegram_id: int
    telegram_username: str | None = None


class NicknameStep(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nickname: str = Field(min_length=2, max_length=32)


class EmailStep(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr


class CategoryStep(BaseModel):
    main_category: str
    blueprint_subcategory: str | None = None
    skill_category_id: str
    skill_category_title: str
    subcategories: list[str] = Field(min_length=1)

    @field_validator("main_category")
    @classmethod
    def validate_main_category(cls, value: str) -> str:
        if value not in CATEGORY_BY_ID:
            raise ValueError("invalid main category")
        return value


class ExperienceStep(BaseModel):
    experience_level: str

    @field_validator("experience_level")
    @classmethod
    def validate_experience(cls, value: str) -> str:
        if value not in EXPERIENCE_LEVELS:
            raise ValueError("invalid experience level")
        return value


class ToolsStep(BaseModel):
    tools: list[str] = Field(min_length=1)
    tools_other: str | None = Field(default=None, min_length=2)

    @field_validator("tools")
    @classmethod
    def validate_tools(cls, value: list[str]) -> list[str]:
        invalid = [tool for tool in value if tool not in ALL_TOOLS]
        if invalid:
            raise ValueError(f"invalid tools: {', '.join(invalid)}")
        return value

    @field_validator("tools_other")
    @classmethod
    def require_other_text(cls, value: str | None, info) -> str | None:
        tools = info.data.get("tools", [])
        if "Other" in tools and not value:
            raise ValueError("tools_other is required when Other is selected")
        return value


class MotivationStep(BaseModel):
    motivations: list[str] = Field(min_length=1)

    @field_validator("motivations")
    @classmethod
    def validate_motivations(cls, value: list[str]) -> list[str]:
        allowed = set(MOTIVATIONS)
        invalid = [item for item in value if item not in allowed]
        if invalid:
            raise ValueError(f"invalid motivations: {', '.join(invalid)}")
        return value


class RegistrationCreate(BaseModel):
    """Final payload validated before persisting to the database."""

    model_config = ConfigDict(str_strip_whitespace=True)

    identity: TelegramIdentity
    nickname: str = Field(min_length=2, max_length=32)
    email: EmailStr
    main_category: str
    blueprint_subcategory: str | None = None
    skill_category_id: str
    skill_category_title: str
    subcategories: list[str] = Field(min_length=1)
    experience_level: str
    engine: list[str] = Field(min_length=1)
    engine_other: str | None = None
    tools: list[str] = Field(min_length=1)
    tools_other: str | None = None
    motivations: list[str] = Field(min_length=1)
    consent_accepted: bool = True

    @field_validator("main_category")
    @classmethod
    def validate_main_category(cls, value: str) -> str:
        if value not in CATEGORY_BY_ID:
            raise ValueError("invalid main category")
        return value

    # The multi-select handlers append whatever token arrives in callback_data,
    # so the final payload is where forged values get stopped: everything below
    # must come from the fixed catalog, or the submission is refused.
    @field_validator("experience_level")
    @classmethod
    def validate_experience(cls, value: str) -> str:
        if value not in EXPERIENCE_LEVELS:
            raise ValueError("invalid experience level")
        return value

    @field_validator("engine")
    @classmethod
    def validate_engine(cls, value: list[str]) -> list[str]:
        invalid = [item for item in value if item not in ALL_ENGINES]
        if invalid:
            raise ValueError(f"invalid engines: {', '.join(invalid)}")
        return value

    @field_validator("tools")
    @classmethod
    def validate_tools(cls, value: list[str]) -> list[str]:
        invalid = [item for item in value if item not in ALL_TOOLS]
        if invalid:
            raise ValueError(f"invalid tools: {', '.join(invalid)}")
        return value

    @field_validator("motivations")
    @classmethod
    def validate_motivations(cls, value: list[str]) -> list[str]:
        invalid = [item for item in value if item not in MOTIVATIONS]
        if invalid:
            raise ValueError(f"invalid motivations: {', '.join(invalid)}")
        return value

    @classmethod
    def from_fsm_data(cls, data: dict, telegram_id: int, telegram_username: str | None) -> "RegistrationCreate":
        category_id = data["category_id"]
        role_ids = list(data.get("roles", []))
        return cls(
            identity=TelegramIdentity(telegram_id=telegram_id, telegram_username=telegram_username),
            nickname=data["nickname"],
            email=data["email"],
            main_category=category_id,
            blueprint_subcategory=None,
            skill_category_id=category_id,
            skill_category_title=data["category_title"],
            # Persist human-readable role titles so every downstream view
            # (status, summary, admin notification) renders without lookups.
            subcategories=role_titles(role_ids),
            experience_level=data["experience_level"],
            engine=data.get("engine", []),
            engine_other=data.get("engine_other"),
            tools=data.get("tools", []),
            tools_other=data.get("tools_other"),
            motivations=data.get("motivations", []),
            consent_accepted=bool(data.get("consent", True)),
        )


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    player_code: int | None = None
    status: str
    is_active: bool = False
    nickname: str | None = None
    email: str | None = None
    main_category: str
    skill_category_title: str
    subcategories: list[str]
    experience_level: str
    engine: list[str] = []
    engine_other: str | None = None
    tools: list[str]
    tools_other: str | None = None
    motivations: list[str]
    telegram_id: int | None = None
    telegram_username: str | None = None
