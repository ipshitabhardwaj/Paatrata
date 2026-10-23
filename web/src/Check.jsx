import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import SourceViewer from "./SourceViewer.jsx";

const LABEL = { ELIGIBLE: "Eligible", NOT_ELIGIBLE: "Not eligible", NEEDS_INFO: "Needs more information" };
const OPS = { ">=": "≥", "<=": "≤", ">": ">", "<": "<", "==": "=", "!=": "≠", in: "in", not_in: "not in" };
const human = (f) => f.replace(/_/g, " ").replace(" inr", " (₹)").replace(" in jurisdiction", " in UT");
const show = (v) => (v === null || v === undefined ? null : typeof v === "boolean" ? (v ? "yes" : "no") : typeof v === "number" ? v.toLocaleString("en-IN") : String(v));

export default function Check({ initial }) {
  const [schemes, setSchemes] = useState([]);
  const [sid, setSid] = useState("");
  const [fields, setFields] = useState([]);
  const [examples, setExamples] = useState([]);
  const [profile, setProfile] = useState({});
  const [lang, setLang] = useState("en");
  const [res, setRes] = useState(null);
  const [source, setSource] = useState(null);
  const [active, setActive] = useState(null);
  const [allResults, setAllResults] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get("/schemes")
      .then((s) => {
        const ok = s.filter((x) => x.approved_version);
        setSchemes(ok);
        if (ok.length) setSid(initial && ok.some((x) => x.id === initial) ? initial : ok[0].id);
      })
      .catch((e) => setErr(e.message));
  }, [initial]);
  useEffect(() => {
    if (!sid) return;
    setRes(null);
    setSource(null);
    setProfile({});
    setErr("");
    api.get(`/schemes/${sid}/form`).then(setFields).catch((e) => setErr(e.message));
    api.get(`/schemes/${sid}/examples`).then(setExamples).catch(() => setExamples([]));
  }, [sid]);

  const setField = (f, raw) => {
    const p = { ...profile };
    if (raw === "" || raw === undefined) delete p[f.name];
    else p[f.name] = f.type === "number" ? Number(raw) : f.type === "boolean" ? raw === "true" : raw;
    setProfile(p);
  };

  const run = async (p = profile) => {
    setErr("");
    setBusy(true);
    try {
      const r = await api.post("/check", { scheme_id: sid, profile: p, lang });
      setRes(r);
      const v = await api.get(`/versions/${r.version_id}`);
      setSource(v.source);
      setActive(r.verdict.failed_conditions[0] || null);
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  };

  const tone = { TRUE: "ok", FALSE: "bad", UNKNOWN: "amb" };
  const marks = res ? res.verdict.results.map((r) => ({ id: r.condition_id, quote: r.citation.quote, page: r.citation.page, tone: tone[r.outcome] })) : [];

  return (
    <div className="split">
      <aside>
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            run();
          }}
        >
          <h3>Applicant details</h3>
          <label>
            Scheme
            <select value={sid} onChange={(e) => setSid(e.target.value)}>
              {schemes.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          {fields.map((f) => (
            <label key={f.name}>
              {f.description}
              {f.unit && f.unit !== "INR" ? ` (${f.unit})` : f.unit === "INR" ? " (₹)" : ""}
              {f.type === "number" && (
                <input type="number" step="any" value={profile[f.name] ?? ""} onChange={(e) => setField(f, e.target.value)} />
              )}
              {f.type === "boolean" && (
                <select value={profile[f.name] === undefined ? "" : String(profile[f.name])} onChange={(e) => setField(f, e.target.value)}>
                  <option value="">— not given —</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              )}
              {f.type === "category" && (
                <select value={profile[f.name] ?? ""} onChange={(e) => setField(f, e.target.value)}>
                  <option value="">— not given —</option>
                  {f.options.map((o) => (
                    <option key={o}>{o}</option>
                  ))}
                </select>
              )}
            </label>
          ))}
          <label>
            Explanation language
            <select value={lang} onChange={(e) => setLang(e.target.value)}>
              <option value="en">English (template, no AI)</option>
              <option value="hi">हिन्दी (Gemini, verdict-checked)</option>
              <option value="pa">ਪੰਜਾਬੀ (Gemini, verdict-checked)</option>
            </select>
          </label>
          <button disabled={!sid || busy}>{busy ? "Checking…" : "Check eligibility"}</button>
          <button
            type="button"
            disabled={!Object.keys(profile).length || busy}
            onClick={async () => {
              setErr("");
              setBusy(true);
              try {
                const r = await api.post("/check/all", profile);
                setRes(null);
                setAllResults(r);
              } catch (e2) {
                setErr(e2.message);
              } finally {
                setBusy(false);
              }
            }}
            className="btn-all"
          >
            Check all schemes
          </button>
          <p className="muted small">Leave a field empty to see how missing information is handled.</p>
        </form>
        {examples.length > 0 && (
          <div className="card">
            <h3>Try a test applicant</h3>
            <p className="muted small">Synthetic cases generated at each rule's boundary. Pick one to fill the form and check it.</p>
            {examples.map((x, i) => (
              <button
                key={i}
                className="example"
                onClick={() => {
                  setProfile(x.profile);
                  run(x.profile);
                }}
              >
                <span>{x.description}</span>
                <span className={`chip ${x.expected}`}>{LABEL[x.expected]}</span>
              </button>
            ))}
          </div>
        )}
        {err && <pre className="error">{err}</pre>}
      </aside>
      <section>
        {!res && (
          <div className="empty">
            <h2>Deterministic, cited answers</h2>
            <p className="muted">
              Only officer-approved rules are used. The verdict is computed by code from those rules, not generated by a model, so
              the same details always give the same answer, with the clause it rests on.
            </p>
          </div>
        )}
        {res && (
          <div>
            <div className={`verdict ${res.verdict.verdict}`}>
              {LABEL[res.verdict.verdict]}
              {res.verdict.verdict === "NEEDS_INFO" && <span className="sub">missing: {res.verdict.missing_fields.map(human).join(", ")}</span>}
            </div>
            <p className="muted small">
              Answered from rules version {res.version}, {res.extractor === "gold" ? "hand-labelled reference rules" : `compiled by ${res.extractor} and approved by an officer`}.
            </p>
            <div className="review-grid">
              <div>
                {res.verdict.results.map((r) => (
                  <div key={r.condition_id} className={`cond out-${r.outcome} ${active === r.condition_id ? "on" : ""}`} onClick={() => setActive(r.condition_id)}>
                    <div className="cond-top">
                      <span className={`dotc ${r.outcome}`} />
                      <span className="rule">
                        {human(r.field)} <b>{OPS[r.op] || r.op}</b> {show(r.expected)}
                      </span>
                      <span className="given">{show(r.actual) ?? <em>missing</em>}</span>
                    </div>
                  </div>
                ))}
                {res.verdict.unmapped_conditions.length > 0 && (
                  <p className="notice">Also needs department verification: {res.verdict.unmapped_conditions.map((u) => u.text).join("; ")}</p>
                )}
                <div className="card">
                  <h3>
                    Explanation{" "}
                    <span className="muted small">
                      ({res.explanation.source}
                      {res.explanation.source === "gemini" && res.explanation.verdict_check ? ", verdict check passed" : ""})
                    </span>
                  </h3>
                  {res.explanation.note && <p className="notice">{res.explanation.note}</p>}
                  <pre className="expl">{res.explanation.text}</pre>
                </div>
              </div>
              <div className="sticky">
                <h3>Cited clauses</h3>
                <SourceViewer source={source} marks={marks} active={active} onPick={setActive} />
              </div>
            </div>
            <p className="muted small">{res.verdict.disclaimer}</p>
          </div>
        )}
        {allResults && !res && (
          <div className="all-results">
            <h2>Results across {allResults.total_schemes} schemes</h2>
            {allResults.eligible.length > 0 && (
              <div className="card">
                <h3 className="pass">✓ Eligible ({allResults.eligible.length})</h3>
                {allResults.eligible.map(r => (
                  <div key={r.scheme_id} className="all-row ok">
                    <strong>{r.scheme_name}</strong>
                    {r.benefit && <span className="muted small"> — {r.benefit}</span>}
                  </div>
                ))}
              </div>
            )}
            {allResults.needs_info.length > 0 && (
              <div className="card">
                <h3 className="amb">? Needs more info ({allResults.needs_info.length})</h3>
                {allResults.needs_info.map(r => (
                  <div key={r.scheme_id} className="all-row amb">
                    <strong>{r.scheme_name}</strong>
                    <span className="muted small"> — missing: {r.missing_fields.join(", ")}</span>
                  </div>
                ))}
              </div>
            )}
            {allResults.not_eligible.length > 0 && (
              <div className="card">
                <h3 className="fail">✗ Not eligible ({allResults.not_eligible.length})</h3>
                {allResults.not_eligible.map(r => (
                  <div key={r.scheme_id} className="all-row bad">
                    <strong>{r.scheme_name}</strong>
                    <span className="muted small"> — failed on: {r.failed_conditions.join(", ")}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
