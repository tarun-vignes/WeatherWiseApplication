"""Rule-based weather insights. These work with no LLM and are also the LLM fallback."""

from dataclasses import dataclass
from datetime import date

from app.schemas import ActivityDay, ActivityResponse, DailyWeather, NormalsResponse
from app.weather_client import ClimateNormals
from app.weather_codes import SNOW_CODES, STORM_CODES


@dataclass(frozen=True)
class ActivityProfile:
    label: str
    temp_range: tuple[float, float]  # comfortable daily high, °C
    max_wind: float  # km/h
    max_rain_chance: float  # %
    wants_sun: bool = False


ACTIVITIES: dict[str, ActivityProfile] = {
    "running": ActivityProfile("Running", (8, 20), max_wind=25, max_rain_chance=30),
    "cycling": ActivityProfile("Cycling", (12, 25), max_wind=20, max_rain_chance=25),
    "hiking": ActivityProfile("Hiking", (10, 24), max_wind=30, max_rain_chance=30),
    "beach": ActivityProfile("Beach", (25, 34), max_wind=25, max_rain_chance=15, wants_sun=True),
    "golf": ActivityProfile("Golf", (15, 28), max_wind=20, max_rain_chance=20),
    "picnic": ActivityProfile("Picnic", (18, 28), max_wind=20, max_rain_chance=15, wants_sun=True),
}


def fmt_temp(celsius: float | None) -> str:
    if celsius is None:
        return "n/a"
    return f"{celsius:.0f}°C ({celsius * 9 / 5 + 32:.0f}°F)"


def weekday(d: date) -> str:
    return f"{d:%a %b} {d.day}"


def rain_chance(day: DailyWeather) -> float:
    """Probability of rain; historical days have no probability, so infer from the amount that fell."""
    if day.precipitation_probability_max is not None:
        return day.precipitation_probability_max
    if day.precipitation_sum is None:
        return 0.0
    return 90.0 if day.precipitation_sum >= 2 else 40.0 if day.precipitation_sum >= 0.5 else 0.0


def is_wet(day: DailyWeather) -> bool:
    return rain_chance(day) >= 50 or (day.precipitation_sum or 0) >= 2


def score_day(day: DailyWeather, activity: str) -> ActivityDay:
    p = ACTIVITIES[activity]
    score = 100.0
    reasons: list[str] = []

    lo, hi = p.temp_range
    t = day.temp_max
    if t is not None:
        # 1°C of slack so a 20.4°C high isn't called "hot" against a 20°C limit.
        if t < lo - 1:
            score -= min(45, (lo - t) * 4)
            reasons.append(f"cool for {p.label.lower()} (high {fmt_temp(t)})")
        elif t > hi + 1:
            score -= min(45, (t - hi) * 4)
            reasons.append(f"hot for {p.label.lower()} (high {fmt_temp(t)})")
        else:
            reasons.append(f"comfortable high of {fmt_temp(t)}")

    chance = rain_chance(day)
    if chance > p.max_rain_chance:
        score -= min(40, (chance - p.max_rain_chance) * 0.8)
        reasons.append(f"{chance:.0f}% chance of rain")
    elif chance <= 10:
        reasons.append("dry")
    if (day.precipitation_sum or 0) >= 5:
        score -= 15

    wind = day.wind_speed_max
    if wind is not None and wind > p.max_wind:
        score -= min(30, (wind - p.max_wind) * 2)
        reasons.append(f"windy (gusts to {wind:.0f} km/h)")

    if day.weather_code in STORM_CODES:
        score -= 40
        reasons.append("thunderstorms possible")
    elif day.weather_code in SNOW_CODES:
        score -= 25
        reasons.append("snow expected")
    elif p.wants_sun and day.weather_code is not None and day.weather_code > 2:
        score -= 10
        reasons.append("not much sun")

    if (day.uv_index_max or 0) >= 8:
        score -= 5
        reasons.append("very high UV - bring sunscreen")

    final = int(max(0, min(100, round(score))))
    rating = "Great" if final >= 80 else "Good" if final >= 60 else "Fair" if final >= 40 else "Poor"
    return ActivityDay(date=day.date, score=final, rating=rating, reasons=reasons)


