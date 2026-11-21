import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app import llm
from app.db import get_db
from app.export import MEDIA_TYPES, ExportFormat, render
from app.insights import briefing_bullets
from app.models import Trip, TripDay
from app.schemas import Briefing, DailyWeather, Location, TripCreate, TripOut, TripUpdate
from app.validation import ValidationProblem, validate_coordinates, validate_date_range
from app.weather_client import WeatherServiceError, get_daily_range, resolve_location, reverse_geocode

router = APIRouter(prefix="/api/trips", tags=["trips"])

# A stored day is only useful with these; both Open-Meteo APIs (forecast and archive) always provide them.
REQUIRED_DAY_FIELDS = ("temp_max", "temp_min")


def _get_trip(db: Session, trip_id: int) -> Trip:
    trip = db.scalar(select(Trip).options(selectinload(Trip.days)).where(Trip.id == trip_id))
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Trip {trip_id} not found.")
    return trip


async def _resolve(location: str | None, lat: float | None, lon: float | None) -> tuple[str, Location]:
    if location:
        return location, await resolve_location(location)
    if lat is None or lon is None:
        raise ValidationProblem("Provide a location or both latitude and longitude.")
    validate_coordinates(lat, lon)
    return f"{lat:.4f},{lon:.4f}", await reverse_geocode(lat, lon)


async def _fetch_days(latitude: float, longitude: float, start: date, end: date) -> list[TripDay]:
    """Download weather for every date in the range, or raise without touching any stored data."""
    fetched = await get_daily_range(latitude, longitude, start, end)
    by_date = {d.date: d for d in fetched}
    expected = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    missing = [d for d in expected if d not in by_date]
    if missing:
        shown = ", ".join(d.isoformat() for d in missing[:3]) + ("…" if len(missing) > 3 else "")
        raise WeatherServiceError(
            f"Weather service returned incomplete data ({len(missing)} of {len(expected)} days missing: {shown}). "
            "Saved weather was not changed; try again later."
        )
    # Every day must have the core values; optional ones (UV, rain chance, conditions) may be null.
    unusable = [d for d in expected if any(getattr(by_date[d], f) is None for f in REQUIRED_DAY_FIELDS)]
    if unusable:
        shown = ", ".join(d.isoformat() for d in unusable[:3]) + ("…" if len(unusable) > 3 else "")
        raise WeatherServiceError(
            f"Weather service returned no temperatures for {len(unusable)} of {len(expected)} days ({shown}). "
            "Saved weather was not changed; try again later."
        )
    return [
        TripDay(
            date=d.date,
            source=d.source,
            weather_code=d.weather_code,
            temp_max=d.temp_max,
            temp_min=d.temp_min,
            precipitation_sum=d.precipitation_sum,
            precipitation_probability_max=d.precipitation_probability_max,
            wind_speed_max=d.wind_speed_max,
            uv_index_max=d.uv_index_max,
        )
        for d in (by_date[day] for day in expected)
    ]


def _replace_weather(trip: Trip, days: list[TripDay]) -> None:
    trip.days = days
    trip.weather_updated_at = datetime.now(timezone.utc)


# --- Create -----------------------------------------------------------------

@router.post("", response_model=TripOut, status_code=status.HTTP_201_CREATED)
async def create_trip(body: TripCreate, db: Session = Depends(get_db)):
    query, loc = await _resolve(body.location, body.latitude, body.longitude)
    if body.location_label and not body.location:
        loc.label = body.location_label
    days = await _fetch_days(loc.latitude, loc.longitude, body.start_date, body.end_date)
    trip = Trip(
        name=body.name or f"{loc.name} trip",
        location_query=query,
        location_name=loc.label,
        latitude=loc.latitude,
        longitude=loc.longitude,
        timezone=loc.timezone or "auto",
        start_date=body.start_date,
        end_date=body.end_date,
        activity=body.activity,
        notes=body.notes,
    )
    _replace_weather(trip, days)
    db.add(trip)
    db.commit()
    return _get_trip(db, trip.id)


# --- Read -------------------------------------------------------------------

@router.get("", response_model=list[TripOut])
def list_trips(q: str | None = Query(None, max_length=100), db: Session = Depends(get_db)):
    stmt = select(Trip).options(selectinload(Trip.days)).order_by(Trip.start_date.desc(), Trip.id.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Trip.name.ilike(like), Trip.location_name.ilike(like), Trip.notes.ilike(like)))
    return db.scalars(stmt).all()


