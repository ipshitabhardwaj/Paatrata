import React from "react";
import { createRoot } from "react-dom/client";
// Self-hosted fonts: the demo works offline.
import "@fontsource-variable/archivo/standard.css";
import "@fontsource/tiro-devanagari-hindi/400.css";
import "@fontsource/noto-sans-gurmukhi/400.css";
import "@fontsource/noto-sans-gurmukhi/600.css";
import App from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(<App />);
