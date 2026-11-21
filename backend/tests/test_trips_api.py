"""End-to-end CRUD tests with the weather service stubbed out (no network)."""

import csv
import io
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import trips as trips_router
from app.schemas import DailyWeather, Location
from app.weather_client import LocationNotFound, WeatherServiceError

TODAY = date.today()


async def fake_resolve(query: str) -> Location:
    if query == "Nowhere":
        raise LocationNotFound("Could not find a location matching 'Nowhere'.")
    return Location(name=query, label=f"{query}, Testland", latitude=10.0, longitude=20.0, timezone="UTC")


async def fake_range(lat, lon, start, end):
    n = (end - start).days + 1
    return [
        DailyWeather(date=start + timedelta(days=i), temp_max=20 + i, temp_min=10, precipitation_sum=0,
                     precipitation_probability_max=10, wind_speed_max=12, weather_code=1, uv_index_max=4)
        for i in range(n)
    ]


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(trips_router, "resolve_location", fake_resolve)
    monkeypatch.setattr(trips_router, "get_daily_range", fake_range)
    with TestClient(app) as c:
        yield c


def _create(client, **overrides):
    body = {"location": "Austin", "start_date": str(TODAY), "end_date": str(TODAY + timedelta(days=2))} | overrides
    return client.post("/api/trips", json=body)


