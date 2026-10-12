// Builds Paatrata.pptx in the visual language of the web app (Chandigarh concrete + Le Corbusier colours).
//
//   cd deck
//   npm install
//   node build.js            -> Paatrata.pptx
//
// If ../evaluation/results/latest.json exists (python -m evaluation.run_eval --live ...), the
// Evaluation slide is filled with those measured numbers. Otherwise it says the run is pending.
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const A = (f) => path.join(__dirname, "assets", f);
const RESULTS = path.join(__dirname, "..", "evaluation", "results", "latest.json");

// ---------------------------------------------------------------- palette (same tokens as web/src/styles.css)
const K = {
  paper: "E8E6E1", slab: "F7F6F3", ink: "22262B", ink2: "5A5F66", line: "CFCBC3",
  red: "C23B22", redSoft: "F6DFD9", ochre: "E0A020", ochreSoft: "F8EBC8",
  cobalt: "2350A0", cobaltSoft: "DFE7F5", green: "2E7D4F", greenSoft: "DCEEE3",
  concrete: "383C41", light: "ECEAE6", lightMuted: "C4C1BB", violet: "6B5BA8",
};
const THEME = {
  name: "Paatrata Concrete",
  headFontFace: "Arial Black",
  bodyFontFace: "Arial",
  colors: {
    dk1: K.ink, lt1: "FFFFFF", dk2: K.concrete, lt2: K.paper,
    accent1: K.cobalt, accent2: K.red, accent3: K.ochre, accent4: K.green, accent5: K.ink2, accent6: K.violet,
    hlink: K.cobalt, folHlink: K.violet,
  },
};
const HEAD = THEME.headFontFace;
const BODY = THEME.bodyFontFace;
const PRINT = "Cambria"; // scheme documents look like printed notices, as in the app

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.theme = { headFontFace: HEAD, bodyFontFace: BODY };
pres.title = "Paatrata: welfare rules anyone can check";
pres.author = "Team clawops";
pres.company = "Code for Communities Chandigarh 2026";

// ---------------------------------------------------------------- layouts
const footer = (dark) => ({
  text: {
    text: "Paatrata  |  team clawops  |  Code for Communities Chandigarh 2026",
    options: { x: 0.5, y: 5.22, w: 6.5, h: 0.25, fontFace: BODY, fontSize: 9, color: dark ? K.lightMuted : K.ink2, margin: 0 },
  },
});
const titlePh = (dark) => ({
  placeholder: {
    options: {
      name: "title", type: "title", x: 0.5, y: 0.3, w: 9, h: 0.85, fontFace: HEAD, fontSize: 20, align: "left",
      color: dark ? "FFFFFF" : K.ink, valign: "top", margin: 0, charSpacing: -0.5,
    },
    text: "",
  },
});
pres.defineSlideMaster({
  title: "LIGHT", background: { path: A("bg_light.jpg") },
  objects: [titlePh(false), footer(false)],
  slideNumber: { x: 9.1, y: 5.2, w: 0.4, h: 0.25, fontFace: BODY, fontSize: 9, color: K.ink2, align: "right" },
});
pres.defineSlideMaster({
  title: "DARK", background: { path: A("bg_dark.jpg") },
  objects: [titlePh(true), footer(true)],
  slideNumber: { x: 9.1, y: 5.2, w: 0.4, h: 0.25, fontFace: BODY, fontSize: 9, color: K.lightMuted, align: "right" },
});
pres.defineSlideMaster({ title: "BLANK", background: { color: K.paper }, objects: [] });

// ---------------------------------------------------------------- helpers
const T = (slide, text, o) => slide.addText(text, { isTextBox: true, fontFace: BODY, margin: 0, valign: "top", ...o });
const square = (slide, x, y, color, s = 0.16, name = "square") =>
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w: s, h: s, fill: { color }, line: { color, width: 0 }, objectName: name });
const panel = (slide, x, y, w, h, fill = K.slab, name = "panel") =>
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: K.line, width: 0.75 }, objectName: name });
const credit = (slide, text, x, y, w, dark = false) =>
  T(slide, text, { x, y, w, h: 0.22, fontSize: 8, color: dark ? K.lightMuted : K.ink2, objectName: "photo credit" });

