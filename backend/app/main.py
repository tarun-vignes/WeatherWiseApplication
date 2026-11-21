import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import llm
from app.config import CORS_ORIGINS
from app.db import init_db
from app.routers import ask, trips, weather
from app.validation import ValidationProblem
from app.weather_client import LocationNotFound, WeatherServiceError

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Weather Trip Planner API",
    description="Live weather, 5-day forecasts, saved trips with stored weather (CRUD), exports and insights.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(RequestValidationError)
async def _request_validation(_req: Request, exc: RequestValidationError):
    # Flatten pydantic's error list into one readable message for the UI, keeping the details too.
    messages = []
    for err in exc.errors():
        msg = str(err.get("msg", "")).removeprefix("Value error, ")
        field = ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query"))
        messages.append(f"{field}: {msg}" if field and err.get("type") != "value_error" else msg)
    return JSONResponse(status_code=422, content={"detail": " ".join(messages), "errors": jsonable_encoder(exc.errors())})


@app.exception_handler(ValidationProblem)
async def _validation_problem(_req: Request, exc: ValidationProblem):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(LocationNotFound)
async def _location_not_found(_req: Request, exc: LocationNotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(WeatherServiceError)
async def _weather_service_error(_req: Request, exc: WeatherServiceError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "llm": llm.status()}


app.include_router(weather.router)
app.include_router(trips.router)
app.include_router(ask.router)