@router.get("/export")
def export_all(format: ExportFormat = "csv", db: Session = Depends(get_db)):
    trips = db.scalars(select(Trip).options(selectinload(Trip.days)).order_by(Trip.start_date)).all()
    return _download(render(list(trips), format), format, "weather-trips")


@router.get("/{trip_id}", response_model=TripOut)
def get_trip(trip_id: int, db: Session = Depends(get_db)):
    return _get_trip(db, trip_id)


@router.get("/{trip_id}/export")
def export_one(trip_id: int, format: ExportFormat = "csv", db: Session = Depends(get_db)):
    return _download(render([_get_trip(db, trip_id)], format), format, f"trip-{trip_id}")


@router.get("/{trip_id}/briefing", response_model=Briefing)
async def trip_briefing(trip_id: int, db: Session = Depends(get_db)):
    """Packing/planning advice from the stored weather. Uses the LLM if configured, else rules."""
    trip = _get_trip(db, trip_id)
    days = [DailyWeather.model_validate(d, from_attributes=True) for d in trip.days]
    bullets = briefing_bullets(trip.location_name, days, trip.activity)

    if llm.enabled():
        data = [d.model_dump(mode="json", exclude={"icon", "description"}) for d in days]
        text = await llm.chat(
            "You write short, friendly trip weather briefings (3-4 sentences). Use ONLY the facts and data given; "
            "do not invent numbers. Give temperatures in °C and °F. End with one practical packing tip.",
            f"Trip: {trip.name} to {trip.location_name}, {trip.start_date} to {trip.end_date}. "
            f"Activity: {trip.activity or 'none'}. Notes: {trip.notes or 'none'}.\n"
            f"Facts: {json.dumps(bullets)}\nDaily data (WMO weather codes): {json.dumps(data)}",
        )
        if text:
            return Briefing(text=text, bullets=bullets, source="llm")
    return Briefing(text=" ".join(bullets), bullets=bullets, source="rules")


# --- Update -----------------------------------------------------------------

@router.api_route("/{trip_id}", methods=["PUT", "PATCH"], response_model=TripOut)
async def update_trip(trip_id: int, body: TripUpdate, db: Session = Depends(get_db)):
    trip = _get_trip(db, trip_id)
    changes = body.model_dump(exclude_unset=True)

    start = changes.get("start_date", trip.start_date)
    end = changes.get("end_date", trip.end_date)
    validate_date_range(start, end)

    location_changed = any(k in changes for k in ("location", "latitude", "longitude"))
    if location_changed:
        query, loc = await _resolve(changes.get("location"), changes.get("latitude"), changes.get("longitude"))
        lat, lon = loc.latitude, loc.longitude
    else:
        lat, lon = trip.latitude, trip.longitude

    # Fetch first: if the weather service fails, nothing about the trip changes.
    days = None
    if location_changed or start != trip.start_date or end != trip.end_date:
        days = await _fetch_days(lat, lon, start, end)

    if location_changed:
        trip.location_query, trip.location_name = query, loc.label
        trip.latitude, trip.longitude = loc.latitude, loc.longitude
        trip.timezone = loc.timezone or "auto"
    trip.start_date, trip.end_date = start, end
    if "name" in changes:
        trip.name = changes["name"]
    for field in ("activity", "notes"):
        if field in changes:
            setattr(trip, field, changes[field])
    if days is not None:
        _replace_weather(trip, days)
    db.commit()
    return _get_trip(db, trip.id)


@router.post("/{trip_id}/refresh", response_model=TripOut)
async def refresh_trip(trip_id: int, db: Session = Depends(get_db)):
    """Re-download the weather for a trip (forecasts change over time)."""
    trip = _get_trip(db, trip_id)
    _replace_weather(trip, await _fetch_days(trip.latitude, trip.longitude, trip.start_date, trip.end_date))
    db.commit()
    return _get_trip(db, trip.id)


# --- Delete -----------------------------------------------------------------

@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(trip_id: int, db: Session = Depends(get_db)):
    db.delete(_get_trip(db, trip_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _download(content: str, fmt: str, basename: str) -> Response:
    return Response(
        content=content,
        media_type=f"{MEDIA_TYPES[fmt]}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{basename}.{fmt}"'},
    )
