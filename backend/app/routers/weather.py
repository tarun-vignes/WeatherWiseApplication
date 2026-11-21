from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.insights import compare_to_normals, rank_activity_days
from app.schemas import Activity, ActivityResponse, Location, NormalsResponse, WeatherResponse
from app.validation import validate_coordinates
from app.weather_client import get_forecast, get_normals, resolve_location, reverse_geocode, search_locations

router = APIRouter(prefix="/api", tags=["weather"])


async def _location(q: str | None, lat: float | None, lon: float | None) -> Location:
    if q:
        return await resolve_location(q)
    if lat is None or lon is None:
        raise HTTPException(422, "Provide either q (location) or both lat and lon.")
    validate_coordinates(lat, lon)
    return await reverse_geocode(lat, lon)


@router.get("/locations/search", response_model=list[Location])
async def location_search(q: str = Query(..., min_length=2, max_length=200), count: int = Query(5, ge=1, le=10)):
    """Autocomplete / validation: city names, postal codes, or 'lat,lon'."""
    return await search_locations(q, count)


@router.get("/weather", response_model=WeatherResponse)
async def weather(q: str | None = None, lat: float | None = None, lon: float | None = None):
    """Current conditions plus today and the next 5 days."""
    loc = await _location(q, lat, lon)
    current, daily, retrieved_at = await get_forecast(loc, days=6)
    return WeatherResponse(location=loc, current=current, daily=daily, retrieved_at=retrieved_at)


@router.get("/weather/normals", response_model=NormalsResponse)
async def normals(lat: float, lon: float):
    """How today's forecast high compares with the 30-year average for this date."""
    validate_coordinates(lat, lon)
    loc = Location(name="", label="", latitude=lat, longitude=lon)
    _, daily, _ = await get_forecast(loc, days=6)
    today_high = daily[0].temp_max if daily else None
    day = daily[0].date if daily else date.today()
    return compare_to_normals(day, await get_normals(lat, lon, day), today_high)


@router.get("/weather/activity", response_model=ActivityResponse)
async def activity(lat: float, lon: float, activity: Activity):
    """Score each of the next 6 days for an outdoor activity."""
    validate_coordinates(lat, lon)
    loc = Location(name="", label="", latitude=lat, longitude=lon)
    _, daily, _ = await get_forecast(loc, days=6)
    return rank_activity_days(daily, activity)
