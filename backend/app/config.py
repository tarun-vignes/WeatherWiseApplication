import os
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()

def database_url(value: str | None, on_render: bool) -> str:
    """Use psycopg 3 with Render's standard PostgreSQL URL."""
    value = (value or "").strip()
    if not value:
        if on_render:
            raise RuntimeError("DATABASE_URL must point to PostgreSQL on Render.")
        return "sqlite:///./weather.db"
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://"):]
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://"):]
    if on_render and not value.startswith("postgresql+psycopg://"):
        raise RuntimeError("DATABASE_URL must use PostgreSQL with psycopg on Render.")
    return value


def cors_origins(value: str | None, on_render: bool) -> list[str]:
    """Require explicit HTTPS browser origins in the hosted environment."""
    if value is None:
        value = "" if on_render else "http://localhost:3000"
    origins = [origin.strip() for origin in value.split(",") if origin.strip()]
    if on_render:
        if not origins:
            raise RuntimeError("Set CORS_ORIGINS to the deployed frontend HTTPS origin.")
        for origin in origins:
            parsed = urlsplit(origin)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                    or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
                raise RuntimeError("CORS_ORIGINS must contain exact public HTTPS origins without paths or trailing slashes.")
    return origins


ON_RENDER = os.getenv("RENDER", "").lower() == "true"
DATABASE_URL = database_url(os.getenv("DATABASE_URL"), ON_RENDER)
CORS_ORIGINS = cors_origins(os.getenv("CORS_ORIGINS"), ON_RENDER)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").strip().lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip()

HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "15"))
