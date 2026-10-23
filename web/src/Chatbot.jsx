import React, { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

const EXAMPLES = [
  "I am 65 years old, family income is 1.2 lakh, living in Chandigarh for 5 years",
  "मेरी उम्र 45 साल है, आय 80,000 है, मैं विकलांग हूँ",
  "Main ek widow hoon, age 40, income 1 lakh, Chandigarh mein 4 saal se hoon",
  "Am I eligible for old age pension? I'm 58, income 1,40,000",
];

function Bubble({ role, children }) {
  return (
    <div className={`chat-bubble chat-${role}`}>
      <div className="chat-bubble-inner">{children}</div>
    </div>
  );
}

function VerdictCard({ result }) {
  const v = result.verdict;
  const cls = v === "ELIGIBLE" ? "pass" : v === "NOT_ELIGIBLE" ? "fail" : "info";
  return (
    <div className={`chat-verdict ${cls}`}>
      <div className="chat-verdict-head">
        <strong>{result.scheme_name}</strong>
        <span className={`verdict-chip ${cls}`}>{v.replace("_", " ")}</span>
      </div>
      {result.benefit && <p className="chat-benefit">{result.benefit}</p>}
      {result.failed_conditions?.length > 0 && (
        <p className="chat-failed">
          Failed: {result.failed_conditions.join(", ")}
        </p>
      )}
      {result.missing_fields?.length > 0 && (
        <p className="chat-missing">
          Missing info: {result.missing_fields.join(", ")}
        </p>
      )}
      {result.citations?.length > 0 && (
        <details className="chat-citations">
          <summary>Citations ({result.citations.length})</summary>
          <ul>
            {result.citations.map((c, i) => (
              <li key={i}>
                <em>{c.field}</em>: &ldquo;{c.quote}&rdquo;
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export default function Chatbot() {
  const [messages, setMessages] = useState([
    {
      role: "bot",
      content:
        "Namaste! I'm Paatrata's eligibility assistant. Tell me about yourself — age, income, where you live — in any language, and I'll check which Chandigarh welfare schemes you may be eligible for.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottom = useRef(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setLoading(true);
    try {
      const res = await api.post("/chat", { message: text });
      setMessages((m) => [
        ...m,
        {
          role: "bot",
          content: res.reply,
          results: res.results,
          extracted: res.extracted_fields,
        },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          role: "bot",
          content:
            "Sorry, I couldn't process that. The server might be offline or missing its Gemini API key. Try again?",
        },
      ]);
    }
    setLoading(false);
  };

  return (
    <div className="chatbot">
      <div className="chat-messages">
        {messages.map((m, i) => (
          <Bubble key={i} role={m.role}>
            <p>{m.content}</p>
            {m.extracted && Object.keys(m.extracted).length > 0 && (
              <div className="chat-extracted">
                <small>Understood:</small>
                {Object.entries(m.extracted).map(([k, v]) => (
                  <span key={k} className="chat-field-chip">
                    {k}: <strong>{String(v)}</strong>
                  </span>
                ))}
              </div>
            )}
            {m.results?.map((r, j) => (
              <VerdictCard key={j} result={r} />
            ))}
          </Bubble>
        ))}
        {loading && (
          <Bubble role="bot">
            <p className="chat-typing">Checking schemes…</p>
          </Bubble>
        )}
        <div ref={bottom} />
      </div>
      <div className="chat-examples">
        {messages.length <= 1 &&
          EXAMPLES.map((ex, i) => (
            <button
              key={i}
              className="chat-example-btn"
              onClick={() => {
                setInput(ex);
              }}
            >
              {ex}
            </button>
          ))}
      </div>
      <form
        className="chat-input-bar"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Tell me about yourself in any language..."
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
