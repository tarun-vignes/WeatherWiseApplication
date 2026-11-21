"use client";

import { useState } from "react";
import { api, type AskResponse, type Location } from "@/lib/api";
import { dayLabel, temp, type Unit } from "@/lib/format";

const EXAMPLES = [
  "Will it rain in Seattle this weekend?",
  "Best day for golf in San Diego?",
  "Warmest day in Phoenix in the next 7 days",
  "Do I need a jacket tomorrow?",
];

interface Props {
  unit: Unit;
  location: Location | null;
  llmEnabled: boolean;
}

export default function AskPanel({ unit, location, llmEnabled }: Props) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function ask(q: string) {
    if (q.trim().length < 3) {
      setError("Type a question first.");
      return;
    }
    setQuestion(q);
    setLoading(true);
    setError("");
    try {
      setResult(await api.ask(q.trim(), location?.latitude, location?.longitude));
    } catch (e) {
      setError((e as Error).message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card">
      <h3>Ask about the weather</h3>
      <p className="muted small">
        Ask in plain English. Answers use only live Open-Meteo data
        {llmEnabled ? " (summarized by the configured LLM)." : " (rule-based mode; no LLM configured)."}
        {location ? ` Questions without a place use ${location.name}.` : ""}
      </p>
      <form
        className="search"
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
      >
        <input aria-label="Question" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Will it rain in Chicago on Saturday?" maxLength={500} />
        <button className="btn primary" disabled={loading}>
          {loading ? "Asking…" : "Ask"}
        </button>
      </form>
      <div className="chips">
        {EXAMPLES.map((ex) => (
          <button key={ex} className="chip" onClick={() => ask(ex)} disabled={loading}>
            {ex}
          </button>
        ))}
      </div>
      {error && <p className="error">{error}</p>}
      {result && (
        <div className="answer">
          <span className="tag">{result.source === "llm" ? "AI answer" : "Rule-based answer"}</span>
          <p>{result.answer}</p>
          {result.location && result.start_date && (
            <p className="small muted">
              {result.location.label} · {dayLabel(result.start_date)}
              {result.end_date && result.end_date !== result.start_date && ` – ${dayLabel(result.end_date)}`}
            </p>
          )}
          {result.days.length > 0 && (
            <div className="mini-days">
              {result.days.map((d) => (
                <div key={d.date} className="mini-day">
                  <div className="small">{dayLabel(d.date, { weekday: "short" })}</div>
                  <div>{d.icon}</div>
                  <div className="small">
                    {temp(d.temp_max, unit)} / {temp(d.temp_min, unit)}
                  </div>
                  <div className="small muted">💧{d.precipitation_probability_max ?? "–"}%</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
