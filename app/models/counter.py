from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlayerCodeCounter(Base):
    """Per-category allocator for the public player_code.

    A single row per discipline holding the last code issued in that category's
    block. Codes are allocated with an atomic ``UPDATE … SET last_code = last_code
    + 1 RETURNING last_code``: the row lock serializes concurrent submissions, so
    two players confirming at the same moment can never be handed the same code
    (the old ``max()+1`` scan raced under aiogram's concurrent update handling).
    """

    __tablename__ = "player_code_counters"

    category_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_code: Mapped[int] = mapped_column(BigInteger, nullable=False)

    def __repr__(self) -> str:
        return f"<PlayerCodeCounter {self.category_id}={self.last_code}>"
