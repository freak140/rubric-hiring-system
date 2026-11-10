from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin


class SellPlan(TimestampMixin, Base):
    __tablename__ = "sell_plans"

    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), unique=True)
    fit: Mapped[str | None] = mapped_column(Text)
    family: Mapped[str | None] = mapped_column(Text)
    freedom: Mapped[str | None] = mapped_column(Text)
    fortune: Mapped[str | None] = mapped_column(Text)
    fun: Mapped[str | None] = mapped_column(Text)

    application: Mapped["Application"] = relationship(back_populates="sell_plan")
