# Weather Trip Planner

**By Tarun Vigneswaran** · Built for the PM Accelerator frontend and backend assessment

**[Try the live app](https://weatherwise-ui-tarun.onrender.com/)** · Hosted on Render. The first visit may take a minute while the free services wake up.

Planning a trip is easier when you know what the weather might bring. Weather Trip Planner lets you look up a place, check the forecast, and save a trip with its weather information so you can come back to it later.

The weather comes from [Open-Meteo](https://open-meteo.com/), rather than a fixed set of example data. You don't need a weather API key to run the app.

## What you can do

- **Check the weather:** Search for a city, postal code, or coordinates. You can also use your current location if you give your browser permission.
- **Look ahead:** See current conditions and the next five days, with a choice of Celsius or Fahrenheit.
- **Plan and revisit a trip:** Save a place and date range, then find, edit, refresh, or delete it later. When the place or dates change, the app fetches fresh weather before saving.
- **Take the data with you:** Download saved trips as CSV, JSON, or Markdown.
- **Make plans:** See a weather briefing, compare days for an outdoor activity, and check how temperatures compare with historical averages.
- **Ask a question:** Get a rule-based weather answer. An optional AI provider can enhance responses, but it isn't required to use the app.

The interface works across screen sizes and includes an About PM Accelerator section. If a search or request fails, the app shows a message instead of presenting made-up weather.

## Screenshots and demo

![Weather screen](docs/screenshots/weather.jpg)

![Saved trips screen](docs/screenshots/trips.jpg)

A [recorded demo](docs/demo/weather-trip-planner-demo.mp4) and its [captions](docs/demo/weather-trip-planner-demo.srt) are included in the repository. GitHub may ask you to download the video because of its size. For an assessment submission, upload the video to a service that provides a viewable link and check that someone without your account can open it.

To try the same flow yourself, search for a place, look at the forecast, save a trip, and then edit or export it from the Saved trips tab.

## How it works

The screen you use is built with Next.js, React, and TypeScript. It talks to a Python FastAPI backend, which checks the request, gets weather from Open-Meteo, and saves trips in a database. SQLite is used by default; PostgreSQL can also be configured. SQLAlchemy manages database access, Pydantic validates input, and HTTPX handles external requests. Forecasts are cached for ten minutes; location searches and climate normals are cached for 24 hours.

The project covers **both** the frontend and backend portions of the assessment. The sections below are for anyone who wants to run the code or explore the API.

```text
frontend/app/          Next.js pages and styles
frontend/components/   Search, weather, trips, and question UI
frontend/lib/          API client and formatting helpers
backend/app/           FastAPI routes, validation, weather, database, and insights
backend/tests/         Backend tests
docs/                  Existing screenshots and demo video
```

## Requirements

- Node.js 20.9 or later (Node 22 recommended) and npm.
- Python 3.10 or later and pip.
- Internet access for Open-Meteo at runtime and Google Fonts during the Next.js build.
- Browser geolocation requires a secure context such as `localhost` and user permission.

## Installation and startup

Run the two services in separate terminals from the repository root. On Windows PowerShell:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

If PowerShell blocks virtual environment activation, use Command Prompt with `.venv\Scripts\activate.bat`. On macOS/Linux use `source .venv/bin/activate` and `cp .env.example .env`.

If Windows application control blocks SQLAlchemy's compiled extension, a pure-Python build can be installed in the activated environment with `$env:DISABLE_SQLALCHEMY_CEXT='1'; python -m pip install --no-binary sqlalchemy -r requirements.txt`.

In another terminal:

```powershell
cd frontend
npm ci
Copy-Item .env.local.example .env.local
npm run dev
```

Use `npm.cmd` instead of `npm` if PowerShell blocks `npm.ps1`; on macOS/Linux use `cp` instead of `Copy-Item`. Visit [http://localhost:3000](http://localhost:3000). The API health check is at [http://localhost:8000/api/health](http://localhost:8000/api/health), and interactive API documentation is at [http://localhost:8000/docs](http://localhost:8000/docs).

SQLite creates `backend/weather.db` when the backend starts. To use PostgreSQL, create a database and set `DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/weatherwise` in `backend/.env`. Set `CORS_ORIGINS` to a comma-separated list of frontend origins and `NEXT_PUBLIC_API_URL` to the backend URL if using different hosts. `NEXT_PUBLIC_AUTHOR_NAME` can override the default author credit. Restart services after changing environment variables; public frontend variables are embedded at build time. Do not commit local `.env` files or credentials.

By default `LLM_PROVIDER=none`. Optional providers are `ollama`, `groq`, and `gemini`; set the model, base URL, and API key in `backend/.env` as needed. Cloud providers may require accounts or incur costs. Provider configuration is optional for the main weather and CRUD features.

## Deploy on Render

Create a Render Postgres database and two **Web Services** connected to this repository. These instructions are a deployment plan; replace the example addresses with the actual URLs Render assigns. Render's [web service documentation](https://render.com/docs/web-services) explains port binding, and its [Postgres guide](https://render.com/docs/postgresql-creating-connecting) explains internal database connections.

1. **Create the database.** In the Render dashboard, create a Postgres database in the same region as the backend. Copy its **Internal Database URL** for the backend service; do not put it in the repository or frontend. The application accepts Render's `postgresql://` URL and selects the installed psycopg 3 driver. It creates tables at startup, but does not run migrations or copy data from your local SQLite database.
2. **Create the backend web service.** Connect this GitHub repository and choose the Python runtime. Set the root directory to `backend`, build command to `pip install -r requirements.txt`, start command to `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, and health check path to `/api/health`. Set `DATABASE_URL` to the database's internal URL, `CORS_ORIGINS` to the exact frontend HTTPS origin (for example `https://your-frontend.onrender.com`, without a trailing slash), and optionally `LLM_PROVIDER=none`. Choose a frontend service name first and use its expected URL, then verify the actual URL after creating it. The backend refuses to start on Render without PostgreSQL and an explicit HTTPS CORS origin.
3. **Create the frontend web service.** Connect the same repository, select the Node runtime, and set the root directory to `frontend`, build command to `npm ci && npm run build`, and start command to `npm run start -- --hostname 0.0.0.0`. Set `NODE_VERSION=22.19.0` and set `NEXT_PUBLIC_API_URL` to the **public** backend HTTPS origin (for example `https://your-backend.onrender.com`). The browser must be able to reach this URL; do not use the database's internal URL or `localhost`. Set `NEXT_PUBLIC_AUTHOR_NAME` only if you want to override the default credit. `NEXT_PUBLIC_API_URL` is embedded at build time, so rebuild/redeploy the frontend after changing it. The Render build fails if the URL is missing or points to localhost.
4. **Check the actual URLs.** Render assigns each service its own HTTPS URL. Update backend `CORS_ORIGINS` if the frontend URL differs from the value you entered, and update and rebuild the frontend if the backend URL differs. Keep the two services and database in the same region where practical. Actual URLs are not known until you create the services.
5. **Verify the deployed app.** Open `<backend-url>/api/health` and `/docs`. Open the frontend URL, search for a location, check current conditions and the five-day forecast, and test geolocation after granting browser permission. Create a trip, reload the page, edit it, export CSV/JSON, and delete it; verify it persists across a backend restart. Also check invalid inputs, weather insights, the About panel, and author credit. Use a test trip you are comfortable deleting.

Render's free web services spin down after inactivity, so the first request can be slow. Their filesystems are ephemeral, so don't use local SQLite for hosted trip storage. [Render's free Postgres plan expires after 30 days](https://render.com/docs/free); choose a suitable database plan and backup strategy for the time reviewers need access. Public services and a shared, unauthenticated database are suitable for an assessment demo only; do not store private information.

## API overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Backend and optional LLM status |
| GET | `/api/locations/search?q=Boston` | Search locations |
| GET | `/api/weather?q=Boston` | Current conditions and daily forecasts; also accepts `lat` and `lon` |
| GET | `/api/weather/normals?lat=42.36&lon=-71.06` | Compare forecast with climate normals |
| GET | `/api/weather/activity?lat=42.36&lon=-71.06&activity=hiking` | Rank forecast days for an activity |
| POST | `/api/trips` | Create a saved trip and weather snapshot |
| GET | `/api/trips` and `/api/trips/{id}` | List or read saved trips |
| PUT/PATCH | `/api/trips/{id}` | Update a trip; refresh weather when location or dates change |
| DELETE | `/api/trips/{id}` | Delete a trip |
| POST | `/api/trips/{id}/refresh` | Refresh stored weather |
| GET | `/api/trips/export?format=csv` | Export all trips (`csv`, `json`, or `md`) |
| GET | `/api/trips/{id}/export?format=json` | Export one trip |
| GET | `/api/trips/{id}/briefing` | Obtain a trip weather briefing |
| POST | `/api/ask` | Ask a weather question |

Request and response schemas and supported activity values are documented at `/docs`. Date ranges are limited to 31 days, starting no earlier than 1940 and ending no later than 15 days ahead. Availability also depends on Open-Meteo; the application reports unavailable data rather than inventing it.

## Tests and checks

```powershell
cd backend
python -m pytest -q
```

The standard suite uses mocked provider data; live API tests are skipped unless explicitly enabled. To run them with internet access in PowerShell, use `$env:RUN_LIVE_TESTS='1'; python -m pytest -q tests/test_live_api.py`. Live results depend on provider availability and current data. For the frontend:

```powershell
cd frontend
npm run lint
npm run build
```

The build checks TypeScript and production compilation. To run the production frontend after building, use `npm run start`. There are currently no automated frontend interaction tests.

## Limitations

Forecasts are estimates and can change. Search coverage and historical availability depend on upstream providers; some locations may not resolve. Saved trips are shared without user accounts, so authentication and per-user access controls would be needed for a public multi-user deployment. SQLite and automatic table creation are intended for local demonstration; production deployment would also need migrations, appropriate database backups, rate limiting, and a deployment configuration. PostgreSQL and optional LLM providers should be tested in the target environment before deployment.
