"""Answer plain-English weather questions ("Will it rain in Austin on Saturday?").

Flow: parse the question -> fetch real data from Open-Meteo -> answer only from that data.
Parsing and answering use the LLM when one is configured, otherwise simple rules.
"""

import json
import re
from datetime import date, timedelta

from app import llm
from app.insights import ACTIVITIES, fmt_temp, is_wet, rain_chance, rank_activity_days, weekday
from app.schemas import AskResponse, DailyWeather, Location
from app.validation import MAX_FORECAST_DAYS_AHEAD, ValidationProblem
from app.weather_client import LocationNotFound, get_daily_range, resolve_location, reverse_geocode

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
# Words that end a location phrase ("rain in Paris on Friday" -> "Paris").
_STOP = r"(?:on|this|next|today|tonight|tomorrow|over|during|for|at|in|by|around|the\s+weekend|weekend|week|" + "|".join(WEEKDAYS) + r")"
_LOCATION_RE = re.compile(rf"\b(?:in|at|near|for)\s+(?!the\b|this\b|next\b)([a-zA-Z][\w .,'-]*?)(?=\s+{_STOP}\b|[?!.]|$)", re.IGNORECASE)


def parse_dates(question: str, today: date) -> tuple[date, date]:
    q = question.lower()
    if m := re.search(r"\b(\d{4}-\d{2}-\d{2})\b", q):
        d = date.fromisoformat(m.group(1))
        return d, d
    if "tomorrow" in q:
        d = today + timedelta(days=1)
        return d, d
    if "today" in q or "tonight" in q or "right now" in q:
        return today, today
    if "weekend" in q:
        sat = today + timedelta(days=(5 - today.weekday()) % 7)
        if "next weekend" in q:
            sat += timedelta(days=7)
        return sat, sat + timedelta(days=1)
    for i, name in enumerate(WEEKDAYS):
        if re.search(rf"\b{name}\b", q):
            d = today + timedelta(days=(i - today.weekday()) % 7)
            if d == today and f"next {name}" in q:
                d += timedelta(days=7)
            return d, d
    if m := re.search(r"next\s+(\d{1,2})\s+days", q):
        n = max(1, min(int(m.group(1)), MAX_FORECAST_DAYS_AHEAD + 1))
        return today, today + timedelta(days=n - 1)
    if "next week" in q:
        start = today + timedelta(days=7 - today.weekday())
        return start, start + timedelta(days=6)
    return today, today + timedelta(days=4)


def parse_location_phrase(question: str) -> str | None:
    """Pick the place out of the question, preferring "in/at/near X" over "for X" ("best day for golf in Austin")."""
    activity_words = set(ACTIVITIES) | {p.label.lower() for p in ACTIVITIES.values()}
    candidates: list[tuple[int, str]] = []
    for match in _LOCATION_RE.finditer(question):
        phrase = match.group(1).strip(" ,.'")
        if len(phrase) < 2 or phrase.lower() in activity_words:
            continue
        preposition = match.group(0).split()[0].lower()
        candidates.append((1 if preposition == "for" else 0, phrase))
    return min(candidates, key=lambda c: c[0])[1] if candidates else None


def _clamp(start: date, end: date, today: date) -> tuple[date, date]:
    latest = today + timedelta(days=MAX_FORECAST_DAYS_AHEAD)
    earliest = today - timedelta(days=60)
    if start > latest:
        raise ValidationProblem(f"I can only forecast up to {MAX_FORECAST_DAYS_AHEAD} days ahead ({latest.isoformat()}).")
    if end < earliest:
        raise ValidationProblem("For dates more than 60 days ago, save a trip with that date range instead.")
    return max(start, earliest), min(end, latest)


