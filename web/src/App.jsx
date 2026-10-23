import React, { useEffect, useRef, useState } from "react";
import { api, getToken, setToken } from "./api.js";
import Hero, { ClauseToVerdict } from "./Hero.jsx";
import { AIRoles, Rulebook } from "./Landing.jsx";
import PhotoBand, { usePhotos } from "./Photos.jsx";
import Compile from "./Compile.jsx";
import Check from "./Check.jsx";
import Evaluation from "./Evaluation.jsx";
import ChatWidget from "./ChatWidget.jsx";

const TABS = [
  { id: "check", label: "Check eligibility", who: "For applicants and Sampark operators" },
  { id: "compile", label: "Compile and review", who: "For scheme officers" },
  { id: "eval", label: "Evidence", who: "Accuracy against hand-labelled rules" },
];

export default function App() {
  const [tab, setTab] = useState("check");
  const [health, setHealth] = useState(null);
  const [token, setTok] = useState(getToken());
  const [overview, setOverview] = useState(null);
  const [scheme, setScheme] = useState(null);
  const bench = useRef(null);
  const photos = usePhotos();

  useEffect(() => {
    api.get("/health").then(setHealth).catch(() => setHealth({ ok: false }));
    api.get("/overview").then(setOverview).catch(() => {});
  }, []);

  const go = (t) => {
    setTab(t);
    bench.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <>
      <Hero onGo={go} health={health} />
      <ClauseToVerdict />
      <PhotoBand photos={photos} />
      <Rulebook
        data={overview}
        onOpen={(id) => {
          setScheme(id);
          go("check");
        }}
      />
      <AIRoles evalData={overview?.eval} />
      <section className="bench" ref={bench} id="workbench">
        <div className="bench-bar">
          <div className="tabs" role="tablist">
            {TABS.map((t) => (
              <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)}>
                <span>{t.label}</span>
                <small>{t.who}</small>
              </button>
            ))}
          </div>
          <div className="bench-meta">
            {health?.ok && !health.gemini_key && !health.groq_key && <span className="warn-chip">No API key set: compiling uses saved results only</span>}
            {tab === "compile" && (
              <label className="token">
                Officer token
                <input
                  value={token}
                  onChange={(e) => {
                    setTok(e.target.value);
                    setToken(e.target.value);
                  }}
                />
              </label>
            )}
          </div>
        </div>
        <div className="bench-body">
          {tab === "compile" && <Compile />}
          {tab === "check" && <Check initial={scheme} />}
          {tab === "eval" && <Evaluation />}
        </div>
      </section>
      <footer className="foot">
        <p>
          Paatrata is a prototype. Its answers are informational and are not official eligibility decisions. Scheme texts in this demo
          are secondary summaries; test applicants are synthetic.
        </p>
        <p>
          Open source under Apache-2.0. Illustration and textures are original
          {photos.length > 0 ? "; photographs are credited where they appear, under their own licences." : "."}
        </p>
      </footer>
      <ChatWidget />
    </>
  );
}
