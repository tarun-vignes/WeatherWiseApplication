"use client";

import { useCallback, useEffect, useState } from "react";
import { ACTIVITIES, api, type Activity, type Briefing, type Trip, type TripInput } from "@/lib/api";
import { addDays, dateTime, dayLabel, iconFor, isoDate, parseDate, precip, temp, wind, type Unit } from "@/lib/format";

// Saved forecasts older than this get a "may have changed" hint.
const STALE_FORECAST_HOURS = 6;

const MAX_RANGE_DAYS = 31;
const MAX_DAYS_AHEAD = 15;

export interface TripDraft {
  location: string;
  latitude?: number;
  longitude?: number;
}

interface FormState {
  name: string;
  location: string;
  latitude?: number;
  longitude?: number;
  start_date: string;
  end_date: string;
  activity: Activity | "";
  notes: string;
}

function emptyForm(draft?: TripDraft | null): FormState {
  const today = new Date();
  return {
    name: "",
    location: draft?.location ?? "",
    latitude: draft?.latitude,
    longitude: draft?.longitude,
    start_date: isoDate(addDays(today, 1)),
    end_date: isoDate(addDays(today, 4)),
    activity: "",
    notes: "",
  };
}

// Mirrors the backend rules so users get instant feedback; the API re-checks everything.
function validate(f: FormState): string | null {
  if (!f.location.trim() && (f.latitude == null || f.longitude == null)) return "Enter a location.";
  if (!f.start_date || !f.end_date) return "Pick a start and end date.";
  const start = parseDate(f.start_date);
  const end = parseDate(f.end_date);
  if (end < start) return "End date must be on or after the start date.";
  if (start < new Date(1940, 0, 1)) return "Start date must be on or after 1940-01-01.";
  const latest = addDays(new Date(), MAX_DAYS_AHEAD);
  if (end > latest) return `End date can be at most ${MAX_DAYS_AHEAD} days from today (${isoDate(latest)}).`;
  const span = Math.round((end.getTime() - start.getTime()) / 86_400_000) + 1;
  if (span > MAX_RANGE_DAYS) return `Date range is ${span} days; the maximum is ${MAX_RANGE_DAYS}.`;
  return null;
}

interface Props {
  unit: Unit;
  draft: TripDraft | null;
  onDraftUsed: () => void;
}