const results = fs.existsSync(RESULTS) ? JSON.parse(fs.readFileSync(RESULTS, "utf8")) : null;
const pct = (x) => (typeof x === "number" ? `${Math.round(x * 100)}%` : "–");

// ================================================================= 1. Title
pres.addSection({ title: "Opening" });
{
  const s = pres.addSlide({ masterName: "BLANK", sectionTitle: "Opening" });
  s.addImage({ path: A("facade.png"), x: 0, y: 0, w: 10, h: 5.625, sizing: { type: "cover", w: 10, h: 5.625 }, altText: "Original illustration of a concrete civic building in Chandigarh with the word Paatrata in Devanagari over its roof" });
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 4.75, h: 5.625, fill: { color: K.paper, transparency: 6 }, line: { color: K.paper, width: 0 }, objectName: "copy panel" });
  square(s, 0.55, 0.62, K.red, 0.18, "red mark");
  T(s, "Chandigarh welfare schemes", { x: 0.85, y: 0.58, w: 3.6, h: 0.3, fontSize: 12, bold: true, color: K.ink });
  T(s, "Paatrata", { x: 0.55, y: 1.05, w: 4, h: 0.5, fontFace: HEAD, fontSize: 20, color: K.red, charSpacing: -0.5 });
  T(s, "Welfare rules anyone can check", { x: 0.55, y: 1.55, w: 4.05, h: 1.75, fontFace: HEAD, fontSize: 29, color: K.ink, charSpacing: -1, lineSpacingMultiple: 0.92 });
  T(s, "Gemini reads a scheme's notification once. An officer approves the rules. Code answers every applicant the same way, citing the clause.", { x: 0.55, y: 3.38, w: 3.95, h: 0.8, fontSize: 12.5, color: "30353B" });
  T(s, [
    { text: "Team clawops", options: { bold: true, breakLine: true } },
    { text: "Veydant Bhardwaj  ·  Ipshita Bhardwaj", options: { breakLine: true } },
    { text: "Theme: AI for Digital Public Infrastructure of Chandigarh", options: { breakLine: true, color: K.ink2 } },
    { text: "Bonus: Best Open-Source AI Project", options: { color: K.ink2 } },
  ], { x: 0.55, y: 4.3, w: 4, h: 0.95, fontSize: 10.5, color: K.ink });
  s.addNotes("Paatrata means eligibility. We built a compiler for welfare-scheme rules: Gemini reads the notification once, an officer approves, and plain code answers every applicant the same way with the clause it rests on.");
}

// ================================================================= 2. Problem
pres.addSection({ title: "Problem" });
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "Problem" });
  s.addText("Eligibility rules exist only as prose, and every channel re-reads them by hand", { placeholder: "title" });
  // the clause, printed like a notice
  panel(s, 0.5, 1.35, 3.9, 2.55, "FBFAF6", "notice paper");
  T(s, "Old Age Pension, Chandigarh: eligibility", { x: 0.75, y: 1.55, w: 3.4, h: 0.3, fontSize: 10, color: K.ink2 });
  T(s, [
    { text: "1. The ", options: {} },
    { text: "family annual income", options: { highlight: "F5D77E" } },
    { text: " of the applicant should not exceed Rs. 1,50,000.", options: { breakLine: true } },
    { text: "2. The applicant should be 60 years of age or above.", options: { breakLine: true } },
    { text: "3. … residing in Chandigarh UT for ", options: {} },
    { text: "more than 3 years", options: { highlight: "F5D77E" } },
    { text: ".", options: {} },
  ], { x: 0.75, y: 1.9, w: 3.45, h: 1.6, fontFace: PRINT, fontSize: 13, color: "2A2D31", paraSpaceAfter: 6 });
  T(s, "Who is \"family\"? Is 3 years enough? Each channel decides on its own.", { x: 0.5, y: 4.05, w: 3.9, h: 0.5, fontSize: 11, italic: true, color: K.ink2 });

  const items = [
    ["Answers drift", "Two channels, or one chatbot asked twice, give different verdicts for the same person."],
    ["No clause behind it", "A citizen told \"not eligible\" rarely learns which clause decided it."],
    ["Guesses stay hidden", "Undefined terms and unclear ranges are interpreted silently and never recorded."],
    ["Updates go stale", "A circular changes a limit; every downstream copy must be found and fixed by hand."],
  ];
  items.forEach(([h, b], i) => {
    const x = 4.75 + (i % 2) * 2.45, y = 1.35 + Math.floor(i / 2) * 1.6;
    panel(s, x, y, 2.3, 1.48, K.slab, `failure ${i + 1}`);
    square(s, x + 0.18, y + 0.22, K.red, 0.16, "fails mark");
    T(s, h, { x: x + 0.45, y: y + 0.17, w: 1.75, h: 0.28, fontSize: 12, bold: true, color: K.ink });
    T(s, b, { x: x + 0.18, y: y + 0.6, w: 1.98, h: 0.8, fontSize: 10.5, color: K.ink2 });
  });
  s.addNotes("A notification is prose. Portals, Sampark counters, helpdesks and chatbots each turn it into their own logic. The result: inconsistent answers, no traceability, silent guesses on ambiguous wording, and slow updates when a circular changes a limit.");
}

