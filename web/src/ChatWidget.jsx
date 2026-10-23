import React, { useState } from "react";
import Chatbot from "./Chatbot.jsx";

export default function ChatWidget() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {open && (
        <div className="chat-widget-panel">
          <div className="chat-widget-header">
            <span>Paatrata Assistant</span>
            <button className="chat-widget-close" onClick={() => setOpen(false)} aria-label="Close chat">✕</button>
          </div>
          <Chatbot />
        </div>
      )}
      <button
        className={`chat-fab ${open ? "chat-fab-hidden" : ""}`}
        onClick={() => setOpen(true)}
        aria-label="Open chat"
        title="Ask about eligibility in any language"
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
      </button>
    </>
  );
}
