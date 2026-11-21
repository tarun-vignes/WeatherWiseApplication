from datetime import date

from app.ask import parse_dates, parse_location_phrase, rule_answer
from app.insights import briefing_bullets, compare_to_normals, rank_activity_days, score_day
from app.schemas import DailyWeather, Location
from app.weather_client import ClimateNormals

FRIDAY = date(2026, 11, 20)


def day(d: int, hi=18.0, lo=8.0, rain=0.0, prob=5.0, wind=10.0, code=1, uv=3.0) -> DailyWeather:
    return DailyWeather(
        date=date(2026, 11, d), temp_max=hi, temp_min=lo, precipitation_sum=rain,
        precipitation_probability_max=prob, wind_speed_max=wind, weather_code=code, uv_index_max=uv,
    )


def test_perfect_running_day_scores_high():
    assert score_day(day(21), "running").score >= 90


def test_storm_and_rain_score_low():
    result = score_day(day(21, rain=12, prob=90, code=95), "running")
    assert result.score < 40
    assert any("thunderstorm" in r for r in result.reasons)


def test_best_day_is_dry_one():
    ranked = rank_activity_days([day(21, prob=80, rain=6, code=63), day(22)], "hiking")
    assert ranked.best.date == date(2026, 11, 22)


def test_briefing_mentions_rain_and_cold():
    bullets = briefing_bullets("Denver", [day(21, lo=-3, prob=80, rain=5, code=63), day(22)], "running", today=FRIDAY)
    text = " ".join(bullets)
    assert "Rain likely on 1 of 2 days" in text
    assert "Cold nights" in text
    assert "Best day for running" in text


def test_normals_comparison():
    normals = ClimateNormals(years=30, normal_high=7.0, normal_low=1.0, high_stdev=4.0, wet_day_percent=30)
    assert "warmer" in compare_to_normals(FRIDAY, normals, 19.0).label
    assert compare_to_normals(FRIDAY, normals, 7.5).label.startswith("About normal")


def test_parse_dates():
    assert parse_dates("rain tomorrow?", FRIDAY) == (date(2026, 11, 21), date(2026, 11, 21))
    assert parse_dates("this weekend", FRIDAY) == (date(2026, 11, 21), date(2026, 11, 22))
    assert parse_dates("on Monday", FRIDAY) == (date(2026, 11, 23), date(2026, 11, 23))
    assert parse_dates("next 3 days", FRIDAY) == (FRIDAY, date(2026, 11, 22))
    assert parse_dates("weather?", FRIDAY) == (FRIDAY, date(2026, 11, 24))


def test_parse_location_phrase():
    assert parse_location_phrase("best day for golf in san diego") == "san diego"
    assert parse_location_phrase("Will it rain in Seattle this weekend?") == "Seattle"
    assert parse_location_phrase("Will it rain?") is None


def test_rule_answer_rain():
    loc = Location(name="Seattle", label="Seattle, WA", latitude=47.6, longitude=-122.3)
    answer = rule_answer("will it rain?", loc, [day(21, prob=85, rain=8, code=63), day(22)])
    assert answer.startswith("Yes")
