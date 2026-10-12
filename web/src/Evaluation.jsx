import React, { useEffect, useState } from "react";
import { api } from "./api.js";

const COLS = [
  ["extraction_f1", "Extraction F1"],
  ["extraction_f1_before_validation", "F1 before validator"],
  ["quote_verified_rate", "Quotes verified"],
  ["decision_accuracy", "Decision accuracy"],
  ["consistency", "Consistency (repeat runs)"],
  ["citation_valid_rate", "Valid citations"],
  ["n_schemes", "Schemes"],
];

const pct = (v) => (typeof v === "number" && v <= 1 ? `${(v * 100).toFixed(1)}%` : v ?? "—");

export default function Evaluation() {
  const [ev, setEv] = useState(null);
  const [calls, setCalls] = useState([]);
  useEffect(() => {
    api.get("/eval").then(setEv).catch(() => setEv({ available: false }));
    api.get("/llm-calls").then(setCalls).catch(() => {});
  }, []);

  return (
    <div>
      <h2>Paatrata vs a RAG chatbot</h2>
      {!ev?.available && (
        <p className="notice">
          No results yet. Run <code>python -m evaluation.run_eval --live</code> after adding gold rules and sources.
        </p>
      )}
      {ev?.available && (
        <>
          <p className="muted">
            Generated {ev.generated_at} on {ev.n_schemes} scheme(s).
          </p>
          <table>
            <thead>
              <tr>
                <th>System</th>
                {COLS.map(([, l]) => (
                  <th key={l}>{l}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(ev.summary).map(([sys, m]) => (
                <tr key={sys}>
                  <td>
                    <code>{sys}</code>
                  </td>
                  {COLS.map(([k]) => (
                    <td key={k}>
                      {k === "consistency" && sys.startsWith("paatrata") ? "100% (deterministic)" : k === "n_schemes" ? m[k] : pct(m[k])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="muted small">
            {ev.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      )}
      <h3>Model call log</h3>
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Purpose</th>
            <th>Backend:model</th>
            <th>Latency</th>
            <th>Cache</th>
            <th>Tokens in/out</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {calls.map((c) => (
            <tr key={c.id}>
              <td>{c.created_at}</td>
              <td>{c.purpose}</td>
              <td>
                {c.backend}:{c.model}
              </td>
              <td>{c.latency_ms ?? "—"} ms</td>
              <td>{c.cache_hit ? "hit" : "miss"}</td>
              <td>
                {c.input_tokens ?? "—"}/{c.output_tokens ?? "—"}
              </td>
              <td className="small">{c.error || ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