def test_crud_lifecycle(client):
    created = _create(client, activity="running", notes="race weekend")
    assert created.status_code == 201
    trip = created.json()
    assert trip["name"] == "Austin trip"
    assert len(trip["days"]) == 3

    assert client.get(f"/api/trips/{trip['id']}").json()["notes"] == "race weekend"
    assert any(t["id"] == trip["id"] for t in client.get("/api/trips").json())

    updated = client.patch(f"/api/trips/{trip['id']}", json={"end_date": str(TODAY + timedelta(days=4)), "name": "Race"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Race"
    assert len(updated.json()["days"]) == 5

    briefing = client.get(f"/api/trips/{trip['id']}/briefing").json()
    assert briefing["source"] == "rules"
    assert "Best day for running" in briefing["text"]

    assert client.delete(f"/api/trips/{trip['id']}").status_code == 204
    assert client.get(f"/api/trips/{trip['id']}").status_code == 404


def test_validation_errors(client):
    bad_order = _create(client, start_date=str(TODAY + timedelta(days=3)), end_date=str(TODAY))
    assert bad_order.status_code == 422
    assert "on or after the start date" in bad_order.json()["detail"]

    assert _create(client, location="Nowhere").status_code == 404
    assert client.post("/api/trips", json={"start_date": str(TODAY), "end_date": str(TODAY)}).status_code == 422

    trip = _create(client).json()
    bad_update = client.patch(f"/api/trips/{trip['id']}", json={"end_date": str(TODAY - timedelta(days=1))})
    assert bad_update.status_code == 422


def test_exports(client):
    trip = _create(client, name="Export me").json()
    exported = client.get("/api/trips/export?format=csv")
    assert exported.status_code == 200
    assert exported.text.startswith("trip_id,trip_name")
    assert "Export me" in exported.text
    assert "attachment" in exported.headers["content-disposition"]

    data = client.get(f"/api/trips/{trip['id']}/export?format=json").json()
    assert data["trips"][0]["name"] == "Export me"

    md = client.get(f"/api/trips/{trip['id']}/export?format=md")
    assert "## Export me" in md.text
    assert client.get("/api/trips/export?format=xml").status_code == 422


# --- Regression tests for review findings -------------------------------------

def test_null_dates_rejected_and_omitted_dates_kept(client):
    trip = _create(client).json()

    for field in ("start_date", "end_date"):
        resp = client.patch(f"/api/trips/{trip['id']}", json={field: None})
        assert resp.status_code == 422, resp.text
        assert field in resp.json()["detail"] and "omit" in resp.json()["detail"]

    resp = client.patch(f"/api/trips/{trip['id']}", json={"name": None})
    assert resp.status_code == 422

    # Omitting the dates keeps the stored ones.
    kept = client.patch(f"/api/trips/{trip['id']}", json={"notes": "only notes"}).json()
    assert (kept["start_date"], kept["end_date"]) == (trip["start_date"], trip["end_date"])
    assert kept["days"] == trip["days"]


async def _failing_range(lat, lon, start, end):
    raise WeatherServiceError("Weather service error (503)")


async def _empty_range(lat, lon, start, end):
    return []


async def _missing_last_day(lat, lon, start, end):
    return (await fake_range(lat, lon, start, end))[:-1]


async def _all_null_range(lat, lon, start, end):
    n = (end - start).days + 1
    return [DailyWeather(date=start + timedelta(days=i)) for i in range(n)]


async def _last_day_empty(lat, lon, start, end):
    days = await fake_range(lat, lon, start, end)
    days[-1] = DailyWeather(date=days[-1].date, source=days[-1].source)
    return days


async def _last_day_missing_low(lat, lon, start, end):
    days = await fake_range(lat, lon, start, end)
    days[-1].temp_min = None
    return days


@pytest.mark.parametrize(
    "bad_fetch", [_failing_range, _empty_range, _missing_last_day, _all_null_range, _last_day_empty, _last_day_missing_low]
)
def test_failed_refresh_keeps_saved_weather(client, monkeypatch, bad_fetch):
    trip = _create(client).json()
    monkeypatch.setattr(trips_router, "get_daily_range", bad_fetch)

    resp = client.post(f"/api/trips/{trip['id']}/refresh")
    assert resp.status_code == 502, resp.text

    after = client.get(f"/api/trips/{trip['id']}").json()
    assert after["days"] == trip["days"]
    assert after["weather_updated_at"] == trip["weather_updated_at"]


def test_failed_refetch_on_update_keeps_trip_unchanged(client, monkeypatch):
    trip = _create(client).json()
    monkeypatch.setattr(trips_router, "get_daily_range", _missing_last_day)

    resp = client.patch(f"/api/trips/{trip['id']}", json={"end_date": str(TODAY + timedelta(days=5)), "name": "Changed"})
    assert resp.status_code == 502

    after = client.get(f"/api/trips/{trip['id']}").json()
    assert after["name"] == trip["name"]
    assert after["end_date"] == trip["end_date"]
    assert after["days"] == trip["days"]


def test_failed_fetch_on_create_saves_nothing(client, monkeypatch):
    before = len(client.get("/api/trips").json())
    monkeypatch.setattr(trips_router, "get_daily_range", _empty_range)
    assert _create(client).status_code == 502
    assert len(client.get("/api/trips").json()) == before


def test_csv_export_neutralizes_formulas(client, monkeypatch):
    async def cold_range(lat, lon, start, end):
        return [DailyWeather(date=start, temp_max=-2.5, temp_min=-8.0, weather_code=71)]

    monkeypatch.setattr(trips_router, "get_daily_range", cold_range)
    trip = _create(
        client,
        location="@SUM(1+1)",
        name='=HYPERLINK("http://evil.example","click")',
        notes="+cmd|' /C calc'!A0",
        end_date=str(TODAY),
    ).json()

    rows = list(csv.reader(io.StringIO(client.get(f"/api/trips/{trip['id']}/export?format=csv").text)))
    header, row = rows[0], rows[1]
    cell = dict(zip(header, row))
    assert cell["trip_name"] == "'" + '=HYPERLINK("http://evil.example","click")'
    assert cell["location"] == "'@SUM(1+1), Testland"
    assert cell["notes"] == "'+cmd|' /C calc'!A0"
    # Numeric weather values (including negatives) are left as numbers.
    assert cell["temp_max_c"] == "-2.5"
    assert cell["temp_min_c"] == "-8.0"
    assert cell["latitude"] == "10.0"


def test_partially_empty_refresh_keeps_whole_snapshot(client, monkeypatch):
    trip = _create(client).json()
    assert trip["days"][-1]["temp_max"] == 22  # the value the bad refresh would have wiped
    monkeypatch.setattr(trips_router, "get_daily_range", _last_day_empty)

    resp = client.post(f"/api/trips/{trip['id']}/refresh")
    assert resp.status_code == 502
    assert trip["days"][-1]["date"] in resp.json()["detail"]

    after = client.get(f"/api/trips/{trip['id']}").json()
    assert after["days"] == trip["days"]
    assert after["days"][-1]["temp_max"] == 22


def test_optional_fields_may_be_null(client, monkeypatch):
    async def no_uv_or_rain_chance(lat, lon, start, end):
        days = await fake_range(lat, lon, start, end)
        for d in days:  # historical days have no UV or rain probability
            d.uv_index_max = d.precipitation_probability_max = d.weather_code = None
        return days

    trip = _create(client).json()
    monkeypatch.setattr(trips_router, "get_daily_range", no_uv_or_rain_chance)
    refreshed = client.post(f"/api/trips/{trip['id']}/refresh")
    assert refreshed.status_code == 200
    assert all(d["uv_index_max"] is None for d in refreshed.json()["days"])
