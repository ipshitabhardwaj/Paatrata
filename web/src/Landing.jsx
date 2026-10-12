import React, { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

const LABEL = { ELIGIBLE: "Eligible", NOT_ELIGIBLE: "Not eligible", NEEDS_INFO: "Needs more information" };
const SCHEME = "oapc-chandigarh";

// Live checker in the hero: real API, deterministic rules, updates as you type.
export function LiveCheck() {
  const [age, setAge] = useState("64");
  const [income, setIncome] = useState("162000");
  const [years, setYears] = useState("5");
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");
  const timer = useRef(null);

  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      const profile = { is_domicile_of_jurisdiction: true };
      if (age !== "") profile.age_years = Number(age);
      if (income !== "") profile.family_annual_income_inr = Number(income);
      if (years !== "") profile.residence_years_in_jurisdiction = Number(years);
      try {
        setRes(await api.post("/check", { scheme_id: SCHEME, profile }));
        setErr("");
      } catch (e) {
        setErr("Start the API to try this live.");
      }
    }, 180);
    return () => clearTimeout(timer.current);
  }, [age, income, years]);

  const v = res?.verdict;
  const failing = v?.results.filter((r) => r.outcome === "FALSE") || [];
  const missing = v?.results.filter((r) => r.outcome === "UNKNOWN") || [];
  const shown = failing[0] || missing[0];

  return (
    <aside className="live" aria-live="polite">
      <p className="live-title">Try it: Old Age Pension, Chandigarh</p>
      <div className="live-fields">
        <label>
          Age
          <input inputMode="numeric" value={age} onChange={(e) => setAge(e.target.value.replace(/[^\d.]/g, ""))} />
        </label>
        <label>
          Family income a year (₹)
          <input inputMode="numeric" value={income} onChange={(e) => setIncome(e.target.value.replace(/[^\d.]/g, ""))} />
        </label>
        <label>
          Years in Chandigarh
          <input inputMode="numeric" value={years} onChange={(e) => setYears(e.target.value.replace(/[^\d.]/g, ""))} />
        </label>
      </div>
      {err && <p className="live-err">{err}</p>}
      {v && (
        <div className={`live-out ${v.verdict}`}>
          <strong>{LABEL[v.verdict]}</strong>
          {shown ? (
            <p>
              <span className="live-why">{failing.length ? "Because the notice says:" : "Still needed, per the notice:"}</span>
              <q>{shown.citation.quote}</q>
            </p>
          ) : (
            <p>
              <span className="live-why">Meets all {v.results.length} conditions in the notice.</span>
            </p>
          )}
        </div>
      )}
      <p className="live-foot">Computed by code from officer-approved rules. No AI runs at this step.</p>
    </aside>
  );
}

export function Rulebook({ data, onOpen }) {
  if (!data?.schemes?.length) return null;
  const total = data.schemes.reduce((a, s) => a + s.conditions, 0);
  return (
    <section className="rulebook">
      <div className="rb-head">
        <h2>The rulebook</h2>
        <p>
          {data.schemes.length} Chandigarh schemes, {total} computable conditions, each tied to the sentence it came from. Open one to check
          an applicant against it.
        </p>
      </div>
      <div className="rb-grid">
        {data.schemes.map((s) => (
          <button key={s.id} className="rb-tile" onClick={() => onOpen(s.id)}>
            <span className="rb-name">{s.name.replace(", Chandigarh", "")}</span>
            <span className="rb-benefit">{s.benefit}</span>
            <span className="rb-facts">
              <span>
                <b>{s.conditions}</b> conditions
              </span>
              {s.any_groups > 0 && <span>alternative routes to qualify</span>}
              {s.needs_human > 0 && <span className="rb-human">{s.needs_human} needs a human check</span>}
            </span>
            <span className="rb-src">{s.source_type.startsWith("primary") ? "Official notification" : "Secondary summary"}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

const pct = (x) => (typeof x === "number" ? `${Math.round(x * 100)}%` : "—");

export function AIRoles({ evalData }) {
  const sys = evalData?.summary ? Object.entries(evalData.summary) : [];
  const ours = sys.find(([k]) => k.startsWith("paatrata/gemini"))?.[1];
  const rag = sys.find(([k]) => k.startsWith("rag/"))?.[1];
  return (
    <section className="roles">
      <div className="roles-head">
        <h2>Where AI does the work, and where it stops</h2>
        <p>Models read and question the document. They never decide who is eligible.</p>
      </div>
      <div className="roles-grid">
        <article className="role">
          <h3>Gemini reads the notification</h3>
          <p>Structured output into a fixed rule schema. Every condition must quote its sentence; code rejects any quote it cannot find in the document.</p>
        </article>
        <article className="role">
          <h3>Gemini reviews its own encoding</h3>
          <p>A second pass looks for missing, misread and ambiguous conditions. Its questions block approval until an officer answers them.</p>
        </article>
        <article className="role">
          <h3>Gemma 4 runs it on-premise</h3>
          <p>The same compiler runs on Google's open-weight Gemma 4, locally or on AI Studio, for departments that cannot send documents out.</p>
        </article>
        <article className="role code">
          <h3>Code decides</h3>
          <p>Approved rules run in a small deterministic engine. Same details, same answer, every time, with the clause cited. Missing facts give "needs information", never a guess.</p>
        </article>
      </div>
      {ours && (
        <div className="evidence">
          <h3>Measured on {evalData.n_schemes} schemes against hand-labelled rules</h3>
          <div className="ev-row">
            <div>
              <span className="ev-num">{pct(ours.decision_accuracy)}</span>
              <span>decision accuracy, Paatrata with Gemini</span>
            </div>
            {rag && (
              <div>
                <span className="ev-num muted-num">{pct(rag.decision_accuracy)}</span>
                <span>decision accuracy, a plain RAG chatbot on the same documents</span>
              </div>
            )}
            {rag && (
              <div>
                <span className="ev-num muted-num">{pct(rag.consistency)}</span>
                <span>of repeated chatbot questions got the same answer (Paatrata: always)</span>
              </div>
            )}
          </div>
          <p className="small">Test applicants are synthetic. Scheme texts are secondary summaries. Details on the Evidence tab.</p>
        </div>
      )}
    </section>
  );
}
