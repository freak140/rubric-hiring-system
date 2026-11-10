from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import ReferenceStatus, RefereeRelationship
from app.models.mixins import TimestampMixin, str_enum


class Reference(TimestampMixin, Base):
    __tablename__ = "references"

    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    referee_name: Mapped[str] = mapped_column(String(200))
    referee_relationship: Mapped[RefereeRelationship] = mapped_column(str_enum(RefereeRelationship))
    contact: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[ReferenceStatus] = mapped_column(str_enum(ReferenceStatus), default=ReferenceStatus.named)
    notes: Mapped[str | None] = mapped_column(Text)
    conducted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    application: Mapped["Application"] = relationship(back_populates="references")
    conducted_by: Mapped["User | None"] = relationship(back_populates="references_conducted")