export default function TripsPanel({ unit, draft, onDraftUsed }: Props) {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [form, setForm] = useState<FormState>(() => emptyForm(draft));
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  const load = useCallback(async (q: string) => {
    setLoading(true);
    try {
      setTrips(await api.listTrips(q));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => load(filter.trim()), 250);
    return () => clearTimeout(timer);
  }, [filter, load]);

  // "Save as trip" from the weather tab pre-fills the form on mount; consume it so it isn't reused.
  useEffect(() => {
    if (draft) onDraftUsed();
  }, [draft, onDraftUsed]);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({
      ...f,
      [key]: value,
      // Typing a new location replaces coordinates that came from geolocation.
      ...(key === "location" ? { latitude: undefined, longitude: undefined } : {}),
    }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const problem = validate(form);
    if (problem) {
      setFormError(problem);
      return;
    }
    setSaving(true);
    setFormError("");
    const useCoords = form.latitude != null && form.longitude != null;
    const input: TripInput = {
      name: form.name.trim() || null,
      location: useCoords ? null : form.location.trim(),
      latitude: useCoords ? form.latitude : null,
      longitude: useCoords ? form.longitude : null,
      location_label: useCoords ? form.location.trim() || null : null,
      start_date: form.start_date,
      end_date: form.end_date,
      activity: form.activity || null,
      notes: form.notes.trim() || null,
    };
    try {
      if (editingId != null) {
        const original = trips.find((t) => t.id === editingId);
        const patch: Partial<TripInput> = { ...input };
        // Only send the location if it changed, so we don't re-geocode needlessly.
        if (original && form.location.trim() === original.location_name && !useCoords) {
          delete patch.location;
          delete patch.latitude;
          delete patch.longitude;
        }
        if (!patch.name) delete patch.name;
        const updated = await api.updateTrip(editingId, patch);
        setTrips((ts) => ts.map((t) => (t.id === updated.id ? updated : t)));
      } else {
        const created = await api.createTrip(input);
        setTrips((ts) => [created, ...ts]);
      }
      setEditingId(null);
      setForm(emptyForm());
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function startEdit(t: Trip) {
    setEditingId(t.id);
    setFormError("");
    setForm({
      name: t.name,
      location: t.location_name,
      start_date: t.start_date,
      end_date: t.end_date,
      activity: t.activity ?? "",
      notes: t.notes ?? "",
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div className="stack">
      <section className="card">
        <h3>{editingId != null ? "Edit trip" : "Plan a trip"}</h3>
        <p className="muted small">
          Save a place and date range. We store the daily weather for it: forecasts for future dates (up to {MAX_DAYS_AHEAD}{" "}
          days ahead) and recorded history for past dates (back to 1940).
        </p>
        <form className="trip-form" onSubmit={submit} noValidate>
          <label>
            Location
            <input
              value={form.location}
              onChange={(e) => set("location", e.target.value)}
              placeholder="City, postal code, or lat,lon"
              required={form.latitude == null}
            />
            {form.latitude != null && <span className="small muted">Using your coordinates</span>}
          </label>
          <label>
            <span>
              Trip name <span className="muted">(optional)</span>
            </span>
            <input value={form.name} onChange={(e) => set("name", e.target.value)} maxLength={120} placeholder="e.g. Spring break" />
          </label>
          <label>
            Start date
            <input type="date" value={form.start_date} min="1940-01-01" onChange={(e) => set("start_date", e.target.value)} required />
          </label>
          <label>
            End date
            <input
              type="date"
              value={form.end_date}
              min={form.start_date}
              max={isoDate(addDays(new Date(), MAX_DAYS_AHEAD))}
              onChange={(e) => set("end_date", e.target.value)}
              required
            />
          </label>
          <label>
            <span>
              Activity <span className="muted">(optional)</span>
            </span>
            <select value={form.activity} onChange={(e) => set("activity", e.target.value as Activity | "")}>
              <option value="">None</option>
              {ACTIVITIES.map((a) => (
                <option key={a.value} value={a.value}>
                  {a.label}
                </option>
              ))}
            </select>
          </label>
          <label className="span-2">
            <span>
              Notes <span className="muted">(optional)</span>
            </span>
            <textarea value={form.notes} onChange={(e) => set("notes", e.target.value)} maxLength={2000} rows={2} />
          </label>
          {formError && <p className="error span-2">{formError}</p>}
          <div className="span-2 row">
            <button className="btn primary" type="submit" disabled={saving}>
              {saving ? "Saving…" : editingId != null ? "Save changes" : "Create trip"}
            </button>
            {editingId != null && (
              <button
                className="btn"
                type="button"
                onClick={() => {
                  setEditingId(null);
                  setForm(emptyForm());
                  setFormError("");
                }}
              >
                Cancel
              </button>
            )}
          </div>
        </form>
      </section>

      <section className="card">
        <div className="row-between wrap">
          <h3>Saved trips</h3>
          <div className="row wrap">
            <input className="filter" placeholder="Filter trips…" value={filter} onChange={(e) => setFilter(e.target.value)} />
            <span className="small muted">Export all:</span>
            <a className="btn small-btn" href={api.exportUrl("csv")}>CSV</a>
            <a className="btn small-btn" href={api.exportUrl("json")}>JSON</a>
            <a className="btn small-btn" href={api.exportUrl("md")}>Markdown</a>
          </div>
        </div>
        {error && <p className="error">{error}</p>}
        {loading && trips.length === 0 && <p className="muted">Loading trips…</p>}
        {!loading && trips.length === 0 && !error && <p className="muted">No trips yet. Create one above.</p>}
        <div className="stack">
          {trips.map((t) => (
            <TripCard
              key={t.id}
              trip={t}
              unit={unit}
              onEdit={() => startEdit(t)}
              onChange={(updated) => setTrips((ts) => ts.map((x) => (x.id === updated.id ? updated : x)))}
              onDeleted={() => {
                setTrips((ts) => ts.filter((x) => x.id !== t.id));
                if (editingId === t.id) {
                  setEditingId(null);
                  setForm(emptyForm());
                }
              }}
            />
          ))}
        </div>
      </section>
    </div>
  );
}

interface CardProps {
  trip: Trip;
  unit: Unit;
  onEdit: () => void;
  onChange: (t: Trip) => void;
  onDeleted: () => void;
}

function TripCard({ trip, unit, onEdit, onChange, onDeleted }: CardProps) {
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [busy, setBusy] = useState<"" | "briefing" | "refresh" | "delete">("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState("");
  const [justRefreshed, setJustRefreshed] = useState(false);
  // Read the clock once per render pass via state so render stays pure.
  const [now] = useState(() => Date.now());
  const savedAt = trip.weather_updated_at ? new Date(trip.weather_updated_at).getTime() : null;
  const hasForecast = trip.days.some((d) => d.source === "forecast");
  const staleForecast = !justRefreshed && hasForecast && savedAt != null && now - savedAt > STALE_FORECAST_HOURS * 3_600_000;

  async function run<T>(kind: typeof busy, fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(kind);
    setError("");
    try {
      return await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  return (
    <article className="trip">
      <header className="row-between wrap">
        <div>
          <h4>{trip.name}</h4>
          <p className="muted small">
            📍 {trip.location_name} · {dayLabel(trip.start_date)} – {dayLabel(trip.end_date)}
            {trip.activity && <> · {ACTIVITIES.find((a) => a.value === trip.activity)?.label}</>}
          </p>
          {trip.notes && <p className="small">{trip.notes}</p>}
        </div>
        <div className="row wrap">
          <button className="btn small-btn" disabled={!!busy} onClick={() => run("briefing", () => api.briefing(trip.id).then(setBriefing))}>
            {busy === "briefing" ? "Thinking…" : "✨ Briefing"}
          </button>
          <button className="btn small-btn" disabled={!!busy} onClick={() =>
              run("refresh", () =>
                api.refreshTrip(trip.id).then((t) => {
                  onChange(t);
                  setJustRefreshed(true);
                }),
              )
            }>
            {busy === "refresh" ? "Refreshing…" : "↻ Refresh"}
          </button>
          <button className="btn small-btn" disabled={!!busy} onClick={onEdit}>
            ✎ Edit
          </button>
          {confirmDelete ? (
            <>
              <button
                className="btn small-btn danger"
                disabled={!!busy}
                onClick={() => run("delete", () => api.deleteTrip(trip.id).then(onDeleted))}
              >
                {busy === "delete" ? "Deleting…" : "Confirm delete"}
              </button>
              <button className="btn small-btn" onClick={() => setConfirmDelete(false)}>
                Keep
              </button>
            </>
          ) : (
            <button className="btn small-btn" disabled={!!busy} onClick={() => setConfirmDelete(true)}>
              🗑 Delete
            </button>
          )}
        </div>
      </header>

      {error && <p className="error">{error}</p>}
      <p className="freshness small">
        <span className="tag saved">Saved weather</span>
        {trip.weather_updated_at ? (
          <>
            {justRefreshed ? "Refreshed just now" : `Retrieved ${dateTime(trip.weather_updated_at)}`}
            {hasForecast ? "; forecast days are a snapshot from then." : "; recorded history, won't change."}
          </>
        ) : (
          "Not retrieved yet."
        )}
        {staleForecast && <span className="stale"> Forecast may have changed. Use ↻ Refresh for the latest.</span>}
      </p>
      {briefing && (
        <div className="briefing">
          <span className="tag">{briefing.source === "llm" ? "AI summary" : "Rule-based summary"}</span>
          {briefing.source === "llm" ? (
            <p>{briefing.text}</p>
          ) : (
            <ul>
              {briefing.bullets.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th></th>
              <th>High</th>
              <th>Low</th>
              <th>Rain</th>
              <th>Wind</th>
              <th>Data</th>
            </tr>
          </thead>
          <tbody>
            {trip.days.map((d) => (
              <tr key={d.date}>
                <td>{dayLabel(d.date)}</td>
                <td>{iconFor(d.weather_code)}</td>
                <td>{temp(d.temp_max, unit)}</td>
                <td>{temp(d.temp_min, unit)}</td>
                <td>
                  {precip(d.precipitation_sum, unit)}
                  {d.precipitation_probability_max != null && <span className="muted"> · {d.precipitation_probability_max}%</span>}
                </td>
                <td>{wind(d.wind_speed_max, unit)}</td>
                <td className="small muted">{d.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted">
        Export this trip: <a href={api.exportUrl("csv", trip.id)}>CSV</a> · <a href={api.exportUrl("json", trip.id)}>JSON</a> ·{" "}
        <a href={api.exportUrl("md", trip.id)}>Markdown</a>
      </p>
    </article>
  );
}
