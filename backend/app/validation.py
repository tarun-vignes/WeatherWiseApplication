"""Location and date-range rules, kept separate so they are easy to unit test."""

import re
from datetime import date, timedelta

# Open-Meteo historical data starts in 1940; forecasts reach 16 days (today + 15).
EARLIEST_DATE = date(1940, 1, 1)
MAX_FORECAST_DAYS_AHEAD = 15
MAX_RANGE_DAYS = 31

_COORDS_RE = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


class ValidationProblem(ValueError):
    """A user-facing validation error (returned as HTTP 422)."""


def validate_date_range(start: date, end: date, today: date | None = None) -> None:
    today = today or date.today()
    latest = today + timedelta(days=MAX_FORECAST_DAYS_AHEAD)

    if end < start:
        raise ValidationProblem("End date must be on or after the start date.")
    if start < EARLIEST_DATE:
        raise ValidationProblem(f"Start date must be on or after {EARLIEST_DATE.isoformat()} (no data before then).")
    if end > latest:
        raise ValidationProblem(
            f"End date can be at most {MAX_FORECAST_DAYS_AHEAD} days from today ({latest.isoformat()}); "
            "forecasts are not available further out."
        )
    span = (end - start).days + 1
    if span > MAX_RANGE_DAYS:
        raise ValidationProblem(f"Date range is {span} days; the maximum is {MAX_RANGE_DAYS} days.")


def validate_coordinates(latitude: float, longitude: float) -> None:
    if not -90 <= latitude <= 90:
        raise ValidationProblem("Latitude must be between -90 and 90.")
    if not -180 <= longitude <= 180:
        raise ValidationProblem("Longitude must be between -180 and 180.")


def parse_coordinates(text: str) -> tuple[float, float] | None:
    """Parse "lat, lon" input. Returns None if the text is not a coordinate pair."""
    match = _COORDS_RE.match(text)
    if not match:
        return None
    lat, lon = float(match.group(1)), float(match.group(2))
    validate_coordinates(lat, lon)
    return lat, lon


def validate_location_query(text: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) < 2:
        raise ValidationProblem("Location must be at least 2 characters.")
    if len(cleaned) > 200:
        raise ValidationProblem("Location must be at most 200 characters.")
    return cleaned
