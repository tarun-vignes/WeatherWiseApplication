export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type Activity = "running" | "cycling" | "hiking" | "beach" | "golf" | "picnic";
export const ACTIVITIES: { value: Activity; label: string }[] = [
  { value: "running", label: "Running" },
  { value: "cycling", label: "Cycling" },
  { value: "hiking", label: "Hiking" },
  { value: "beach", label: "Beach" },
  { value: "golf", label: "Golf" },
  { value: "picnic", label: "Picnic" },
];

export interface Location {
  name: string;
  label: string;
  latitude: number;
  longitude: number;
  country?: string | null;
  admin1?: string | null;
  timezone?: string | null;
}

export interface DailyWeather {
  date: string;
  source: string;
  weather_code: number | null;
  description: string;
  icon: string;
  temp_max: number | null;
  temp_min: number | null;
  precipitation_sum: number | null;
  precipitation_probability_max: number | null;
  wind_speed_max: number | null;
  uv_index_max: number | null;
}

export interface CurrentWeather {
  time: string;
  temperature: number | null;
  apparent_temperature: number | null;
  relative_humidity: number | null;
  precipitation: number | null;
  wind_speed: number | null;
  wind_direction: number | null;
  weather_code: number | null;
  description: string;
  icon: string;
  is_day: boolean;
}

export interface WeatherResponse {
  location: Location;
  current: CurrentWeather;
  daily: DailyWeather[];
  /** When the backend fetched this from Open-Meteo (it caches for up to 10 minutes). */
  retrieved_at: string;
}

export interface NormalsResponse {
  date: string;
  years: number;
  normal_high: number;
  normal_low: number;
  wet_day_percent: number;
  forecast_high: number | null;
  delta: number | null;
  label: string;
}

export interface ActivityDay {
  date: string;
  score: number;
  rating: string;
  reasons: string[];
}

export interface ActivityResponse {
  activity: Activity;
  best: ActivityDay | null;
  days: ActivityDay[];
}

export type TripDay = Omit<DailyWeather, "description" | "icon">;

export interface Trip {
  id: number;
  name: string;
  location_query: string;
  location_name: string;
  latitude: number;
  longitude: number;
  timezone: string;
  start_date: string;
  end_date: string;
  activity: Activity | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  weather_updated_at: string | null;
  days: TripDay[];
}

export interface TripInput {
  name?: string | null;
  location?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  location_label?: string | null;
  start_date: string;
  end_date: string;
  activity?: Activity | null;
  notes?: string | null;
}

export interface Briefing {
  text: string;
  bullets: string[];
  source: "llm" | "rules";
}

export interface AskResponse {
  answer: string;
  source: "llm" | "rules";
  location: Location | null;
  start_date: string | null;
  end_date: string | null;
  days: DailyWeather[];
}

export interface Health {
  status: string;
  llm: { enabled: boolean; provider: string; model: string | null };
}

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(`Can't reach the API at ${API_BASE}. Is the backend running?`, 0);
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join(" ");
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(message, res.status);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const qs = (params: Record<string, string | number>) =>
  new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();

export const api = {
  health: () => request<Health>("/api/health"),
  searchLocations: (q: string, signal?: AbortSignal) =>
    request<Location[]>(`/api/locations/search?${qs({ q, count: 5 })}`, { signal }),
  weatherByQuery: (q: string, signal?: AbortSignal) => request<WeatherResponse>(`/api/weather?${qs({ q })}`, { signal }),
  weatherByCoords: (lat: number, lon: number, signal?: AbortSignal) =>
    request<WeatherResponse>(`/api/weather?${qs({ lat, lon })}`, { signal }),
  normals: (lat: number, lon: number) => request<NormalsResponse>(`/api/weather/normals?${qs({ lat, lon })}`),
  activity: (lat: number, lon: number, activity: Activity) =>
    request<ActivityResponse>(`/api/weather/activity?${qs({ lat, lon, activity })}`),

  listTrips: (q = "") => request<Trip[]>(`/api/trips${q ? `?${qs({ q })}` : ""}`),
  createTrip: (input: TripInput) => request<Trip>("/api/trips", { method: "POST", body: JSON.stringify(input) }),
  updateTrip: (id: number, input: Partial<TripInput>) =>
    request<Trip>(`/api/trips/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
  refreshTrip: (id: number) => request<Trip>(`/api/trips/${id}/refresh`, { method: "POST" }),
  deleteTrip: (id: number) => request<void>(`/api/trips/${id}`, { method: "DELETE" }),
  briefing: (id: number) => request<Briefing>(`/api/trips/${id}/briefing`),
  exportUrl: (format: "csv" | "json" | "md", id?: number) =>
    `${API_BASE}/api/trips${id ? `/${id}` : ""}/export?${qs({ format })}`,

  ask: (question: string, lat?: number, lon?: number) =>
    request<AskResponse>("/api/ask", {
      method: "POST",
      body: JSON.stringify({ question, latitude: lat ?? null, longitude: lon ?? null }),
    }),
};