def rank_activity_days(days: list[DailyWeather], activity: str) -> ActivityResponse:
    scored = [score_day(d, activity) for d in days]
    best = max(scored, key=lambda s: s.score, default=None)
    return ActivityResponse(activity=activity, best=best, days=scored)


def compare_to_normals(day: date, normals: ClimateNormals, forecast_high: float | None) -> NormalsResponse:
    delta = None
    label = f"Typical high for this date is {fmt_temp(normals.normal_high)}."
    if forecast_high is not None:
        delta = round(forecast_high - normals.normal_high, 1)
        z = delta / normals.high_stdev if normals.high_stdev else 0
        if abs(delta) < 1.5:
            label = "About normal for this time of year."
        else:
            direction = "warmer" if delta > 0 else "cooler"
            strength = "Much " if abs(z) >= 1.5 else ""
            label = f"{strength}{direction} than normal - {abs(delta):.0f}°C ({abs(delta) * 9 / 5:.0f}°F) {'above' if delta > 0 else 'below'} the {normals.years}-year average."
            label = label[0].upper() + label[1:]
    return NormalsResponse(
        date=day,
        years=normals.years,
        normal_high=normals.normal_high,
        normal_low=normals.normal_low,
        wet_day_percent=normals.wet_day_percent,
        forecast_high=forecast_high,
        delta=delta,
        label=label,
    )


def briefing_bullets(location_name: str, days: list[DailyWeather], activity: str | None, today: date | None = None) -> list[str]:
    """Plain-language packing/planning tips derived only from the stored data."""
    if not days:
        return ["No weather data is stored for this trip yet. Try refreshing it."]
    today = today or date.today()
    past = all(d.date < today for d in days)
    bullets: list[str] = []

    highs = [d.temp_max for d in days if d.temp_max is not None]
    lows = [d.temp_min for d in days if d.temp_min is not None]
    verb = "were" if past else "range"
    if highs and lows:
        bullets.append(
            f"{'Looking back: ' if past else ''}Highs {verb} {fmt_temp(min(highs))} to {fmt_temp(max(highs))} in {location_name}, "
            f"with lows down to {fmt_temp(min(lows))}."
        )

    wet = [d for d in days if is_wet(d)]
    if wet:
        names = ", ".join(weekday(d.date) for d in wet[:5]) + ("…" if len(wet) > 5 else "")
        bullets.append(f"{'It rained' if past else 'Rain likely'} on {len(wet)} of {len(days)} days ({names}). {'' if past else 'Pack a rain jacket or umbrella.'}".strip())
    else:
        bullets.append("Dry all trip." if past else "Looks mostly dry - no rain gear needed.")

    if any(d.weather_code in SNOW_CODES for d in days):
        bullets.append("Snow is in the picture - bring waterproof boots and check road conditions.")
    if any(d.weather_code in STORM_CODES for d in days):
        bullets.append("Thunderstorms possible - plan indoor backups for outdoor activities.")
    if lows and min(lows) < 5:
        bullets.append(f"Cold nights (down to {fmt_temp(min(lows))}) - pack warm layers.")
    if highs and max(highs) > 30:
        bullets.append(f"Hot days (up to {fmt_temp(max(highs))}) - stay hydrated and plan outdoor time for mornings.")
    windy = [d for d in days if (d.wind_speed_max or 0) >= 40]
    if windy:
        bullets.append(f"Strong wind on {', '.join(weekday(d.date) for d in windy[:3])} (40+ km/h).")
    if any((d.uv_index_max or 0) >= 7 for d in days):
        bullets.append("High UV expected - sunscreen and a hat.")

    if activity and activity in ACTIVITIES and not past:
        ranked = rank_activity_days([d for d in days if d.date >= today], activity)
        if ranked.best:
            bullets.append(
                f"Best day for {ACTIVITIES[activity].label.lower()}: {weekday(ranked.best.date)} "
                f"({ranked.best.rating.lower()}, score {ranked.best.score}/100)."
            )
    return bullets
