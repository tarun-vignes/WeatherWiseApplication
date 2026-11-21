"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { api, type Location, type WeatherResponse } from "@/lib/api";
import type { Unit } from "@/lib/format";
import AboutModal from "./AboutModal";
import AskPanel from "./AskPanel";
import SearchBar from "./SearchBar";
import TripsPanel, { type TripDraft } from "./TripsPanel";
import WeatherView from "./WeatherView";

type Tab = "weather" | "trips" | "ask";

// Set NEXT_PUBLIC_AUTHOR_NAME in .env.local; the credit line is hidden until it is set.
const AUTHOR = process.env.NEXT_PUBLIC_AUTHOR_NAME?.trim();

// The °C/°F preference lives in localStorage; read it as an external store so SSR and hydration agree.
const UNIT_EVENT = "unit-change";
function subscribeUnit(cb: () => void) {
  window.addEventListener(UNIT_EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(UNIT_EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}
function readUnit(): Unit {
  try {
    return localStorage.getItem("unit") === "F" ? "F" : "C";
  } catch {
    return "C";
  }
}

export default function WeatherApp() {
  const [tab, setTab] = useState<Tab>("weather");
  const unit = useSyncExternalStore(subscribeUnit, readUnit, () => "C" as Unit);
  const [weather, setWeather] = useState<WeatherResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<TripDraft | null>(null);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [llmEnabled, setLlmEnabled] = useState(false);

  useEffect(() => {
    api.health().then((h) => setLlmEnabled(h.llm.enabled)).catch(() => {});
  }, []);

  function changeUnit(u: Unit) {
    try {
      localStorage.setItem("unit", u);
    } catch {
      /* storage unavailable: preference just won't persist */
    }
    window.dispatchEvent(new Event(UNIT_EVENT));
  }

  // Only the most recent search may update the screen: starting a new one aborts the previous request, and a
  // response that arrives after being superseded is ignored, so a slow earlier search can't overwrite a later one.
  const inFlight = useRef<AbortController | null>(null);
  const load = useCallback(async (fetcher: (signal: AbortSignal) => Promise<WeatherResponse>) => {
    inFlight.current?.abort();
    const request = new AbortController();
    inFlight.current = request;
    setLoading(true);
    setError("");
    try {
      const data = await fetcher(request.signal);
      if (request.signal.aborted) return;
      setWeather(data);
      setTab("weather");
    } catch (e) {
      if (!request.signal.aborted) setError((e as Error).message);
    } finally {
      if (inFlight.current === request) setLoading(false);
    }
  }, []);

  const onSelect = (loc: Location) =>
    load((signal) => api.weatherByCoords(loc.latitude, loc.longitude, signal).then((w) => ({ ...w, location: loc })));
  const clearDraft = useCallback(() => setDraft(null), []);

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>⛅ Weather Trip Planner</h1>
          {AUTHOR && (
            <p className="muted small">
              Built by <strong>{AUTHOR}</strong>
            </p>
          )}
        </div>
        <div className="row">
          <div className="toggle" role="group" aria-label="Units">
            <button className={unit === "C" ? "on" : ""} onClick={() => changeUnit("C")}>
              °C
            </button>
            <button className={unit === "F" ? "on" : ""} onClick={() => changeUnit("F")}>
              °F
            </button>
          </div>
          <button className="btn" onClick={() => setAboutOpen(true)}>
            ℹ️ About PM Accelerator
          </button>
        </div>
      </header>

      <SearchBar
        loading={loading}
        onSearch={(q) => load((signal) => api.weatherByQuery(q, signal))}
        onSelect={onSelect}
        onCoords={(lat, lon) => load((signal) => api.weatherByCoords(lat, lon, signal))}
        onError={setError}
      />
      {error && (
        <p className="error banner" role="alert">
          {error}
        </p>
      )}

      <nav className="tabs" role="tablist">
        {(
          [
            ["weather", "Weather"],
            ["trips", "Saved trips"],
            ["ask", "Ask"],
          ] as const
        ).map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "on" : ""} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </nav>

      <main>
        {tab === "weather" &&
          (weather ? (
            <WeatherView
              data={weather}
              unit={unit}
              onSaveTrip={() => {
                setDraft({ location: weather.location.label, latitude: weather.location.latitude, longitude: weather.location.longitude });
                setTab("trips");
              }}
            />
          ) : (
            <section className="card empty">
              <p className="big-icon">🌍</p>
              <p>Search for a city, postal code or coordinates, or use your current location.</p>
            </section>
          ))}
        {tab === "trips" && <TripsPanel unit={unit} draft={draft} onDraftUsed={clearDraft} />}
        {tab === "ask" && <AskPanel unit={unit} location={weather?.location ?? null} llmEnabled={llmEnabled} />}
      </main>

      <footer className="muted small">
        Weather data by{" "}
        <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">
          Open-Meteo.com
        </a>{" "}
        (CC BY 4.0) · Maps © OpenStreetMap contributors
      </footer>

      {aboutOpen && <AboutModal onClose={() => setAboutOpen(false)} />}
    </div>
  );
}