// ================================================================= 3. Evidence and users
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "Problem" });
  s.addText("Chandigarh runs two rulebooks, and every state has the same problem", { placeholder: "title" });
  s.addImage({ path: A("capitol.jpg"), x: 0.5, y: 1.3, w: 4.3, h: 3.25, sizing: { type: "cover", w: 4.3, h: 3.25 }, altText: "Palace of Assembly, Chandigarh, reflected in its pool" });
  credit(s, "Palace of Assembly, Chandigarh. Photo: duncid, CC BY-SA 2.0, via Wikimedia Commons", 0.5, 4.6, 4.3, true);
  const facts = [
    ["Own schemes + central schemes", "The UT administration runs its own pensions and child-support schemes next to central ones."],
    ["6 schemes, 30 conditions", "Chandigarh schemes already compiled into Paatrata's rulebook, each condition tied to its sentence."],
    ["5,000+ schemes across India", "Listed by one provider alone (Haqdarshak, via NITI Aayog Frontier Tech). The same bottleneck repeats in every state."],
  ];
  facts.forEach(([h, b], i) => {
    const y = 1.3 + i * 0.95;
    square(s, 5.15, y + 0.06, [K.ochre, K.green, K.cobalt][i], 0.16);
    T(s, h, { x: 5.45, y, w: 4.05, h: 0.3, fontSize: 14, bold: true, color: "FFFFFF" });
    T(s, b, { x: 5.45, y: y + 0.32, w: 4.05, h: 0.55, fontSize: 10.5, color: K.lightMuted });
  });
  T(s, [
    { text: "Who uses it  ", options: { bold: true, color: "FFFFFF" } },
    { text: "Scheme officers · Sampark / e-District operators · Citizens · Portal builders", options: { color: K.light } },
  ], { x: 5.15, y: 4.25, w: 4.35, h: 0.5, fontSize: 10.5 });
  s.addNotes("Chandigarh is a sharp case: as a Union Territory it administers its own pensions and child schemes beside central ones. We compiled six of them. Nationally, one provider lists more than five thousand schemes, so the document-to-rules bottleneck repeats everywhere.");
}

