from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import CheckStatus
from app.models.mixins import TimestampMixin, str_enum


class SafeguardingCheck(TimestampMixin, Base):
    __tablename__ = "safeguarding_checks"

    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    check_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[CheckStatus] = mapped_column(str_enum(CheckStatus), default=CheckStatus.pending)
    notes: Mapped[str | None] = mapped_column(Text)
    verified_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    application: Mapped["Application"] = relationship(back_populates="safeguarding_checks")
    verified_by: Mapped["User | None"] = relationship(back_populates="safeguarding_checks_verified")
