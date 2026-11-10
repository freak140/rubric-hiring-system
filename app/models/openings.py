from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import OpeningStatus, RoleType
from app.models.mixins import TimestampMixin, str_enum


class RoleOpening(TimestampMixin, Base):
    __tablename__ = "role_openings"

    title: Mapped[str] = mapped_column(String(200))
    role_type: Mapped[RoleType] = mapped_column(str_enum(RoleType))
    department: Mapped[str] = mapped_column(String(200))
    status: Mapped[OpeningStatus] = mapped_column(str_enum(OpeningStatus), default=OpeningStatus.draft)
    hiring_manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    hiring_manager: Mapped["User"] = relationship(back_populates="openings_managed")
    scorecard: Mapped["Scorecard | None"] = relationship(back_populates="opening", cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship(back_populates="opening")
