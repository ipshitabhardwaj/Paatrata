import React, { useEffect, useMemo, useRef } from "react";

// Renders the source document page by page and highlights every cited quote.
// `marks` = [{ id, quote, page, tone }]; `active` = id to scroll to and emphasise.
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function quoteRegex(quote) {
  const words = quote.trim().split(/\s+/).filter(Boolean).map(escapeRe);
  if (!words.length) return null;
  return new RegExp(words.join("\\s+"), "i");
}

function highlightPage(text, marks) {
  // find non-overlapping spans for each mark on this page
  const spans = [];
  for (const m of marks) {
    const re = quoteRegex(m.quote);
    if (!re) continue;
    const hit = re.exec(text);
    if (!hit) continue;
    const start = hit.index;
    const end = start + hit[0].length;
    if (spans.some((s) => start < s.end && end > s.start)) {
      // overlapping quote (e.g. same sentence cited twice): attach id to existing span
      const s = spans.find((x) => start < x.end && end > x.start);
      s.ids.push(m.id);
      continue;
    }
    spans.push({ start, end, ids: [m.id], tone: m.tone });
  }
  spans.sort((a, b) => a.start - b.start);
  const out = [];
  let pos = 0;
  spans.forEach((s, i) => {
    if (s.start > pos) out.push(text.slice(pos, s.start));
    out.push({ text: text.slice(s.start, s.end), ids: s.ids, tone: s.tone, key: i });
    pos = s.end;
  });
  if (pos < text.length) out.push(text.slice(pos));
  return out;
}

export default function SourceViewer({ source, marks, active, onPick }) {
  const box = useRef(null);
  const pages = source?.pages || [];
  const rendered = useMemo(
    () => pages.map((t, i) => highlightPage(t, marks.filter((m) => !m.page || m.page === i + 1 || pages.length === 1))),
    [pages, marks]
  );

  useEffect(() => {
    if (!active || !box.current) return;
    const el = box.current.querySelector(`[data-ids~="${active}"]`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [active]);

  if (!source) return <div className="source empty-src">No source text stored for this version.</div>;
  return (
    <div className="source" ref={box}>
      <div className="source-head">
        <span>{source.title}</span>
        <span className={`badge ${source.is_primary_source ? "verified" : "unverified"}`}>
          {source.is_primary_source ? "primary source" : "secondary source"}
        </span>
      </div>
      {source.url && (
        <a className="small" href={source.url} target="_blank" rel="noreferrer">
          {source.url}
        </a>
      )}
      {rendered.map((parts, i) => (
        <div key={i} className="page">
          {pages.length > 1 && <div className="page-no">Page {i + 1}</div>}
          <pre>
            {parts.map((p, j) =>
              typeof p === "string" ? (
                p
              ) : (
                <mark
                  key={j}
                  data-ids={p.ids.join(" ")}
                  className={`${p.tone || ""} ${p.ids.includes(active) ? "on" : ""}`}
                  onClick={() => onPick && onPick(p.ids[0])}
                  title={p.ids.join(", ")}
                >
                  {p.text}
                  <sup>{p.ids.join(",")}</sup>
                </mark>
              )
            )}
          </pre>
        </div>
      ))}
    </div>
  );
}
