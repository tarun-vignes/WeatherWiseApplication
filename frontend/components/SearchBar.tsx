"use client";

import { useEffect, useRef, useState } from "react";
import { api, type Location } from "@/lib/api";

interface Props {
  loading: boolean;
  onSearch: (query: string) => void;
  onSelect: (location: Location) => void;
  onCoords: (lat: number, lon: number) => void;
  onError: (message: string) => void;
}

export default function SearchBar({ loading, onSearch, onSelect, onCoords, onError }: Props) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Location[]>([]);
  const [open, setOpen] = useState(false);
  const [locating, setLocating] = useState(false);
  const skipNext = useRef(false);
  // Bumped whenever the user starts a new lookup, so a slow geolocation fix can't replace a search typed meanwhile.
  const intent = useRef(0);

  // Debounced autocomplete for city names / postal codes.
  useEffect(() => {
    if (skipNext.current) {
      skipNext.current = false;
      return;
    }
    const q = query.trim();
    if (q.length < 3 || /^-?\d+(\.\d+)?\s*,/.test(q)) return;
    const request = new AbortController();
    const timer = setTimeout(() => {
      api
        .searchLocations(q, request.signal)
        .then((s) => !request.signal.aborted && setSuggestions(s))
        .catch(() => !request.signal.aborted && setSuggestions([]));
    }, 300);
    return () => {
      clearTimeout(timer);
      request.abort();
    };
  }, [query]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (q.length < 2) {
      onError("Enter a city, postal code, or coordinates (e.g. 40.71, -74.00).");
      return;
    }
    intent.current++;
    setLocating(false);
    setOpen(false);
    onSearch(q);
  }

  function pick(loc: Location) {
    skipNext.current = true;
    setQuery(loc.label);
    setOpen(false);
    setSuggestions([]);
    intent.current++;
    setLocating(false);
    onSelect(loc);
  }

  function locate() {
    if (!("geolocation" in navigator)) {
      onError("Your browser doesn't support geolocation. Search for a place instead.");
      return;
    }
    const mine = ++intent.current;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        if (mine !== intent.current) return;
        setLocating(false);
        onCoords(pos.coords.latitude, pos.coords.longitude);
      },
      (err) => {
        if (mine !== intent.current) return;
        setLocating(false);
        onError(
          err.code === err.PERMISSION_DENIED
            ? "Location permission was denied. Allow it in your browser, or search for a place instead."
            : "Couldn't get your location. Try again or search for a place.",
        );
      },
      { timeout: 10000, maximumAge: 5 * 60 * 1000 },
    );
  }

  return (
    <form className="search" onSubmit={submit} role="search">
      <div className="search-field">
        <input
          aria-label="Location"
          placeholder="City, postal code, or lat,lon (e.g. Austin, 10001, 48.85,2.35)"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          autoComplete="off"
        />
        {open && query.trim().length >= 3 && suggestions.length > 0 && (
          <ul className="suggestions" role="listbox">
            {suggestions.map((s) => (
              <li key={`${s.latitude},${s.longitude}`}>
                <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => pick(s)}>
                  {s.label}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <button className="btn primary" type="submit">
        {loading ? "Loading…" : "Search"}
      </button>
      <button className="btn" type="button" onClick={locate} disabled={locating} title="Use my current location">
        {locating ? "Locating…" : "📍 My location"}
      </button>
    </form>
  );
}
