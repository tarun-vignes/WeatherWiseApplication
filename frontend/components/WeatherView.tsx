"use client";

import { useEffect, useState } from "react";
import { ACTIVITIES, api, type Activity, type ActivityResponse, type NormalsResponse, type WeatherResponse } from "@/lib/api";
import { compass, dayLabel, precip, temp, timeOfDay, wind, type Unit } from "@/lib/format";

interface Props {
  data: WeatherResponse;
  unit: Unit;
  onSaveTrip: () => void;
}

export default function WeatherView({ data, unit, onSaveTrip }: Props) {
  const { location, current, daily } = data;
  const today = daily[0];
  const forecast = daily.slice(1, 6);

  return (
    <div className="stack">
      <section className="card current">
        <div className="current-head">
          <div>
            <h2>{location.label}</h2>
            <p className="muted">
              {location.latitude.toFixed(3)}, {location.longitude.toFixed(3)}
            </p>
            <p className="freshness small">
              <span className="tag live">Live</span> Retrieved from Open-Meteo at {timeOfDay(data.retrieved_at)} · observation time{" "}
              {current.time.slice(11)} local
            </p>
          </div>
          <button className="btn" onClick={onSaveTrip}>
            ＋ Save as trip
          </button>
        </div>
        <div className="current-body">
          <span className="big-icon" aria-hidden>
            {current.icon}
          </span>
          <div>
            <div className="big-temp">{temp(current.temperature, unit)}</div>
            <div>{current.description}</div>
            {today && (
              <div className="muted">
                H {temp(today.temp_max, unit)} · L {temp(today.temp_min, unit)}
              </div>
            )}
          </div>
          <dl className="facts">
            <div>
              <dt>Feels like</dt>
              <dd>{temp(current.apparent_temperature, unit)}</dd>
            </div>
            <div>
              <dt>Humidity</dt>
              <dd>{current.relative_humidity ?? "–"}%</dd>
            </div>
            <div>
              <dt>Wind</dt>
              <dd>
                {wind(current.wind_speed, unit)} {compass(current.wind_direction)}
              </dd>
            </div>
            <div>
              <dt>Rain chance today</dt>
              <dd>{today?.precipitation_probability_max ?? "–"}%</dd>
            </div>
            <div>
              <dt>UV index</dt>
              <dd>{today?.uv_index_max?.toFixed(0) ?? "–"}</dd>
            </div>
          </dl>
        </div>
        <NormalsBadge lat={location.latitude} lon={location.longitude} />
      </section>

      <section className="card">
        <h3>5-day forecast</h3>
        <div className="forecast">
          {forecast.map((d) => (
            <div key={d.date} className="day">
              <div className="day-name">{dayLabel(d.date, { weekday: "short" })}</div>
              <div className="muted small">{dayLabel(d.date, { month: "short", day: "numeric" })}</div>
              <div className="day-icon" title={d.description}>
                {d.icon}
              </div>
              <div className="small">{d.description}</div>
              <div>
                <strong>{temp(d.temp_max, unit)}</strong> <span className="muted">{temp(d.temp_min, unit)}</span>
              </div>
              <div className="small muted">
                💧 {d.precipitation_probability_max ?? 0}% · {precip(d.precipitation_sum, unit)}
              </div>
              <div className="small muted">💨 {wind(d.wind_speed_max, unit)}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="grid-2">
        <ActivityPlanner lat={location.latitude} lon={location.longitude} />
        <section className="card">
          <h3>Map</h3>
          <iframe
            className="map"
            title={`Map of ${location.label}`}
            loading="lazy"
            src={`https://www.openstreetmap.org/export/embed.html?bbox=${location.longitude - 0.15},${location.latitude - 0.1},${location.longitude + 0.15},${location.latitude + 0.1}&layer=mapnik&marker=${location.latitude},${location.longitude}`}
          />
          <a
            className="small"
            href={`https://www.openstreetmap.org/?mlat=${location.latitude}&mlon=${location.longitude}#map=11/${location.latitude}/${location.longitude}`}
            target="_blank"
            rel="noreferrer"
          >
            Open larger map ↗
          </a>
        </section>
      </div>
    </div>
  );
}

function NormalsBadge({ lat, lon }: { lat: number; lon: number }) {
  // Results are tagged with the coordinates they belong to, so a new location shows "loading" without resetting state.
  const key = `${lat},${lon}`;
  const [state, setState] = useState<{ key: string; normals: NormalsResponse | null }>({ key: "", normals: null });

  useEffect(() => {
    let cancelled = false;
    api
      .normals(lat, lon)
      .then((normals) => !cancelled && setState({ key, normals }))
      .catch(() => !cancelled && setState({ key, normals: null }));
    return () => {
      cancelled = true;
    };
  }, [key, lat, lon]);

  const normals = state.key === key ? state.normals : null;
  if (state.key === key && !normals) return null;
  if (!normals) return <p className="badge muted">Comparing with 30 years of history…</p>;
  const tone = normals.delta == null || Math.abs(normals.delta) < 1.5 ? "" : normals.delta > 0 ? "warm" : "cool";
  return (
    <p className={`badge ${tone}`} title={`30-year normal: high ${normals.normal_high}°C, low ${normals.normal_low}°C, rain on ${normals.wet_day_percent}% of days`}>
      📊 {normals.label}
    </p>
  );
}

function ActivityPlanner({ lat, lon }: { lat: number; lon: number }) {
  const [activity, setActivity] = useState<Activity>("running");
  const key = `${lat},${lon},${activity}`;
  const [state, setState] = useState<{ key: string; result: ActivityResponse | null; error: string }>({
    key: "",
    result: null,
    error: "",
  });

  useEffect(() => {
    let cancelled = false;
    api
      .activity(lat, lon, activity)
      .then((result) => !cancelled && setState({ key, result, error: "" }))
      .catch((e) => !cancelled && setState({ key, result: null, error: e.message }));
    return () => {
      cancelled = true;
    };
  }, [key, lat, lon, activity]);

  const current = state.key === key ? state : null;
  const result = current?.result;
  const error = current?.error;

  return (
    <section className="card">
      <div className="row-between">
        <h3>Best day for…</h3>
        <select className="activity-select" value={activity} onChange={(e) => setActivity(e.target.value as Activity)} aria-label="Activity">
          {ACTIVITIES.map((a) => (
            <option key={a.value} value={a.value}>
              {a.label}
            </option>
          ))}
        </select>
      </div>
      {error && <p className="error">{error}</p>}
      {result?.best && (
        <p>
          🏆 <strong>{dayLabel(result.best.date)}</strong> — {result.best.rating} ({result.best.score}/100)
        </p>
      )}
      <ul className="scores">
        {result?.days.map((d) => (
          <li key={d.date}>
            <span className="score-day">{dayLabel(d.date, { weekday: "short" })}</span>
            <span className="bar" aria-hidden>
              <span className={`fill r-${d.rating.toLowerCase()}`} style={{ width: `${d.score}%` }} />
            </span>
            <span className="score-num">{d.score}</span>
            <span className="small muted reasons">{d.reasons.join(", ")}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
