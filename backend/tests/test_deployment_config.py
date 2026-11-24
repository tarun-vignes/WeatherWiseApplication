import pytest

from app.config import cors_origins, database_url


def test_local_defaults():
    assert database_url(None, False) == "sqlite:///./weather.db"
    assert cors_origins(None, False) == ["http://localhost:3000"]


@pytest.mark.parametrize("url", ["postgres://user:pass@db/service", "postgresql://user:pass@db/service"])
def test_render_postgres_url_uses_psycopg(url):
    assert database_url(url, True) == "postgresql+psycopg://user:pass@db/service"


@pytest.mark.parametrize("url", [None, "", "sqlite:///weather.db", "postgresql+psycopg2://db/service"])
def test_render_rejects_missing_or_unsupported_database(url):
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        database_url(url, True)


def test_render_accepts_explicit_https_origins():
    assert cors_origins("https://frontend.onrender.com, https://example.com", True) == [
        "https://frontend.onrender.com", "https://example.com"
    ]


@pytest.mark.parametrize("origin", [None, "", "*", "http://localhost:3000", "https://localhost", "https://example.com/", "https://user:pass@example.com"])
def test_render_rejects_invalid_cors_origins(origin):
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        cors_origins(origin, True)
