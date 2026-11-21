"""Live tests against the real Open-Meteo / BigDataCloud APIs (no mocks).

Skipped by default so the regular suite runs offline. Run with:  RUN_LIVE_TESTS=1 pytest -q tests/test_live_api.py
"""

import os
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.weather_client import FORECAST_PAST_DAYS

pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="set RUN_LIVE_TESTS=1 to call the real APIs")

TODAY = date.today()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _ok(resp, status: int = 200):
    """Check the status first, so a network failure reads as an HTTP error rather than a confusing TypeError."""
    assert resp.status_code == status, f"{resp.request.method} {resp.request.url.path} -> {resp.status_code}: {resp.text[:300]}"
    return resp.json()


def _dates(days: list[dict]) -> list[str]:
    return [d["date"] for d in days]


def _expected(start: date, end: date) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


@pytest.mark.parametrize(
    ("query", "expect_in_label"),
    [("Austin", "Texas"), ("Paris", "France"), ("10001", "United States"), ("SW1A 1AA", "United Kingdom")],
)
def test_search_by_city_and_postal_code(client, query, expect_in_label):
    results = _ok(client.get("/api/locations/search", params={"q": query}))
    assert results, f"no results for {query}"
    assert any(expect_in_label in r["label"] for r in results), [r["label"] for r in results]


def test_search_by_coordinates(client):
    results = _ok(client.get("/api/locations/search", params={"q": "48.8566, 2.3522"}))
    assert len(results) == 1
    assert results[0]["latitude"] == pytest.approx(48.8566)
    assert "Paris" in results[0]["label"] or "France" in results[0]["label"]


def test_unknown_place_is_404(client):
    resp = client.get("/api/weather", params={"q": "Qxzqxzqxz Nowhereville"})
    assert resp.status_code == 404


def test_current_weather_and_five_day_forecast(client):
    data = _ok(client.get("/api/weather", params={"q": "Austin"}))
    assert data["current"]["temperature"] is not None
    assert len(data["daily"]) == 6
    assert data["daily"][0]["date"] == TODAY.isoformat() or abs(
        (date.fromisoformat(data["daily"][0]["date"]) - TODAY).days) <= 1  # local date at the location


def _trip(client, start: date, end: date, location="Chicago"):
    resp = client.post("/api/trips", json={"location": location, "start_date": str(start), "end_date": str(end)})
    return _ok(resp, 201)


def test_historical_range_from_archive(client):
    start, end = date(2019, 7, 1), date(2019, 7, 5)
    trip = _trip(client, start, end)
    try:
        assert _dates(trip["days"]) == _expected(start, end)
        assert {d["source"] for d in trip["days"]} == {"historical"}
        assert all(d["temp_max"] is not None for d in trip["days"])
    finally:
        client.delete(f"/api/trips/{trip['id']}")


def test_future_range_from_forecast(client):
    start, end = TODAY + timedelta(days=10), TODAY + timedelta(days=15)
    trip = _trip(client, start, end)
    try:
        assert _dates(trip["days"]) == _expected(start, end)
        assert {d["source"] for d in trip["days"]} == {"forecast"}
    finally:
        client.delete(f"/api/trips/{trip['id']}")


def test_range_crossing_today(client):
    start, end = TODAY - timedelta(days=3), TODAY + timedelta(days=3)
    trip = _trip(client, start, end)
    try:
        assert _dates(trip["days"]) == _expected(start, end)
        sources = {d["date"]: d["source"] for d in trip["days"]}
        assert sources[start.isoformat()] == "historical"
        assert sources[end.isoformat()] == "forecast"
    finally:
        client.delete(f"/api/trips/{trip['id']}")


def test_range_crossing_archive_forecast_api_boundary(client):
    # Dates older than FORECAST_PAST_DAYS come from the archive API, newer ones from the forecast API.
    cutoff = TODAY - timedelta(days=FORECAST_PAST_DAYS)
    start, end = cutoff - timedelta(days=3), cutoff + timedelta(days=3)
    trip = _trip(client, start, end)
    try:
        assert _dates(trip["days"]) == _expected(start, end)
        assert {d["source"] for d in trip["days"]} == {"historical"}
        assert all(d["temp_max"] is not None for d in trip["days"])
    finally:
        client.delete(f"/api/trips/{trip['id']}")


def test_trip_by_coordinates_and_refresh(client):
    resp = client.post("/api/trips", json={"latitude": 51.5072, "longitude": -0.1276, "location_label": "London",
                                           "start_date": str(TODAY), "end_date": str(TODAY + timedelta(days=2))})
    trip = _ok(resp, 201)
    try:
        assert trip["location_name"] == "London"
        refreshed = _ok(client.post(f"/api/trips/{trip['id']}/refresh"))
        assert _dates(refreshed["days"]) == _dates(trip["days"])
        assert refreshed["weather_updated_at"] >= trip["weather_updated_at"]
    finally:
        client.delete(f"/api/trips/{trip['id']}")
