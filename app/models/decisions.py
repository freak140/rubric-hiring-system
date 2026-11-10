from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import DecisionOutcome, Grade
from app.models.mixins import TimestampMixin, str_enum


class Decision(TimestampMixin, Base):
    __tablename__ = "decisions"

    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), unique=True)
    outcome: Mapped[DecisionOutcome] = mapped_column(str_enum(DecisionOutcome))
    overall_grade: Mapped[Grade] = mapped_column(str_enum(Grade))
    rationale: Mapped[str] = mapped_column(Text)
    decided_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    application: Mapped["Application"] = relationship(back_populates="decision")
    decided_by: Mapped["User"] = relationship(back_populates="decisions_made")