// ================================================================= 4. Gap
pres.addSection({ title: "Solution" });
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "Solution" });
  s.addText("Existing tools answer citizens; nobody verifies the rules they run on", { placeholder: "title" });
  const hdr = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: K.ink } } });
  const rows = [
    [hdr(""), hdr("Typical scheme chatbot"), hdr("Paatrata")],
    ["When the model runs", "On every question", "Once per document"],
    ["Who decides eligibility", "The model, each time", "Deterministic code"],
    ["Same question twice", "Can differ", "Always identical"],
    ["Why this answer?", "Free-text reasoning", "Exact clause, page and quote"],
    ["Unclear wording", "Silently guessed", "A question that blocks approval"],
    ["Missing applicant facts", "Often guessed", "\"Needs information\", naming the fact"],
    ["Rule changes", "Re-prompt and hope", "New version, re-run boundary tests"],
  ].map((r, i) => (i === 0 ? r : r.map((c, j) => ({ text: c, options: { bold: j === 0, color: j === 2 ? K.green : K.ink, fill: { color: i % 2 ? K.slab : "FFFFFF" } } }))));
  s.addTable(rows, { x: 0.5, y: 1.3, w: 9, colW: [2.4, 3.1, 3.5], fontFace: BODY, fontSize: 11.5, rowH: 0.42, border: { type: "solid", color: K.line, pt: 0.75 }, valign: "middle", margin: [0, 0.12, 0, 0.12] });
  T(s, "myScheme, Haqdarshak and Indus Action's eligibility engines do discovery well. Paatrata works one step upstream: document → verified, executable rules.", { x: 0.5, y: 4.75, w: 9, h: 0.4, fontSize: 10.5, color: K.ink2 });
  s.addNotes("We are not another scheme chatbot. A chatbot asks the model every time. Paatrata compiles once, then code decides, so answers are identical, cited, and ambiguity becomes an explicit question.");
}

// ================================================================= 5. Solution flow
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "Solution" });
  s.addText("Compile once. Decide with code", { placeholder: "title" });
  const steps = [
    ["Gemini extracts", "Each clause becomes field, operator, value, verbatim quote, page, and a question if unclear.", K.cobalt, "Google AI"],
    ["Code validates", "Rejects any condition whose quote is not in the document; parses ₹1.5 lakh → 150000.", K.ink, "Code"],
    ["Gemini reviews", "Second pass finds missing, misread and ambiguous conditions, each quoted.", K.cobalt, "Google AI"],
    ["Officer approves", "Answers every question, checks boundary tests, approves a version.", K.ochre, "Human"],
    ["Code decides", "Eligible, Not eligible or Needs information, with the clause for every condition.", K.green, "Code"],
  ];
  const w = 1.66, gap = 0.17;
  steps.forEach(([h, b, c, who], i) => {
    const x = 0.5 + i * (w + gap), y = 1.45;
    panel(s, x, y, w, 2.85, K.slab, `step ${i + 1}`);
    s.addShape(pres.shapes.RECTANGLE, { x: x + 0.15, y: y + 0.18, w: 0.42, h: 0.42, fill: { color: c }, line: { color: c, width: 0 }, objectName: "step number block" });
    T(s, String(i + 1), { x: x + 0.15, y: y + 0.18, w: 0.42, h: 0.42, fontFace: HEAD, fontSize: 16, color: "FFFFFF", align: "center", valign: "middle" });
    T(s, h, { x: x + 0.15, y: y + 0.75, w: w - 0.3, h: 0.5, fontSize: 13, bold: true, color: K.ink });
    T(s, b, { x: x + 0.15, y: y + 1.25, w: w - 0.3, h: 1.25, fontSize: 10, color: K.ink2 });
    T(s, who, { x: x + 0.15, y: y + 2.5, w: w - 0.3, h: 0.25, fontSize: 9, bold: true, color: c === K.ink ? K.ink2 : c });
    if (i < steps.length - 1) s.addShape(pres.shapes.RIGHT_TRIANGLE, { x: x + w + 0.035, y: y + 1.3, w: 0.1, h: 0.2, fill: { color: K.ink2 }, line: { color: K.ink2, width: 0 }, rotate: 0, objectName: "arrow" });
  });
  T(s, "The model reads once. Every answer after that comes from officer-approved rules run by plain, testable code.", { x: 0.5, y: 4.5, w: 9, h: 0.4, fontSize: 12, bold: true, color: K.ink });
  s.addNotes("Five steps. Blue is Google AI, grey is code, ochre is the officer, green is the deterministic decision. Note that AI never makes the decision; it only reads and questions the document.");
}

