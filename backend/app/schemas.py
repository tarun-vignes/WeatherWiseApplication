from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.validation import validate_date_range

Activity = Literal["running", "cycling", "hiking", "beach", "golf", "picnic"]


class Location(BaseModel):
    name: str
    label: str
    latitude: float
    longitude: float
    country: str | None = None
    admin1: str | None = None
    timezone: str | None = None


class DailyWeather(BaseModel):
    date: date
    source: str = "forecast"
    weather_code: int | None = None
    description: str = ""
    icon: str = ""
    temp_max: float | None = None
    temp_min: float | None = None
    precipitation_sum: float | None = None
    precipitation_probability_max: float | None = None
    wind_speed_max: float | None = None
    uv_index_max: float | None = None


class CurrentWeather(BaseModel):
    time: str
    temperature: float | None
    apparent_temperature: float | None
    relative_humidity: float | None
    precipitation: float | None
    wind_speed: float | None
    wind_direction: float | None
    weather_code: int | None
    description: str
    icon: str
    is_day: bool


class WeatherResponse(BaseModel):
    location: Location
    current: CurrentWeather
    daily: list[DailyWeather]
    retrieved_at: datetime = Field(description="When this data was fetched from Open-Meteo (responses are cached up to 10 minutes)")
    units: dict[str, str] = {"temperature": "°C", "precipitation": "mm", "wind_speed": "km/h"}


class NormalsResponse(BaseModel):
    date: date
    years: int
    normal_high: float
    normal_low: float
    wet_day_percent: float
    forecast_high: float | None = None
    delta: float | None = None
    label: str


class ActivityDay(BaseModel):
    date: date
    score: int
    rating: str
    reasons: list[str]


class ActivityResponse(BaseModel):
    activity: Activity
    best: ActivityDay | None
    days: list[ActivityDay]


class TripCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(None, max_length=120)
    location: str | None = Field(None, max_length=200, description="City, address or postal code, or 'lat,lon'")
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    location_label: str | None = Field(None, max_length=200, description="Display name to keep when saving by coordinates")
    start_date: date
    end_date: date
    activity: Activity | None = None
    notes: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _check(self) -> "TripCreate":
        if not self.location and (self.latitude is None or self.longitude is None):
            raise ValueError("Provide a location (name or postal code) or both latitude and longitude.")
        validate_date_range(self.start_date, self.end_date)
        return self


class TripUpdate(BaseModel):
    """Partial update. Changing location or dates re-fetches the stored weather."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(None, min_length=1, max_length=120)
    location: str | None = Field(None, max_length=200)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    start_date: date | None = None
    end_date: date | None = None
    activity: Activity | None = None
    notes: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _no_null_required_fields(self) -> "TripUpdate":
        # Omitting a field keeps its stored value; sending null for a field that can't be empty is an error.
        nulls = [f for f in ("name", "start_date", "end_date") if f in self.model_fields_set and getattr(self, f) is None]
        if nulls:
            raise ValueError(f"{', '.join(nulls)} cannot be null. To keep the current value, omit the field.")
        return self


class TripDayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    source: str
    weather_code: int | None
    temp_max: float | None
    temp_min: float | None
    precipitation_sum: float | None
    precipitation_probability_max: float | None
    wind_speed_max: float | None
    uv_index_max: float | None


class TripOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location_query: str
    location_name: str
    latitude: float
    longitude: float
    timezone: str
    start_date: date
    end_date: date
    activity: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    weather_updated_at: datetime | None
    days: list[TripDayOut]

    @field_validator("created_at", "updated_at", "weather_updated_at")
    @classmethod
    def _assume_utc(cls, value: datetime | None) -> datetime | None:
        # SQLite drops tzinfo; timestamps are always stored in UTC.
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


class Briefing(BaseModel):
    text: str
    bullets: list[str]
    source: Literal["llm", "rules"]


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)


class AskResponse(BaseModel):
    answer: str
    source: Literal["llm", "rules"]
    location: Location | None
    start_date: date | None
    end_date: date | None
    days: list[DailyWeather] = []
