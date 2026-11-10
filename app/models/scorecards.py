from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import ScorecardItemKind, ScorecardStatus
from app.models.mixins import TimestampMixin, str_enum


class Scorecard(TimestampMixin, Base):
    __tablename__ = "scorecards"

    opening_id: Mapped[int] = mapped_column(ForeignKey("role_openings.id"), unique=True)
    mission: Mapped[str] = mapped_column(Text)
    status: Mapped[ScorecardStatus] = mapped_column(str_enum(ScorecardStatus), default=ScorecardStatus.draft)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    opening: Mapped["RoleOpening"] = relationship(back_populates="scorecard")
    approved_by: Mapped["User | None"] = relationship(back_populates="scorecards_approved")
    items: Mapped[list["ScorecardItem"]] = relationship(back_populates="scorecard", order_by="ScorecardItem.position")


class ScorecardItem(TimestampMixin, Base):
    __tablename__ = "scorecard_items"

    scorecard_id: Mapped[int] = mapped_column(ForeignKey("scorecards.id"))
    kind: Mapped[ScorecardItemKind] = mapped_column(str_enum(ScorecardItemKind))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    measure: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int]

    scorecard: Mapped["Scorecard"] = relationship(back_populates="items")
    ratings: Mapped[list["Rating"]] = relationship(back_populates="scorecard_item")