// ================================================================= 6. Live workflow
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "Solution" });
  s.addText("Working prototype: every condition sits beside its sentence", { placeholder: "title" });
  s.addImage({ path: A("ui_compile.png"), x: 0.5, y: 1.25, w: 4.4, h: 3.54, sizing: { type: "contain", w: 4.4, h: 3.54 }, altText: "Officer review screen with conditions beside the highlighted source" });
  s.addImage({ path: A("ui_check.png"), x: 5.1, y: 1.25, w: 4.4, h: 3.88, sizing: { type: "contain", w: 4.4, h: 3.54 }, altText: "Eligibility check screen showing Not eligible with the cited clause" });
  T(s, "Officer review: questions to answer, rejected conditions, boundary tests", { x: 0.5, y: 4.85, w: 4.4, h: 0.3, fontSize: 10, color: K.light });
  T(s, "Eligibility check: verdict, each condition coloured, clause highlighted", { x: 5.1, y: 4.85, w: 4.4, h: 0.3, fontSize: 10, color: K.light });
  s.addNotes("Left: the officer screen. Conditions on the left, the source document on the right with each quote highlighted; an ambiguity question blocks approval; a hallucinated condition was rejected because its quote is not in the document. Right: the citizen check. Not eligible, because income is above 1.5 lakh, with the clause highlighted in red.");
}

// ================================================================= 7. Architecture
pres.addSection({ title: "Technology" });
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "Technology" });
  s.addText("Architecture: one small service, AI only on the authoring path", { placeholder: "title" });
  const box = (x, y, w, h, title, sub, color, name) => {
    s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: color === K.ink ? "FFFFFF" : color === K.cobalt ? K.cobaltSoft : color === K.ochre ? K.ochreSoft : K.greenSoft }, line: { color, width: 1.25 }, objectName: name });
    T(s, title, { x: x + 0.1, y: y + 0.08, w: w - 0.2, h: 0.28, fontSize: 11, bold: true, color: K.ink, align: "center" });
    if (sub) T(s, sub, { x: x + 0.1, y: y + 0.36, w: w - 0.2, h: h - 0.42, fontSize: 9, color: K.ink2, align: "center" });
  };
  const arrow = (x1, y1, x2, y2) => s.addShape(pres.shapes.LINE, { x: x1, y: y1, w: x2 - x1, h: y2 - y1, line: { color: K.ink2, width: 1.25, endArrowType: "triangle" }, objectName: "connector" });
  // authoring row
  T(s, "Authoring path (officer)", { x: 0.5, y: 1.2, w: 3, h: 0.25, fontSize: 10, bold: true, color: K.ink2 });
  box(0.5, 1.5, 1.45, 0.85, "Notification", "PDF or text", K.ink, "notification");
  box(2.2, 1.5, 1.6, 0.85, "Gemini / Gemma 4", "structured extraction", K.cobalt, "extractor");
  box(4.05, 1.5, 1.6, 0.85, "Validator", "vocabulary · units · quote-in-source", K.ink, "validator");
  box(5.9, 1.5, 1.6, 0.85, "Gemini review", "missing · misread · ambiguous", K.cobalt, "review");
  box(7.75, 1.5, 1.75, 0.85, "Officer approves", "answers questions, tests", K.ochre, "officer");
  arrow(1.95, 1.92, 2.2, 1.92); arrow(3.8, 1.92, 4.05, 1.92); arrow(5.65, 1.92, 5.9, 1.92); arrow(7.5, 1.92, 7.75, 1.92);
  // rulebook under the officer
  box(7.75, 2.42, 1.75, 0.55, "Rulebook", "versioned, SQLite", K.ink, "rulebook");
  arrow(8.62, 2.35, 8.62, 2.42);
  // approved rules feed the evaluator: elbow above the query row
  s.addShape(pres.shapes.LINE, { x: 3.3, y: 2.7, w: 4.45, h: 0, line: { color: K.ink2, width: 1.25 }, objectName: "rules to evaluator" });
  arrow(3.3, 2.7, 3.3, 3.2);
  // query row
  T(s, "Query path (citizen, operator): no AI", { x: 0.5, y: 2.6, w: 2.6, h: 0.45, fontSize: 10, bold: true, color: K.ink2 });
  box(0.5, 3.2, 1.45, 0.85, "Applicant details", "web form or API", K.ink, "applicant");
  box(2.2, 3.2, 2.2, 0.85, "Deterministic evaluator", "three-valued logic over ALL/ANY groups", K.green, "evaluator");
  box(4.65, 3.2, 2.2, 0.85, "Verdict + citations", "Eligible · Not eligible · Needs info", K.green, "verdict");
  box(7.1, 3.2, 2.4, 0.85, "Hindi / Punjabi wording", "Gemini, verdict-checked", K.cobalt, "explainer");
  arrow(1.95, 3.62, 2.2, 3.62); arrow(4.4, 3.62, 4.65, 3.62); arrow(6.85, 3.62, 7.1, 3.62);
  T(s, "Interfaces: React web app · FastAPI REST API · paatrata CLI · Python library · Agent Skill. One Docker image, Cloud Run ready.", { x: 0.5, y: 4.4, w: 9, h: 0.35, fontSize: 10.5, color: K.ink });
  s.addNotes("Two paths. Authoring uses Gemini or Gemma, then code validates, Gemini reviews, an officer approves into a versioned rulebook. The query path has no AI at all: a deterministic evaluator returns the verdict with citations; Gemini only rewords it into Hindi or Punjabi and must echo the same verdict.");
}

