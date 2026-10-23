import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import SourceViewer from "./SourceViewer.jsx";

const fmt = (v) =>
  Array.isArray(v) ? v.join(", ") : typeof v === "number" ? v.toLocaleString("en-IN") : typeof v === "boolean" ? (v ? "yes" : "no") : String(v);
const OPS = { ">=": "≥", "<=": "≤", ">": ">", "<": "<", "==": "=", "!=": "≠", in: "in", not_in: "not in" };
const human = (f) => f.replace(/_/g, " ").replace(" inr", " (₹)").replace(" in jurisdiction", " in UT");

export default function Compile() {
  const [schemes, setSchemes] = useState([]);
  const [versions, setVersions] = useState({});
  const [vid, setVid] = useState(null);
  const [err, setErr] = useState("");

  const refresh = async () => {
    const s = await api.get("/schemes");
    setSchemes(s);
    const all = {};
    await Promise.all(s.map(async (x) => (all[x.id] = (await api.get(`/schemes/${x.id}`)).versions)));
    setVersions(all);
  };
  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
  }, []);

  return (
    <div className="split">
      <aside>
        <CompileForm
          onDone={async (r) => {
            await refresh();
            setVid(r.version_id);
          }}
        />
        <h3>Rulebook</h3>
        {err && <pre className="error">{err}</pre>}
        {schemes.length === 0 && <p className="muted">No schemes yet.</p>}
        {schemes.map((s) => (
          <div key={s.id} className="scheme">
            <div className="scheme-name">{s.name}</div>
            <ul>
              {(versions[s.id] || []).map((v) => (
                <li key={v.id}>
                  <button className={`vbtn ${vid === v.id ? "sel" : ""}`} onClick={() => setVid(v.id)}>
                    <span>v{v.version}</span>
                    <span className={`badge ${v.status}`}>{v.status}</span>
                    <span className="muted small">{v.extractor === "gold" ? "hand-labelled" : v.extractor.split(":")[0]}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </aside>
      <section>{vid ? <VersionView key={vid} vid={vid} onChange={refresh} /> : <Empty />}</section>
    </div>
  );
}

function Empty() {
  return (
    <div className="empty">
      <div className="empty-icon">&#9881;</div>
      <h2>Compile a scheme</h2>
      <ol className="steps">
        <li>
          <b>Extract.</b> Gemini (or Groq/Gemma) reads the notification into a fixed rule schema, quoting the source for every condition.
        </li>
        <li>
          <b>Validate.</b> Code rejects any condition whose quote is not in the document, or whose value doesn't parse.
        </li>
        <li>
          <b>Review.</b> A second pass looks for missing, misread and ambiguous conditions.
        </li>
        <li>
          <b>Approve.</b> An officer answers every open question. Only approved rules answer citizens, deterministically.
        </li>
      </ol>
      <p className="muted">Pick a version on the left, or compile a new source document above.</p>
    </div>
  );
}

function CompileForm({ onDone }) {
  const [file, setFile] = useState(null);
  const [text, setText] = useState("");
  const [backend, setBackend] = useState("gemini");
  const [schemeId, setSchemeId] = useState("");
  const [review, setReview] = useState(true);
  const [busy, setBusy] = useState(false);
  const [secs, setSecs] = useState(0);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!busy) return;
    setSecs(0);
    const t = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [busy]);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    const fd = new FormData();
    if (file) fd.append("file", file);
    else fd.append("text", text);
    fd.append("backend", backend);
    fd.append("review", review ? "true" : "false");
    if (schemeId) fd.append("scheme_id", schemeId);
    try {
      onDone(await api.form("/compile", fd));
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card" onSubmit={submit}>
      <h3>Compile a scheme document</h3>
      <label>
        Source (PDF or .txt)
        <input type="file" accept=".pdf,.txt,.md" onChange={(e) => setFile(e.target.files[0] || null)} />
      </label>
      {!file && (
        <label>
          …or paste official text
          <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} />
        </label>
      )}
      <div className="row">
        <label>
          Model
          <select value={backend} onChange={(e) => setBackend(e.target.value)}>
            <option value="gemini">Gemini</option>
            <option value="groq">Groq (Llama 3.1)</option>
            <option value="gemma-studio">Gemma 4 (AI Studio)</option>
            <option value="ollama">Gemma 4 (local)</option>
          </select>
        </label>
        <label>
          Scheme id
          <input placeholder="auto from sources.csv" value={schemeId} onChange={(e) => setSchemeId(e.target.value)} />
        </label>
      </div>
      <label className="check">
        <input type="checkbox" checked={review} onChange={(e) => setReview(e.target.checked)} /> Second-pass review (Gemini)
      </label>
      <button disabled={busy || (!file && !text.trim())}>
        {busy ? `Reading the document… ${secs}s` : "Compile"}
      </button>
      {busy && <p className="muted small">Extraction plus review usually takes 20–60 s on the free tier. Cached sources return instantly.</p>}
      {err && <pre className="error">{err}</pre>}
    </form>
  );
}

function VersionView({ vid, onChange }) {
  const [v, setV] = useState(null);
  const [tests, setTests] = useState(null);
  const [msg, setMsg] = useState("");
  const [answers, setAnswers] = useState({});
  const [active, setActive] = useState(null);

  const load = async () => {
    setV(await api.get(`/versions/${vid}`));
    setTests(await api.get(`/versions/${vid}/tests`));
  };
  useEffect(() => {
    load().catch((e) => setMsg(e.message));
  }, [vid]);
  if (!v) return <p className="muted">Loading…</p>;

  const r = v.rules;
  const draft = v.status === "draft";
  const act = async (fn) => {
    setMsg("");
    try {
      await fn();
      await load();
      await onChange();
    } catch (e) {
      setMsg(e.message);
    }
  };
  const groups = Object.fromEntries(r.groups.map((g) => [g.id, g]));
  const rejected = v.issues.filter((i) => i.level === "error");
  const reviewer = v.issues.filter((i) => i.code.startsWith("review") || i.message.startsWith("[reviewer]"));
  const other = v.issues.filter((i) => i.level !== "error" && !reviewer.includes(i) && i.code !== "ambiguity");
  const marks = [
    ...r.conditions.map((c) => ({ id: c.id, quote: c.citation.quote, page: c.citation.page, tone: c.ambiguity && !c.ambiguity_resolution ? "amb" : "" })),
    ...r.unmapped_conditions.map((u, i) => ({ id: `u${i + 1}`, quote: u.quote, page: u.page, tone: "unmapped" })),
  ];

  return (
    <div>
      <div className="vhead">
        <div>
          <h2>{r.scheme_name}</h2>
          <p className="muted">
            Version {v.version} <span className={`badge ${v.status}`}>{v.status}</span>{" "}
            {v.extractor === "gold" ? "Hand-labelled reference rules." : `Extracted by ${v.extractor}.`}
            {r.benefit_summary && <> Benefit: {r.benefit_summary}.</>}
          </p>
        </div>
        {draft && (
          <button className="primary" disabled={v.open_ambiguities.length > 0} onClick={() => act(() => api.post(`/versions/${vid}/approve`, {}, true))}>
            {v.open_ambiguities.length ? `${v.open_ambiguities.length} question(s) open` : `Approve v${v.version}`}
          </button>
        )}
      </div>
      {msg && <pre className="error">{msg}</pre>}

      <div className="review-grid">
        <div>
          <h3>Conditions ({r.conditions.length})</h3>
          {r.groups
            .filter((g) => g.logic === "ANY" || g.parent)
            .map((g) => (
              <p key={g.id} className="muted small">
                Group <code>{g.id}</code>: {g.logic === "ANY" ? "any one of its conditions is enough" : "all must hold"}
                {g.parent ? ` (inside ${g.parent})` : " (top level)"}
              </p>
            ))}
          {r.conditions.map((c) => (
            <div
              key={c.id}
              className={`cond ${active === c.id ? "on" : ""} ${c.ambiguity && !c.ambiguity_resolution ? "has-q" : ""}`}
              onClick={() => setActive(c.id)}
            >
              <div className="cond-top">
                <span className="cid">{c.id}</span>
                <span className="rule">
                  {human(c.field)} <b>{OPS[c.op] || c.op}</b> {fmt(c.value)}
                </span>
                {groups[c.group]?.logic === "ANY" && <span className="badge">ANY</span>}
                <span className={`badge ${c.citation.verified || v.extractor === "gold" ? "verified" : "unverified"}`}>
                  p.{c.citation.page} {c.citation.verified ? "quote ✓" : v.extractor === "gold" ? "gold" : "unverified"}
                </span>
                <span className="conf" title="model confidence">
                  {Math.round((c.confidence ?? 1) * 100)}%
                </span>
                {draft && (
                  <button
                    className="link small"
                    onClick={(e) => {
                      e.stopPropagation();
                      act(() => api.del(`/versions/${vid}/conditions/${c.id}`));
                    }}
                  >
                    remove
                  </button>
                )}
              </div>
              {c.ambiguity && (
                <div className="q" onClick={(e) => e.stopPropagation()}>
                  <b>Question for officer:</b> {c.ambiguity}
                  {c.ambiguity_resolution ? (
                    <div className="resolved">Resolved: {c.ambiguity_resolution}</div>
                  ) : (
                    draft && (
                      <div className="resolve">
                        <input
                          placeholder="Answer (cite the clarification you rely on)"
                          value={answers[c.id] || ""}
                          onChange={(e) => setAnswers({ ...answers, [c.id]: e.target.value })}
                        />
                        <button
                          disabled={!answers[c.id]}
                          onClick={() => act(() => api.post(`/versions/${vid}/conditions/${c.id}/resolve`, { resolution: answers[c.id] }, true))}
                        >
                          Resolve
                        </button>
                      </div>
                    )
                  )}
                </div>
              )}
            </div>
          ))}

          {r.unmapped_conditions.length > 0 && (
            <>
              <h3>Not computable: needs human verification</h3>
              {r.unmapped_conditions.map((u, i) => (
                <div key={i} className="cond unmapped" onClick={() => setActive(`u${i + 1}`)}>
                  <span className="cid">u{i + 1}</span> {u.text} <span className="muted small">({u.reason})</span>
                </div>
              ))}
            </>
          )}

          {rejected.length > 0 && (
            <IssueList title="Rejected by the validator" items={rejected} cls="err" />
          )}
          {reviewer.length > 0 && <IssueList title="Second-pass review" items={reviewer} />}
          {other.length > 0 && <IssueList title="Other notes" items={other} />}
          {tests && <Tests tests={tests} />}
        </div>
        <div className="sticky">
          <h3>Source</h3>
          <SourceViewer source={v.source} marks={marks} active={active} onPick={setActive} />
        </div>
      </div>
    </div>
  );
}

function IssueList({ title, items, cls = "" }) {
  return (
    <>
      <h3>{title}</h3>
      <ul className="issues">
        {items.map((i, k) => (
          <li key={k} className={cls}>
            <code>{i.code}</code> {i.condition_id && <b>{i.condition_id}</b>} {i.message}
          </li>
        ))}
      </ul>
    </>
  );
}

function Tests({ tests }) {
  const [show, setShow] = useState(false);
  const rows = tests.gold || tests.self;
  return (
    <div className="card">
      <h3>Boundary tests</h3>
      {tests.gold_total !== undefined ? (
        <p>
          Against hand-labelled gold rules:{" "}
          <b className={tests.gold_passed === tests.gold_total ? "pass" : "fail"}>
            {tests.gold_passed}/{tests.gold_total} pass
          </b>
        </p>
      ) : (
        <p className="muted small">These are the gold rules themselves; cases below are for review.</p>
      )}
      <button className="link" onClick={() => setShow(!show)}>
        {show ? "Hide" : "Show"} {rows.length} generated cases
      </button>
      {show && (
        <table>
          <thead>
            <tr>
              <th>Case</th>
              <th>Verdict under these rules</th>
              {tests.gold && <th>Gold</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.test.id} className={t.passed ? "" : "failrow"}>
                <td>{t.test.description}</td>
                <td>{t.actual}</td>
                {tests.gold && <td>{t.test.expected}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
