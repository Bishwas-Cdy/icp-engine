from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    website: Mapped[str] = mapped_column(String(2048), index=True)
    industry: Mapped[str | None] = mapped_column(String(255))
    business_model: Mapped[str | None] = mapped_column(String(255))
    estimated_employee_range: Mapped[str | None] = mapped_column(String(100))
    target_market: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    signals: Mapped[list["Signal"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", lazy="selectin"
    )
    score: Mapped["Score"] = relationship(
        back_populates="company", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    evidence: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    confidence: Mapped[float] = mapped_column(Float)
    points: Mapped[int] = mapped_column(Integer, default=0)

    company: Mapped[Company] = relationship(back_populates="signals")


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), unique=True
    )
    industry_match: Mapped[int] = mapped_column(Integer)
    company_type_match: Mapped[int] = mapped_column(Integer)
    company_size_match: Mapped[int] = mapped_column(Integer)
    sales_motion_match: Mapped[int] = mapped_column(Integer)
    growth_signal_match: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer, index=True)
    explanation: Mapped[str] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="score")
