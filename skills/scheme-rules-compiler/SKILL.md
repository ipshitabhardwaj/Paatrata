---
name: scheme-rules-compiler
description: Compile an Indian government welfare-scheme document (PDF or text) into validated, clause-cited eligibility rules, run boundary tests, and check an applicant profile deterministically. Use when asked to encode, verify or test scheme eligibility rules, or to check eligibility against a scheme's official text.
license: Apache-2.0
---

# Scheme rules compiler

Turns a scheme notification into a `RuleSet` JSON (conditions over a fixed vocabulary, each with a
verbatim source quote and page) using Gemini or Gemma, rejects anything the source does not support,
and evaluates profiles with deterministic three-valued logic (ELIGIBLE / NOT_ELIGIBLE / NEEDS_INFO).

## Requirements

- Python 3.10+ and the `paatrata-core` package: `pip install -e <repo>` (repo root contains `pyproject.toml`).
- For Gemini: `GEMINI_API_KEY`. For local Gemma: a running Ollama with a Gemma model (`OLLAMA_MODEL`).

## Steps

1. Compile the source (choose `--backend gemini`, `gemma-studio` or `ollama`):
   `python scripts/compile.py <source.pdf|.txt> --backend gemini --out rules.json`
2. Read the printed issues. Never present a condition from the `Rejected` list as a rule.
   For every `ambiguity` issue, ask the user (the officer) the question verbatim; do not resolve it yourself.
3. Run boundary tests and show the table to the user for review:
   `python scripts/compile.py --tests rules.json` (add `--reference gold.json` to compare with hand-labelled rules).
4. To answer an eligibility question, evaluate, don't reason it out:
   `python scripts/compile.py --check rules.json --profile '{"age_years": 64, "family_annual_income_inr": 162000}'`
   Report the verdict exactly as returned, with each condition's quote and page. If the verdict is
   NEEDS_INFO, ask for the listed missing fields.

## Rules for the agent

- The verdict comes only from step 4's output. Do not override it with your own reading of the document.
- Always include the disclaimer: informational only, not an official decision.
- See `references/schema.md` for the vocabulary and JSON format.