def rule_answer(question: str, loc: Location, days: list[DailyWeather]) -> str:
    q = question.lower()
    if not days:
        return f"I couldn't find weather data for {loc.label} on those dates."
    span = weekday(days[0].date) if len(days) == 1 else f"{weekday(days[0].date)} - {weekday(days[-1].date)}"

    for key, profile in ACTIVITIES.items():
        if key in q or profile.label.lower() in q:
            ranked = rank_activity_days(days, key)
            best = ranked.best
            return (
                f"Best day for {profile.label.lower()} in {loc.name} ({span}): {weekday(best.date)} - "
                f"{best.rating.lower()} ({best.score}/100): {', '.join(best.reasons) or 'good conditions'}."
            )

    if any(w in q for w in ("rain", "umbrella", "wet", "shower", "storm")):
        wet = [d for d in days if is_wet(d)]
        if not wet:
            peak = max(days, key=rain_chance)
            return f"Rain looks unlikely in {loc.name} ({span}). Highest chance is {rain_chance(peak):.0f}% on {weekday(peak.date)}."
        details = "; ".join(f"{weekday(d.date)} {rain_chance(d):.0f}% ({d.precipitation_sum or 0:.1f} mm)" for d in wet)
        return f"Yes - rain is likely in {loc.name}: {details}. Bring an umbrella."

    if "snow" in q:
        snowy = [d for d in days if d.description and "snow" in d.description.lower()]
        if snowy:
            return f"Snow is expected in {loc.name} on {', '.join(weekday(d.date) for d in snowy)}."
        return f"No snow in the forecast for {loc.name} ({span})."

    if any(w in q for w in ("warm", "hot", "heat")):
        d = max(days, key=lambda x: x.temp_max if x.temp_max is not None else -999)
        return f"Warmest day in {loc.name} ({span}) is {weekday(d.date)} with a high of {fmt_temp(d.temp_max)}."

    if any(w in q for w in ("cold", "cool", "freez", "jacket", "coat")):
        d = min(days, key=lambda x: x.temp_min if x.temp_min is not None else 999)
        return f"Coldest point in {loc.name} ({span}) is {weekday(d.date)} with a low of {fmt_temp(d.temp_min)}."

    if any(w in q for w in ("wind", "breez", "gust")):
        d = max(days, key=lambda x: x.wind_speed_max or 0)
        return f"Windiest day in {loc.name} ({span}) is {weekday(d.date)} with winds up to {d.wind_speed_max or 0:.0f} km/h."

    if any(w in q for w in ("uv", "sunscreen", "sunburn")):
        d = max(days, key=lambda x: x.uv_index_max or 0)
        return f"Peak UV in {loc.name} ({span}) is {d.uv_index_max or 0:.0f} on {weekday(d.date)}."

    lines = [
        f"{weekday(d.date)}: {d.description.lower()}, {fmt_temp(d.temp_min)} to {fmt_temp(d.temp_max)}, {rain_chance(d):.0f}% rain"
        for d in days
    ]
    return f"Weather in {loc.name}: " + "; ".join(lines) + "."


_PARSE_SYSTEM = (
    "You extract weather query parameters. Reply with JSON only: "
    '{"location": string or null, "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}. '
    "location is the place named in the question (null if none). Resolve relative dates against today's date. "
    "If no date is given use today through today+4 days."
)
_ANSWER_SYSTEM = (
    "You are a concise weather assistant. Answer the user's question in 1-3 sentences using ONLY the JSON weather "
    "data provided (temperatures in °C, also give °F; precipitation in mm; wind in km/h). If the data cannot answer "
    "the question, say so. Do not invent numbers."
)


async def answer_question(question: str, latitude: float | None, longitude: float | None, today: date | None = None) -> AskResponse:
    today = today or date.today()
    start, end = parse_dates(question, today)
    phrase = parse_location_phrase(question)
    source = "rules"

    parsed = await llm.chat_json(_PARSE_SYSTEM, f"Today is {today.isoformat()} ({today:%A}).\nQuestion: {question}")
    if parsed:
        try:
            start = date.fromisoformat(parsed["start_date"])
            end = date.fromisoformat(parsed["end_date"])
            phrase = parsed.get("location") or phrase
            source = "llm"
        except (KeyError, TypeError, ValueError):
            pass
    if end < start:
        start, end = end, start

    if phrase:
        try:
            loc = await resolve_location(phrase)
        except (LocationNotFound, ValidationProblem):
            if latitude is None or longitude is None:
                raise
            loc = await reverse_geocode(latitude, longitude)
    elif latitude is not None and longitude is not None:
        loc = await reverse_geocode(latitude, longitude)
    else:
        return AskResponse(
            answer="Which place? Include a location (e.g. 'in Chicago') or search for a location first.",
            source="rules",
            location=None,
            start_date=None,
            end_date=None,
        )

    start, end = _clamp(start, end, today)
    days = await get_daily_range(loc.latitude, loc.longitude, start, end)

    answer = None
    if llm.enabled():
        data = [d.model_dump(mode="json", exclude={"icon", "weather_code"}) for d in days]
        answer = await llm.chat(_ANSWER_SYSTEM, f"Location: {loc.label}\nData: {json.dumps(data)}\nQuestion: {question}")
    if answer:
        source = "llm"
    else:
        answer = rule_answer(question, loc, days)
        source = "rules"

    return AskResponse(answer=answer, source=source, location=loc, start_date=start, end_date=end, days=days)
