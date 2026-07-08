from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, BigInteger, Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
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
            postgresql_where=text("status != 'rejected'"),
            sqlite_where=text("status != 'rejected'"),
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Category-coded public id, assigned at submit time: leading digit = discipline
    # (see CATEGORY_ID_PREFIX), e.g. 10007 = 7th programmer. Lets admins/research
    # tell disciplines apart at a glance. Unique across all applications.
    player_code: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, unique=True, index=True
    )
    # Snapshot of the contact details AS ENTERED for this application. Kept per-row
    # (not only on the shared User) so a later edit or re-registration never
    # rewrites what an older application recorded.
    nickname: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

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
    # Step F (beginner branch): what the applicant is best at. Empty for every
    # other experience level, which never sees the strengths step.
    strengths: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
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

    user: Mapped[User] = relationship(back_populates="applications", lazy="joined")
    logs: Mapped[list[Log]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Application id={self.id} status={self.status}>"
