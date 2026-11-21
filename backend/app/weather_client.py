"""Thin async client for the free Open-Meteo APIs (no API key needed)."""

import re
import statistics
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import HTTP_TIMEOUT_SECONDS
from app.schemas import CurrentWeather, DailyWeather, Location
from app.validation import parse_coordinates, validate_location_query
from app.weather_codes import describe, icon

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
REVERSE_GEOCODE_URL = "https://api.bigdatacloud.net/data/reverse-geocode-client"

# Open-Meteo's geocoder knows UK outward codes ("SW1A") but not full postcodes ("SW1A 1AA").
_UK_POSTCODE_RE = re.compile(r"^([A-Z]{1,2}\d[A-Z\d]?)\s*\d[A-Z]{2}$", re.I)

# The forecast API also serves the recent past; older dates come from the archive.
FORECAST_PAST_DAYS = 60

DAILY_FIELDS = [
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "uv_index_max",
]
ARCHIVE_DAILY_FIELDS = [
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "wind_speed_10m_max",
]
CURRENT_FIELDS = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
    "is_day",
]


class WeatherServiceError(Exception):
    """The upstream weather service failed or returned something unusable."""


class LocationNotFound(Exception):
    pass


class _TTLCache:
    def __init__(self, ttl_seconds: float, max_items: int = 512):
        self.ttl = ttl_seconds
        self.max_items = max_items
        self._data: dict[Any, tuple[float, Any]] = {}

    def get(self, key: Any) -> Any | None:
        hit = self._data.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        self._data.pop(key, None)
        return None

    def set(self, key: Any, value: Any) -> None:
        if len(self._data) >= self.max_items:
            self._data.pop(next(iter(self._data)))
        self._data[key] = (time.monotonic() + self.ttl, value)


_geocode_cache = _TTLCache(ttl_seconds=24 * 3600)
_forecast_cache = _TTLCache(ttl_seconds=10 * 60)
_normals_cache = _TTLCache(ttl_seconds=24 * 3600)


async def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(url, params=params)
    except httpx.HTTPError as exc:
        raise WeatherServiceError(f"Could not reach weather service: {exc.__class__.__name__}") from exc
    if resp.status_code != 200:
        reason = ""
        try:
            reason = resp.json().get("reason", "")
        except ValueError:
            pass
        raise WeatherServiceError(f"Weather service error ({resp.status_code}) {reason}".strip())
    return resp.json()


def _label(name: str, admin1: str | None, country: str | None) -> str:
    parts = [name]
    if admin1 and admin1 != name:
        parts.append(admin1)
    if country:
        parts.append(country)
    return ", ".join(parts)


async def search_locations(query: str, count: int = 5) -> list[Location]:
    query = validate_location_query(query)
    coords = parse_coordinates(query)
    if coords:
        return [await reverse_geocode(*coords)]

    key = (query.lower(), count)
    if (cached := _geocode_cache.get(key)) is not None:
        return cached

    data = await _get_json(GEOCODE_URL, {"name": query, "count": count, "language": "en", "format": "json"})
    results = [
        Location(
            name=r["name"],
            label=_label(r["name"], r.get("admin1"), r.get("country")),
            latitude=r["latitude"],
            longitude=r["longitude"],
            country=r.get("country"),
            admin1=r.get("admin1"),
            timezone=r.get("timezone"),
        )
        for r in data.get("results", [])
    ]
    if not results and (uk := _UK_POSTCODE_RE.match(query)):
        results = await search_locations(uk.group(1).upper(), count)
    _geocode_cache.set(key, results)
    return results


async def resolve_location(query: str) -> Location:
    """Turn free text into one location, or raise LocationNotFound."""
    results = await search_locations(query, count=1)
    if not results:
        raise LocationNotFound(f"Could not find a location matching '{query}'. Try a city name or postal code.")
    return results[0]


async def reverse_geocode(latitude: float, longitude: float) -> Location:
    """Best-effort place name for coordinates; falls back to the raw coordinates."""
    fallback = f"{latitude:.3f}, {longitude:.3f}"
    try:
        data = await _get_json(
            REVERSE_GEOCODE_URL,
            {"latitude": latitude, "longitude": longitude, "localityLanguage": "en"},
        )
        name = data.get("city") or data.get("locality") or fallback
        label = _label(name, data.get("principalSubdivision") or None, data.get("countryName") or None)
        return Location(
            name=name,
            label=label,
            latitude=latitude,
            longitude=longitude,
            country=data.get("countryName") or None,
            admin1=data.get("principalSubdivision") or None,
        )
    except WeatherServiceError:
        return Location(name=fallback, label=fallback, latitude=latitude, longitude=longitude)


def _daily_from_payload(payload: dict[str, Any], source: str) -> list[DailyWeather]:
    daily = payload.get("daily") or {}
    days = []
    for i, day in enumerate(daily.get("time", [])):
        def val(field: str) -> Any:
            values = daily.get(field)
            return values[i] if values and i < len(values) else None

        code = val("weather_code")
        days.append(
            DailyWeather(
                date=date.fromisoformat(day),
                source=source,
                weather_code=code,
                description=describe(code),
                icon=icon(code),
                temp_max=val("temperature_2m_max"),
                temp_min=val("temperature_2m_min"),
                precipitation_sum=val("precipitation_sum"),
                precipitation_probability_max=val("precipitation_probability_max"),
                wind_speed_max=val("wind_speed_10m_max"),
                uv_index_max=val("uv_index_max"),
            )
        )
    return days


