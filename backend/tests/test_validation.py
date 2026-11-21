from datetime import date, timedelta

import pytest

from app.validation import (
    ValidationProblem,
    parse_coordinates,
    validate_date_range,
    validate_location_query,
)

TODAY = date(2026, 11, 20)


def test_valid_future_range():
    validate_date_range(TODAY, TODAY + timedelta(days=5), today=TODAY)


def test_valid_historical_range():
    validate_date_range(date(2019, 7, 1), date(2019, 7, 10), today=TODAY)


@pytest.mark.parametrize(
    "start,end,message",
    [
        (TODAY + timedelta(days=3), TODAY, "on or after the start"),
        (date(1939, 12, 30), date(1940, 1, 2), "1940"),
        (TODAY, TODAY + timedelta(days=16), "at most 15 days"),
        (date(2020, 1, 1), date(2020, 3, 1), "maximum is 31"),
    ],
)
def test_invalid_ranges(start, end, message):
    with pytest.raises(ValidationProblem, match=message):
        validate_date_range(start, end, today=TODAY)


def test_parse_coordinates():
    assert parse_coordinates("41.88, -87.63") == (41.88, -87.63)
    assert parse_coordinates("Chicago") is None
    with pytest.raises(ValidationProblem):
        parse_coordinates("95, 10")


def test_location_query():
    assert validate_location_query("  New   York ") == "New York"
    with pytest.raises(ValidationProblem):
        validate_location_query("x")


def test_uk_postcode_pattern():
    from app.weather_client import _UK_POSTCODE_RE

    assert _UK_POSTCODE_RE.match("SW1A 1AA").group(1) == "SW1A"
    assert _UK_POSTCODE_RE.match("m1 1ae").group(1) == "m1"
    assert _UK_POSTCODE_RE.match("10001") is None
    assert _UK_POSTCODE_RE.match("New York") is None
