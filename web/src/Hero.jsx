import React, { useEffect, useRef, useState } from "react";
import Facade from "./Facade.jsx";
import { LiveCheck } from "./Landing.jsx";

export default function Hero({ onGo, health }) {
  return (
    <header className="hero">
      <Facade />
      <div className="hero-inner">
        <nav className="hero-nav">
          <span className="wordmark" aria-label="Paatrata, पात्रता">
            <span className="wm-en">Paatrata</span>
            <span className="wm-rule" aria-hidden="true" />
            <span className="wm-hi" lang="hi">पात्रता</span>
            <span className="wm-gloss">eligibility</span>
          </span>
          <span className={`api ${health?.ok ? "up" : "down"}`}>{health?.ok ? "Service running" : "Service offline"}</span>
        </nav>
        <div className="hero-copy">
          <p className="place">Chandigarh welfare schemes</p>
          <h1>Welfare rules anyone can check.</h1>
          <p className="lede">
            Paatrata reads a scheme's notification, turns each eligibility clause into a tested rule that an officer approves, and
            answers every applicant the same way, with the clause it rests on.
          </p>
          <div className="cta">
            <button className="btn-solid" onClick={() => onGo("check")}>
              Check eligibility
            </button>
            <button className="btn-line" onClick={() => onGo("compile")}>
              Compile a scheme
            </button>
          </div>
          <p className="powered">Reads documents with Gemini, Groq, and Gemma 4. Decides with plain, auditable code.</p>
        </div>
        <LiveCheck />
      </div>
    </header>
  );
}

// One orchestrated moment: a real clause becomes a rule, the rule meets an applicant, the verdict cites the clause.
export function ClauseToVerdict() {
  const ref = useRef(null);
  const [play, setPlay] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || !("IntersectionObserver" in window)) return setPlay(true);
    const io = new IntersectionObserver(([e]) => e.isIntersecting && (setPlay(true), io.disconnect()), { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <section className={`flow ${play ? "play" : ""}`} ref={ref} aria-label="How a clause becomes an answer">
      <div className="flow-head">
        <h2>How one clause becomes an answer</h2>
        <p>Old Age Pension, Chandigarh. The model reads once; after that, code decides.</p>
      </div>
      <ol className="flow-steps">
        <li className="step s1">
          <span className="step-name">The notification says</span>
          <div className="clause-paper">
            <p>
              1. The <mark>family annual income of the applicant should not exceed Rs. 1,50,000.</mark>
            </p>
            <p>2. The applicant should be 60 years of age or above.</p>
          </div>
        </li>
        <li className="step s2">
          <span className="step-name">Gemini / Groq compiles a rule, quote checked</span>
          <div className="rulecard">
            <code>family_annual_income_inr ≤ 150000</code>
            <span className="cite">quote found in source, page 1</span>
          </div>
        </li>
        <li className="step s3">
          <span className="step-name">An applicant asks</span>
          <div className="applicant">
            <span>Age 64</span>
            <span>Family income ₹1,62,000</span>
            <span>5 years in Chandigarh</span>
          </div>
        </li>
        <li className="step s4">
          <span className="step-name">Code answers, citing the clause</span>
          <div className="stamp">
            <strong>Not eligible</strong>
            <span>Income is above ₹1,50,000 (clause 1)</span>
          </div>
        </li>
      </ol>
    </section>
  );
}