async def get_forecast(location: Location, days: int = 6) -> tuple[CurrentWeather, list[DailyWeather], datetime]:
    """Current conditions plus `days` daily forecasts starting today, and when they were retrieved (may be cached)."""
    key = (round(location.latitude, 3), round(location.longitude, 3), days)
    if (cached := _forecast_cache.get(key)) is not None:
        return cached

    payload = await _get_json(
        FORECAST_URL,
        {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "current": ",".join(CURRENT_FIELDS),
            "daily": ",".join(DAILY_FIELDS),
            "forecast_days": days,
            "timezone": "auto",
        },
    )
    c = payload.get("current") or {}
    if not c:
        raise WeatherServiceError("Weather service returned no current conditions.")
    code = c.get("weather_code")
    current = CurrentWeather(
        time=c.get("time", ""),
        temperature=c.get("temperature_2m"),
        apparent_temperature=c.get("apparent_temperature"),
        relative_humidity=c.get("relative_humidity_2m"),
        precipitation=c.get("precipitation"),
        wind_speed=c.get("wind_speed_10m"),
        wind_direction=c.get("wind_direction_10m"),
        weather_code=code,
        description=describe(code),
        icon=icon(code),
        is_day=bool(c.get("is_day", 1)),
    )
    result = (current, _daily_from_payload(payload, "forecast"), datetime.now(timezone.utc))
    _forecast_cache.set(key, result)
    return result


async def get_daily_range(latitude: float, longitude: float, start: date, end: date) -> list[DailyWeather]:
    """Daily weather for any validated range, mixing historical and forecast data as needed."""
    today = date.today()
    cutoff = today - timedelta(days=FORECAST_PAST_DAYS)
    days: list[DailyWeather] = []

    if start < cutoff:
        archive_end = min(end, cutoff - timedelta(days=1))
        payload = await _get_json(
            ARCHIVE_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "start_date": start.isoformat(),
                "end_date": archive_end.isoformat(),
                "daily": ",".join(ARCHIVE_DAILY_FIELDS),
                "timezone": "auto",
            },
        )
        days += _daily_from_payload(payload, "historical")

    if end >= cutoff:
        fc_start = max(start, cutoff)
        payload = await _get_json(
            FORECAST_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "start_date": fc_start.isoformat(),
                "end_date": end.isoformat(),
                "daily": ",".join(DAILY_FIELDS),
                "timezone": "auto",
            },
        )
        for d in _daily_from_payload(payload, "forecast"):
            # Past dates served by the forecast API are observations, not predictions.
            d.source = "historical" if d.date < today else "forecast"
            days.append(d)

    return days


@dataclass(frozen=True)
class ClimateNormals:
    years: int
    normal_high: float
    normal_low: float
    high_stdev: float
    wet_day_percent: float


async def get_normals(latitude: float, longitude: float, day: date, years: int = 30, window: int = 3) -> ClimateNormals:
    """Average high/low for +/- `window` days around `day`'s calendar date over the last `years` full years."""
    key = (round(latitude, 2), round(longitude, 2), day.month, day.day, years)
    if (cached := _normals_cache.get(key)) is not None:
        return cached

    last_year = day.year - 1
    payload = await _get_json(
        ARCHIVE_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": date(last_year - years + 1, 1, 1).isoformat(),
            "end_date": date(last_year, 12, 31).isoformat(),
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
        },
    )
    daily = payload.get("daily") or {}
    target = _day_of_year(day)
    highs: list[float] = []
    lows: list[float] = []
    wet: list[bool] = []
    for i, ds in enumerate(daily.get("time", [])):
        diff = abs(_day_of_year(date.fromisoformat(ds)) - target)
        if min(diff, 365 - diff) > window:
            continue
        hi, lo, pr = daily["temperature_2m_max"][i], daily["temperature_2m_min"][i], daily["precipitation_sum"][i]
        if hi is not None:
            highs.append(hi)
        if lo is not None:
            lows.append(lo)
        if pr is not None:
            wet.append(pr >= 1.0)
    if len(highs) < 2 or not lows:
        raise WeatherServiceError("No historical data available for this location.")

    normals = ClimateNormals(
        years=years,
        normal_high=round(statistics.fmean(highs), 1),
        normal_low=round(statistics.fmean(lows), 1),
        high_stdev=round(statistics.stdev(highs), 2),
        wet_day_percent=round(100 * sum(wet) / len(wet), 1) if wet else 0.0,
    )
    _normals_cache.set(key, normals)
    return normals


def _day_of_year(d: date) -> int:
    # Ignore Feb 29 so leap years line up with normal years.
    return date(2001, d.month, min(d.day, 28) if d.month == 2 else d.day).timetuple().tm_yday
