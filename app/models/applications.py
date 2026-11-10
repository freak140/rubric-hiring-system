from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import ApplicationStage
from app.models.mixins import TimestampMixin, str_enum


class Application(TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("candidate_id", "opening_id"),)

    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="RESTRICT"))
    opening_id: Mapped[int] = mapped_column(ForeignKey("role_openings.id", ondelete="RESTRICT"))
    stage: Mapped[ApplicationStage] = mapped_column(str_enum(ApplicationStage), default=ApplicationStage.sourced)

    candidate: Mapped["Candidate"] = relationship(back_populates="applications")
    opening: Mapped["RoleOpening"] = relationship(back_populates="applications")
    interviews: Mapped[list["Interview"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    references: Mapped[list["Reference"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    safeguarding_checks: Mapped[list["SafeguardingCheck"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    decision: Mapped["Decision | None"] = relationship(back_populates="application", cascade="all, delete-orphan")
    sell_plan: Mapped["SellPlan | None"] = relationship(back_populates="application", cascade="all, delete-orphan")
