from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Index, JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


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

    main_category: Mapped[str] = mapped_column(String(64), nullable=False)
    blueprint_subcategory: Mapped[str | None] = mapped_column(String(64), nullable=True)
    skill_category_id: Mapped[str] = mapped_column(String(64), nullable=False)
    skill_category_title: Mapped[str] = mapped_column(String(128), nullable=False)
    subcategories: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    experience_level: Mapped[str] = mapped_column(String(32), nullable=False)
    tools: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    tools_other: Mapped[str | None] = mapped_column(Text, nullable=True)
    motivations: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    consent_accepted: Mapped[bool] = mapped_column(default=True, server_default="1")

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, native_enum=False, length=32),
        default=ApplicationStatus.PENDING_REVIEW,
        server_default=ApplicationStatus.PENDING_REVIEW.value,
        index=True,
    )

    layer_1_team_result: Mapped[float | None] = mapped_column(Float, nullable=True)
    layer_2_head_to_head: Mapped[float | None] = mapped_column(Float, nullable=True)
    layer_3_individual: Mapped[float | None] = mapped_column(Float, nullable=True)
    layer_4_skill_progression: Mapped[float | None] = mapped_column(Float, nullable=True)
    layer_5_community_feedback: Mapped[float | None] = mapped_column(Float, nullable=True)

    user: Mapped["User"] = relationship(back_populates="applications", lazy="joined")
    logs: Mapped[list["Log"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Application id={self.id} status={self.status}>"
