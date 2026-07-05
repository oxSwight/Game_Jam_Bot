from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.application import Application


class EventStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    FINISHED = "finished"


class Event(Base, TimestampMixin):
    """A GameJam run. Groups teams and provides the scoring context that the
    five per-application layers feed into (Team Result, Head-to-Head, ...)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[EventStatus] = mapped_column(
        Enum(
            EventStatus,
            native_enum=False,
            length=16,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        default=EventStatus.DRAFT,
        server_default=EventStatus.DRAFT.value,
        index=True,
    )

    teams: Mapped[list[Team]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Event id={self.id} name={self.name!r} status={self.status}>"


class Team(Base, TimestampMixin):
    __tablename__ = "teams"
    __table_args__ = (
        # Team names are unique within their event, not globally.
        UniqueConstraint("event_id", "name", name="uq_team_event_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)

    event: Mapped[Event] = relationship(back_populates="teams")
    members: Mapped[list[Application]] = relationship(
        back_populates="team",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Team id={self.id} name={self.name!r} event_id={self.event_id}>"