// ================================================================= 8. Google AI + open source
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "Technology" });
  s.addText("Google AI does the reading. Open weights make it deployable anywhere", { placeholder: "title" });
  const rows = [
    ["Gemini API, structured output", "Clause → typed condition with quote, page, confidence, question"],
    ["Gemini API, second pass", "Finds missing, misread and ambiguous conditions"],
    ["Gemini multimodal", "Reads scanned PDFs that have no text layer"],
    ["Gemini API", "Hindi and Punjabi explanations, checked against the verdict"],
    ["Gemma 4 via AI Studio / Ollama", "Same compiler on open weights, for on-premise departments"],
  ];
  T(s, "Where Google AI works", { x: 0.5, y: 1.25, w: 5.2, h: 0.3, fontSize: 13, bold: true, color: K.ink });
  rows.forEach(([a, b], i) => {
    const y = 1.62 + i * 0.6;
    square(s, 0.5, y + 0.05, K.cobalt, 0.14);
    T(s, a, { x: 0.78, y, w: 4.9, h: 0.25, fontSize: 11, bold: true, color: K.ink });
    T(s, b, { x: 0.78, y: y + 0.25, w: 4.9, h: 0.3, fontSize: 10, color: K.ink2 });
  });
  T(s, "Never: deciding who is eligible. That is always approved rules + code.", { x: 0.5, y: 4.68, w: 5.2, h: 0.3, fontSize: 10.5, bold: true, color: K.red });

  panel(s, 6.05, 1.25, 3.45, 3.75, K.slab, "bonus panel");
  T(s, "Bonus: open-source AI", { x: 6.3, y: 1.42, w: 3.0, h: 0.3, fontSize: 13, bold: true, color: K.ink });
  const bonus = [
    "Gemma 4 (Apache-2.0) as a real extraction backend",
    "Agent Skill in the Agent Skill Open Standard format",
    "paatrata_core: reusable library with schema, validator, evaluator, test generator",
    "Evaluation harness with a public answer-key format",
    "Public GitHub repo, Apache-2.0; 60 offline tests",
  ];
  bonus.forEach((b, i) => {
    const y = 1.85 + i * 0.6;
    square(s, 6.3, y + 0.05, K.green, 0.14);
    T(s, b, { x: 6.55, y, w: 2.8, h: 0.55, fontSize: 10.5, color: K.ink });
  });
  s.addNotes("Gemini does the hard language work and it is measurable. Gemma 4 gives an open-weight path for departments that cannot send documents outside. For the bonus: an Agent Skill, a reusable library, and an evaluation harness, all Apache-2.0.");
}

