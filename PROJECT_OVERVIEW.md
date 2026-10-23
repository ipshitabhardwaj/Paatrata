# Paatrata · पात्रता: Project Overview

**Code for Communities Chandigarh 2026** · GDG Cloud Chandigarh
**Team:** clawops: Veydant Bhardwaj, Ipshita Bhardwaj
**Theme:** Innovative Solution for AI for Digital Public Infrastructure of Chandigarh
**Also entered for:** Bonus Challenge, Best Open-Source AI Project
**Repository:** https://github.com/ipshitabhardwaj/Paatrata (public, Apache-2.0)
**Live demo:** https://paatrata.onrender.com

---

## One-line summary

Paatrata turns welfare-scheme notifications into eligibility rules that are **extracted by Gemini or Groq (Llama 3.1), checked
against the source text, approved by an officer, and then executed by plain code**, so every citizen gets the same
answer with the exact clause it rests on.

---

## 1. Problem statement

**Eligibility rules for welfare schemes exist only as prose, and every channel that serves citizens re-interprets
that prose by hand.**

A scheme notification says things like *"The family annual income of the applicant should not exceed Rs. 1,50,000"*
or *"The applicant should be a resident of UT, Chandigarh for more than 3 years."* Portals, Sampark/e-District
counters, helpdesks and chatbots each turn those sentences into their own logic. This causes four concrete failures:

1. **Inconsistent answers.** Two channels, or one AI chatbot asked twice, can give different verdicts for the same person.
2. **Untraceable answers.** A citizen told "not eligible" rarely learns which clause, or which reading of it, decided that.
3. **Hidden guesses.** Notifications are ambiguous ("family" is undefined; is "18–60 years" inclusive?). Someone
   silently picks an interpretation and nobody records it.
4. **Slow, error-prone updates.** When a circular changes a ceiling or an age limit, every downstream encoding must
   be found and fixed by hand.

**Why Chandigarh.** As a Union Territory, Chandigarh's administration runs its own schemes (old age, widow and
disability pensions, support for children of widows, ICDS) alongside central ones, so residents face two rulebooks.
The administration is also a realistic size for a pilot.

