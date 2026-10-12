# Gold rules

One `<scheme_id>.json` per scheme, hand-labelled **before** looking at any model output.
File name must match `scheme_id` and the source in `samples/sources/sources.csv`.

Labelling rules
- Encode only what the source states; put non-computable conditions in `unmapped_conditions`.
- Inclusive vs exclusive: "not exceeding" → `<=`, "more than" → `>`, "or above" → `>=`.
- Write a `_labelling_note` for every judgement call.
- For agreement: a second person relabels 3 schemes independently; report agreement in the README.

## Status of the current files

`oapc-chandigarh.json` was labelled first. The other five carry a `_status` line: they were drafted by
Claude from the source text (independently of Gemini/Gemma output) and **must be checked by a person
against the source** before they count as gold. Delete the `_status` line once checked. Judgement
calls are written in each file's `_labelling_note`.
