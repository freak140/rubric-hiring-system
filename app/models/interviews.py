from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import Grade, InterviewStatus, InterviewType, ScreeningOutcome
from app.models.mixins import TimestampMixin, str_enum


class Interview(TimestampMixin, Base):
    __tablename__ = "interviews"

    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    interview_type: Mapped[InterviewType] = mapped_column(str_enum(InterviewType))
    interviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[InterviewStatus] = mapped_column(str_enum(InterviewStatus), default=InterviewStatus.assigned)
    notes: Mapped[str | None] = mapped_column(Text)
    screening_outcome: Mapped[ScreeningOutcome | None] = mapped_column(str_enum(ScreeningOutcome))
    release_reason: Mapped[str | None] = mapped_column(String(500))
    conducted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    application: Mapped["Application"] = relationship(back_populates="interviews")
    interviewer: Mapped["User"] = relationship(back_populates="interviews")
    ratings: Mapped[list["Rating"]] = relationship(back_populates="interview", cascade="all, delete-orphan")


class Rating(TimestampMixin, Base):
    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("interview_id", "scorecard_item_id"),)

    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"))
    scorecard_item_id: Mapped[int] = mapped_column(ForeignKey("scorecard_items.id"))
    grade: Mapped[Grade] = mapped_column(str_enum(Grade))
    evidence: Mapped[str] = mapped_column(Text)

    interview: Mapped["Interview"] = relationship(back_populates="ratings")
    scorecard_item: Mapped["ScorecardItem"] = relationship(back_populates="ratings")