// ================================================================= 9. Evaluation
pres.addSection({ title: "Evidence" });
{
  const s = pres.addSlide({ masterName: "LIGHT", sectionTitle: "Evidence" });
  s.addText("Measured against hand-labelled rules, versus a plain RAG chatbot", { placeholder: "title" });
  const sum = results?.summary || {};
  const ours = Object.entries(sum).find(([k]) => k.startsWith("paatrata/gemini"))?.[1];
  const rag = Object.entries(sum).find(([k]) => k.startsWith("rag/"))?.[1];
  if (ours) {
    const stats = [
      [pct(ours.decision_accuracy), "decision accuracy, Paatrata with Gemini", K.green],
      [pct(ours.extraction_f1), "condition extraction F1 after validation", K.green],
      [rag ? pct(rag.decision_accuracy) : "–", "decision accuracy, RAG chatbot, same model and documents", K.ink2],
      [rag ? pct(rag.consistency) : "–", "chatbot answers identical when asked again (Paatrata: always)", K.ink2],
    ];
    stats.forEach(([n, l, c], i) => {
      const x = 0.5 + i * 2.27;
      panel(s, x, 1.35, 2.1, 1.9, K.slab, `stat ${i + 1}`);
      T(s, n, { x: x + 0.15, y: 1.5, w: 1.85, h: 0.85, fontFace: HEAD, fontSize: 36, color: c, charSpacing: -1 });
      T(s, l, { x: x + 0.15, y: 2.4, w: 1.85, h: 0.75, fontSize: 10, color: K.ink2 });
    });
    T(s, `${results.n_schemes} Chandigarh schemes · run ${results.generated_at}`, { x: 0.5, y: 3.35, w: 9, h: 0.3, fontSize: 10, color: K.ink2 });
  } else {
    panel(s, 0.5, 1.35, 9, 1.4, K.ochreSoft, "results pending");
    T(s, "Results pending the final evaluation run", { x: 0.75, y: 1.55, w: 8.5, h: 0.4, fontSize: 16, bold: true, color: "6D4B00" });
    T(s, "Run  python -m evaluation.run_eval --live --review  then  node deck/build.js  to fill this slide with measured numbers.", { x: 0.75, y: 2.05, w: 8.5, h: 0.6, fontSize: 12, color: "6D4B00" });
  }
  const metrics = [
    ["Extraction F1", "field, operator, value vs answer key"],
    ["Quotes verified", "model citations found in the document"],
    ["Decision accuracy", "boundary cases + 300 synthetic applicants per scheme"],
    ["Consistency", "same question, repeated runs (baseline)"],
  ];
  metrics.forEach(([h, b], i) => {
    const x = 0.5 + (i % 2) * 4.5, y = 3.75 + Math.floor(i / 2) * 0.5;
    T(s, [{ text: h + "  ", options: { bold: true, color: K.ink } }, { text: b, options: { color: K.ink2 } }], { x, y, w: 4.4, h: 0.4, fontSize: 10.5 });
  });
  T(s, "Applicants are synthetic and answer keys are team-labelled: results measure agreement with those labels, not real-world accuracy.", { x: 0.5, y: 4.78, w: 9, h: 0.35, fontSize: 9.5, italic: true, color: K.ink2 });
  s.addNotes("The baseline uses the same Gemini model and the same documents; the only difference is asking every time versus compiling once. We report extraction F1, verified quotes, decision accuracy and consistency, with honest caveats: synthetic applicants and team-labelled keys.");
}

