from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db import Base
from app.models.enums import CandidateSource
from app.models.mixins import TimestampMixin, str_enum


class Candidate(TimestampMixin, Base):
    __tablename__ = "candidates"

    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[CandidateSource] = mapped_column(str_enum(CandidateSource))
    source_detail: Mapped[str | None] = mapped_column(String(200))

    applications: Mapped[list["Application"]] = relationship(back_populates="candidate")

    @validates("email")
    def _normalize_email(self, key: str, value: str) -> str:
        return value.strip().lower()
