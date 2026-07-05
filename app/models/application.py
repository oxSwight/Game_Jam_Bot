from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Enum, Float, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.event import Team
    from app.models.log import Log
    from app.models.user import User


class ApplicationStatus(str, enum.Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class Application(Base, TimestampMixin):
    __tablename__ = "applications"
    __table_args__ = (
        # Enforces at most one non-rejected application per user at the DB level,
        # closing the TOCTOU window between the service-level check and INSERT.
        Index(
            "ix_applications_one_active_per_user",
            "user_id",
            unique=True,
            sqlite_where=text("status != 'rejected'"),
            postgresql_where=text("status != 'rejected'"),
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True
    )

    main_category: Mapped[str] = mapped_column(String(64), nullable=False)
    blueprint_subcategory: Mapped[str | None] = mapped_column(String(64), nullable=True)
    skill_category_id: Mapped[str] = mapped_column(String(64), nullable=False)
    skill_category_title: Mapped[str] = mapped_column(String(128), nullable=False)
    subcategories: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    experience_level: Mapped[str] = mapped_column(String(32), nullable=False)
    engine: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    engine_other: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    tools_other: Mapped[str | None] = mapped_column(Text, nullable=True)
    motivations: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    consent_accepted: Mapped[bool] = mapped_column(default=True, server_default="1")

    status: Mapped[ApplicationStatus] = mapped_column(
        # values_callable is critical: without it a non-native Enum stores the
        # member NAME ("REJECTED"), but server_default and the partial unique
        # index below use the lowercase VALUE ("rejected"). That mismatch made
        # rejected rows count as "active" in the index and blocked re-registration.
        Enum(
            ApplicationStatus,
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ApplicationStatus.PENDING_REVIEW,
        server_default=ApplicationStatus.PENDING_REVIEW.value,
        index=True,
    )

    layer_1_team_result: Mapped[float | None] = mapped_column(Float, nullable=True)
    layer_2_head_to_head: Mapped[float | None] = mapped_column(Float, nullable=True)
    layer_3_individual: Mapped[float | None] = mapped_column(Float, nullable=True)
    layer_4_skill_progression: Mapped[float | None] = mapped_column(Float, nullable=True)
    layer_5_community_feedback: Mapped[float | None] = mapped_column(Float, nullable=True)

    user: Mapped[User] = relationship(back_populates="applications", lazy="joined")
    team: Mapped[Team | None] = relationship(back_populates="members", lazy="joined")
    logs: Mapped[list[Log]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def layer_scores(self) -> list[float | None]:
        return [
            self.layer_1_team_result,
            self.layer_2_head_to_head,
            self.layer_3_individual,
            self.layer_4_skill_progression,
            self.layer_5_community_feedback,
        ]

    @property
    def total_score(self) -> float:
        """Sum of the layer scores that have been set (unset layers count as 0)."""
        return sum(s for s in self.layer_scores if s is not None)

    @property
    def has_any_score(self) -> bool:
        return any(s is not None for s in self.layer_scores)

    def __repr__(self) -> str:
        return f"<Application id={self.id} status={self.status}>"