// ================================================================= 10. Scale and deployment
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "Evidence" });
  s.addText("Pilot in weeks, then scale to any state", { placeholder: "title" });
  T(s, "Pilot in weeks", { x: 0.5, y: 1.25, w: 4.4, h: 0.3, fontSize: 14, bold: true, color: "FFFFFF" });
  const steps = [
    "Collect the department's current notifications",
    "Compile, review and approve with its own officers",
    "Give one helpdesk or Sampark counter the read-only checker",
    "Compare answers with past applications, then widen",
  ];
  steps.forEach((t, i) => {
    const y = 1.7 + i * 0.75;
    s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y, w: 0.42, h: 0.42, fill: { color: K.ochre }, line: { color: K.ochre, width: 0 }, objectName: "pilot step" });
    T(s, String(i + 1), { x: 0.5, y, w: 0.42, h: 0.42, fontFace: HEAD, fontSize: 15, color: K.ink, align: "center", valign: "middle" });
    T(s, t, { x: 1.1, y: y + 0.03, w: 3.8, h: 0.5, fontSize: 12, color: K.light });
  });
  s.addImage({ path: A("open-hand.jpg"), x: 5.25, y: 1.25, w: 4.25, h: 2.0, sizing: { type: "cover", w: 4.25, h: 2.0 }, altText: "Open Hand Monument, Chandigarh" });
  credit(s, "Open Hand Monument. Photo: Raakesh Blokhra, CC BY-SA 2.0, via Wikimedia Commons", 5.25, 3.28, 4.25, true);
  T(s, [
    { text: "Reach across India", options: { bold: true, color: "FFFFFF", breakLine: true } },
    { text: "Every state and ministry publishes schemes as notifications. The vocabulary, compiler and engine are scheme-agnostic; Gemini reads Hindi and other Indian languages; one Docker image runs on Cloud Run.", options: { color: K.light } },
  ], { x: 5.25, y: 3.6, w: 4.25, h: 1.4, fontSize: 11, paraSpaceAfter: 4 });
  s.addNotes("Deployability: a department uploads notifications it already publishes; officers approve; the rules are served by an API. No government integration needed for a pilot. Scale: nothing in the engine is Chandigarh-specific.");
}

// ================================================================= 11. Roadmap and close
pres.addSection({ title: "Close" });
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "Close" });
  s.addText("Next: from six schemes to a shared, verified rulebook", { placeholder: "title" });
  const road = [
    ["Circular delta", "Compile a new circular against the approved rules; show exactly what changed and for whom."],
    ["Official notifications", "Department PDFs for every Chandigarh scheme, including Hindi-only sources."],
    ["Gemma 4 measured", "Published on-premise accuracy for departments that keep documents in-house."],
    ["Every language, every counter", "Hindi and Punjabi across the interface; voice input at Sampark counters."],
  ];
  road.forEach(([h, b], i) => {
    const x = 0.5 + (i % 2) * 4.55, y = 1.3 + Math.floor(i / 2) * 1.15;
    square(s, x, y + 0.06, [K.cobalt, K.ochre, K.green, K.red][i], 0.16);
    T(s, h, { x: x + 0.3, y, w: 4.0, h: 0.3, fontSize: 13, bold: true, color: "FFFFFF" });
    T(s, b, { x: x + 0.3, y: y + 0.33, w: 4.0, h: 0.7, fontSize: 10.5, color: K.lightMuted });
  });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 3.75, w: 9, h: 1.2, fill: { color: K.paper }, line: { color: K.paper, width: 0 }, objectName: "closing band" });
  T(s, "The model reads once. Code decides every time.", { x: 0.75, y: 3.9, w: 8.5, h: 0.5, fontFace: HEAD, fontSize: 22, color: K.ink, charSpacing: -0.5 });
  T(s, "Live: paatrata.onrender.com  |  github.com/ipshitabhardwaj/Paatrata  |  Apache-2.0  |  team clawops", { x: 0.75, y: 4.45, w: 8.5, h: 0.35, fontSize: 11, color: K.ink2 });
  s.addNotes("For the finale: circular delta, official notifications, measured Gemma results, and full Hindi and Punjabi. The core idea in one line: the model reads once; code decides every time.");
}

(async () => {
  const out = path.join(__dirname, "Paatrata.pptx");
  await pres.writeFile({ fileName: out });
  try {
    const { applyTheme } = require(process.env.APPLY_THEME || "./apply_theme.js");
    await applyTheme(out, THEME);
  } catch (_) {
    /* theme colours are optional: every colour in this deck is set explicitly */
  }
  console.log(`wrote ${out}${results ? " (with evaluation results)" : " (evaluation results pending)"}`);
})();
