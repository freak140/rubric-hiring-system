from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import AppRole
from app.models.mixins import TimestampMixin, str_enum


class User(TimestampMixin, Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    app_role: Mapped[AppRole] = mapped_column(str_enum(AppRole))

    openings_managed: Mapped[list["RoleOpening"]] = relationship(back_populates="hiring_manager")
    scorecards_approved: Mapped[list["Scorecard"]] = relationship(back_populates="approved_by")
    interviews: Mapped[list["Interview"]] = relationship(back_populates="interviewer")
    references_conducted: Mapped[list["Reference"]] = relationship(back_populates="conducted_by")
    safeguarding_checks_verified: Mapped[list["SafeguardingCheck"]] = relationship(back_populates="verified_by")
    decisions_made: Mapped[list["Decision"]] = relationship(back_populates="decided_by")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="actor")