**Why it is an infrastructure problem.** The bottleneck is not the citizen-facing app; it is the absence of a
**verified, machine-readable version of the rules** that every channel could share. Existing tools (myScheme,
Haqdarshak, Indus Action's eligibility engines) do discovery and eligibility well at the citizen end. Paatrata works
one step upstream: from **document** to **verified, executable rules**.

## 2. Who it is for

| User | What they do with Paatrata |
|---|---|
| **Scheme officers** (e.g. Social Welfare, Women & Child Development) | Upload a notification, answer the questions it raises, approve a versioned rule set |
| **Sampark / e-District operators and helpdesks** | Check an applicant in seconds and show the clause behind the answer |
| **Citizens** | See whether they qualify, what is missing, and why, in English, Hindi or Punjabi |
| **Portal and app builders** | Consume approved rules through an API instead of re-encoding them |

## 3. What Paatrata does

1. **Reads the document.** Gemini or Groq (Llama 3.1) extracts each eligibility condition into a fixed schema: field, operator, value,
   a **verbatim quote**, page, confidence, and a **question for the officer** where the wording is unclear. Gemini handles multimodal
   scanned circulars; Groq delivers sub-second extraction for text notifications.
2. **Checks the AI's work with code.** A validator rejects any condition whose quote is not in the document, whose
   value does not parse (`"Rs. 1.5 lakh"` → `150000`), or whose field is not in the controlled vocabulary. It also
   detects contradictions.
3. **Reviews itself.** A second Gemini pass looks only for missing, misread or ambiguous conditions; every finding
   must quote the source, and its questions block approval.
4. **Puts a human in charge.** The officer sees each condition beside the highlighted source sentence, answers every
   open question, checks auto-generated boundary tests (age 59 vs 60, income ₹1,50,000 vs ₹1,50,001), and approves.
5. **Decides with code, not AI.** Approved rules run in a small deterministic engine with three-valued logic:
   **Eligible**, **Not eligible**, or **Needs more information** (naming the missing fact). Same input, same
   answer, every time, with the clause cited for every condition.
6. **Explains in the citizen's language.** Gemini rewrites the result in Hindi or Punjabi; code checks that the
   rewrite keeps the same verdict, or falls back to English.

**The core idea: the model reads once; code decides every time.**

## 4. What is built (working now)

- **Compiler:** multi-backend extraction with Gemini (structured output, multimodal), **Groq** (high-speed Llama 3.1 on Groq LPUs),
  deterministic validator, second-pass Gemini review, response caching, retries and plain-language errors.
- **High-speed & open-weight paths:** the same compiler runs on **Groq** for sub-second responses and on **Gemma 4**
  (Google AI Studio or local Ollama) for on-premise deployments.
- **Deterministic evaluator:** three-valued logic over nested ALL/ANY rule groups, with a citation for every condition.
- **Boundary-test generator:** synthetic test applicants at every threshold, used for officer review and for scoring.
- **Officer workflow:** compile, review against highlighted source, resolve questions, approve, version history.
- **Citizen checker:** a form that shows only the fields each scheme needs, plus a live checker on the landing page and chat assistant.
- **Rulebook:** six Chandigarh schemes, including one where any of several categories qualifies (ICDS) and one with
  a widow-or-legal-guardian alternative.
- **Evaluation harness:** extraction accuracy, quote verification and decision accuracy against hand-labelled
  answer keys, compared with a plain retrieval-augmented chatbot baseline using the same model and documents.
- **Agent Skill:** `skills/scheme-rules-compiler/`, in the Agent Skill Open Standard format.
- **Interfaces:** web app (React), REST API (FastAPI), command line (`paatrata`) and Python library (`paatrata_core`).
- **67 automated tests**, all running offline.

**Simulated / not real:** test applicants are synthetic; scheme texts are secondary summaries from
publicservicesmap.in (a myScheme mirror); five of six answer keys are drafts pending human verification; there is no
integration with any government system.

## 5. AI and tools used

| Tool / Model | How Paatrata uses it | Status |
|---|---|---|
| **Gemini API** | Rule extraction with structured output (Pydantic schema → JSON); multimodal scanned PDF parsing | Built |
| **Gemini API** | Second-pass review for missing, misread and ambiguous conditions | Built |
| **Gemini API** | Hindi and Punjabi explanations, verdict-checked | Built |
| **Gemini API** | Baseline chatbot in the evaluation, for a fair comparison | Built |
| **Groq API (Llama 3.1)** | Ultra-fast rule compilation on Groq LPUs (sub-second) and real-time citizen chat query extraction fallback | Built |
| **Google AI Studio** | API keys; hosted **Gemma 4** for the open-weight extractor | Built |
| **Gemma 4 (open weights)** | Same compiler, locally via Ollama, for on-premise use | Built; to be measured |
| **Gemini Multimodal** | Scanned PDFs without a text layer are sent to Gemini as PDF | Built |
| **Cloud Run** | Deployment target for the Docker image (API + UI in one container) | Ready (Dockerfile); demo currently hosted on Render |
| **Agent Skill Open Standard** | Lets Gemini CLI and other agents compile and check schemes | Built |
| Cloud Translation, Speech-to-Text, Text-to-Speech, Dialogflow | Not used; Gemini handles translation. Voice is a roadmap item | Not used |
| Vertex AI, BigQuery, Firebase, Maps, Earth Engine, LiteRT | Not needed for this problem | Not used |

**What the AI never does:** decide whether a person is eligible. That is always the deterministic engine running
officer-approved rules.

## 6. How it maps to the judging criteria

### Problem-Solution Fit (20%)
A specific, recurring failure in public infrastructure (inconsistent, untraceable eligibility decisions), solved at
its source: one verified rulebook that every channel can use. Built and demonstrated on six real Chandigarh schemes.

### AI / Technical Execution (25%)
Google AI and Groq do the hard language work: reading varied prose, mapping it to typed conditions, finding ambiguity,
reviewing output, and writing explanations in Indian languages. That work is **measurable**: extraction
accuracy and decision accuracy against answer keys, and a head-to-head with a chatbot baseline. It runs end to end:
document in, approved rules, answer out, in a web app, an API, a command line and a library.

### Depth & Reach Across India (20%)
Every state and ministry publishes schemes as notifications, and the bottleneck of turning documents into rules
repeats everywhere. Nothing in Paatrata is Chandigarh-specific except the sample data: the field vocabulary,
compiler and engine work for any scheme. Gemini reads Hindi and other Indian-language notifications. One private
provider alone lists more than 5,000 schemes across India
([NITI Aayog Frontier Tech](https://frontiertech.niti.gov.in/story/a-revolution-for-indias-welfare-how-ai-is-helping-families-access-public-schemes/)).

### Impact Potential (15%)
A single approved rulebook means every channel (portal, counter, helpdesk, chatbot) gives the same, cited answer, and
rule changes are one review instead of many re-encodings. Citizens learn exactly what is missing instead of being
turned away. *We make no household-level impact claims; those require a pilot to measure.*

### Deployability & Scalability (20%)
A pilot needs **no integration**. A department uploads notifications it already publishes, an officer reviews and
approves, and the approved rules are available through an API. One Docker image runs on Cloud Run. A pilot could
start in weeks:

1. Collect the department's current notifications.
2. Compile, review and approve them with the department's own officers.
3. Expose the approved rules to one helpdesk or Sampark counter as a read-only checker.
4. Compare its answers with current practice on a sample of past applications.

### Bonus: Best Open-Source AI Project
- **High-speed inference & open-weight paths:** Groq (Llama 3.1) enables sub-second compilation on Groq LPUs; Gemma 4
  runs the same extraction, locally or on AI Studio, for departments that cannot send documents outside.
- **Agent skill:** `skills/scheme-rules-compiler/` follows the Agent Skill Open Standard; it makes agents call the
  deterministic engine instead of guessing eligibility.
- **Original, reusable component:** `paatrata_core` is an installable library: rule schema, validator, three-valued
  evaluator, boundary-test generator, pluggable extractor interface (Gemini, Groq, Gemma) and an evaluation harness with a public answer-key format.
- **Public and licensed:** public GitHub repository, Apache-2.0; answer keys CC-BY-4.0.

## 7. Evaluation method

| Metric | What it shows |
|---|---|
| Extraction F1 | Do extracted conditions match the hand-labelled answer key? |
| F1 before validator | How much the code-side checks protect the result |
| Quotes verified | How often the model's citations are genuinely in the document |
| Decision accuracy | Do verdicts agree with the answer key, on boundary cases and 300 synthetic applicants per scheme? |
| Consistency (baseline) | Does a plain chatbot give the same answer when asked the same thing again? |
| Valid citations (baseline) | Does the chatbot's quoted text exist in the source? |

**Baseline:** a retrieval-augmented chatbot with the same Gemini model and the same documents, asked at question
time. The only difference is *ask every time* versus *compile once*.

**Results:** _to be filled from `evaluation/results/latest.md` after the final run._

**Honest framing:** applicants are synthetic and answer keys are team-labelled; results measure agreement with
those labels, not real-world accuracy.

## 8. Technology stack

| Layer | Choice |
|---|---|
| AI | Gemini API (structured output, multimodal), Groq API (Llama 3.1 on LPUs), Gemma 4 via Google AI Studio or Ollama |
| Core | Python 3.11+, Pydantic, rapidfuzz, pdfplumber |
| Backend | FastAPI, SQLite |
| Frontend | React + Vite, original illustration, self-hosted fonts (Archivo, Tiro Devanagari Hindi, Noto Sans Gurmukhi) |
| Evaluation | Custom harness, scikit-learn TF-IDF for the baseline |
| Packaging | Docker (Cloud Run ready), `pip install` library, CLI, Agent Skill |
| Tests | pytest, 67 offline tests |

## 9. Responsible design

- The model never decides eligibility; a wrong extraction becomes a visible rule error that an officer catches,
  not a wrong answer given to a citizen.
- Every rule and every review finding must quote the source, or it is discarded.
- Ambiguity is surfaced as a question, not resolved by the model.
- No personal data is stored; test applicants are synthetic.
- Every answer is labelled "informational only, not an official eligibility decision".
- Sources are labelled primary or secondary throughout the app.

## 10. Limitations

- Six schemes, all from secondary summaries; five answer keys await human verification.
- No live government integration; the pilot path above is the plan, not a claim.
- Scanned-PDF quotes cannot be verified locally (flagged).
- The Gemma 4 path is implemented but not yet measured in the evaluation.

## 11. Roadmap (Grand Finale and beyond)

- **Circular delta:** compile a new circular against the approved rules and show exactly what changed, from when,
  and who is affected.
- Official department notifications for every Chandigarh scheme, including Hindi-only sources.
- Measured Gemma 4 results for fully on-premise use.
- Hindi and Punjabi across the whole interface; voice input at counters.
- Publishing approved rules as open data for any portal to consume.

## 12. Team

| Member | Email |
|---|---|
| Veydant Bhardwaj | veydantbhardwaj@gmail.com |
| Ipshita Bhardwaj | bhardwaj.ipshita0@gmail.com |

_Team: clawops._
