"""Export stored trips as CSV, JSON or Markdown."""

import csv
import io
import json
from datetime import datetime, timezone
from typing import Literal

from app.models import Trip
from app.schemas import TripOut
from app.weather_codes import describe

ExportFormat = Literal["csv", "json", "md"]

MEDIA_TYPES: dict[str, str] = {
    "csv": "text/csv",
    "json": "application/json",
    "md": "text/markdown",
}

CSV_COLUMNS = [
    "trip_id", "trip_name", "location", "latitude", "longitude", "date", "source", "conditions",
    "temp_max_c", "temp_min_c", "precipitation_mm", "precipitation_probability_pct", "wind_speed_max_kmh",
    "uv_index_max", "activity", "notes",
]


# Spreadsheet apps run cells starting with these characters as formulas (CSV/formula injection).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_text(value: str | None) -> str:
    """Neutralize user-entered text for CSV by prefixing a quote; numbers are written untouched."""
    value = value or ""
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


def to_csv(trips: list[Trip]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for t in trips:
        for d in t.days or [None]:
            writer.writerow([
                t.id, _safe_text(t.name), _safe_text(t.location_name), t.latitude, t.longitude,
                d.date.isoformat() if d else "", d.source if d else "", describe(d.weather_code) if d else "",
                d.temp_max if d else "", d.temp_min if d else "", d.precipitation_sum if d else "",
                d.precipitation_probability_max if d else "", d.wind_speed_max if d else "",
                d.uv_index_max if d else "", t.activity or "", _safe_text(t.notes),
            ])
    return buf.getvalue()


def to_json(trips: list[Trip]) -> str:
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "units": {"temperature": "°C", "precipitation": "mm", "wind_speed": "km/h"},
        "trips": [TripOut.model_validate(t).model_dump(mode="json") for t in trips],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _cell(value: float | None, suffix: str = "") -> str:
    return "–" if value is None else f"{value:g}{suffix}"


def to_markdown(trips: list[Trip]) -> str:
    lines = [f"# Weather export", "", f"_Exported {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC_", ""]
    for t in trips:
        lines += [
            f"## {t.name}",
            "",
            f"**Location:** {t.location_name} ({t.latitude:.3f}, {t.longitude:.3f})  ",
            f"**Dates:** {t.start_date.isoformat()} to {t.end_date.isoformat()}  ",
        ]
        if t.activity:
            lines.append(f"**Activity:** {t.activity}  ")
        if t.notes:
            lines.append(f"**Notes:** {t.notes}  ")
        lines += [
            "",
            "| Date | Conditions | High | Low | Precip | Rain chance | Wind | Source |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for d in t.days:
            lines.append(
                f"| {d.date.isoformat()} | {describe(d.weather_code)} | {_cell(d.temp_max, '°C')} | {_cell(d.temp_min, '°C')} "
                f"| {_cell(d.precipitation_sum, ' mm')} | {_cell(d.precipitation_probability_max, '%')} "
                f"| {_cell(d.wind_speed_max, ' km/h')} | {d.source} |"
            )
        lines.append("")
    return "\n".join(lines)


def render(trips: list[Trip], fmt: ExportFormat) -> str:
    return {"csv": to_csv, "json": to_json, "md": to_markdown}[fmt](trips)
