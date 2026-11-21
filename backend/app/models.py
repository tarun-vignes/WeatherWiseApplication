from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Trip(Base):
    """A saved location + date range, with the weather stored for each day."""

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    location_query: Mapped[str] = mapped_column(String(200))
    location_name: Mapped[str] = mapped_column(String(200))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    timezone: Mapped[str] = mapped_column(String(64), default="auto")
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    activity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    weather_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    days: Mapped[list["TripDay"]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="TripDay.date",
    )


class TripDay(Base):
    """Daily weather for one date of a trip. `source` is "forecast" or "historical"."""

    __tablename__ = "trip_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(16))
    weather_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temp_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    temp_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_sum: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_probability_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    uv_index_max: Mapped[float | None] = mapped_column(Float, nullable=True)

    trip: Mapped[Trip] = relationship(back_populates="days")
