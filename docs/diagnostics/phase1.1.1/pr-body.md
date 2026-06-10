# Phase 1.1.1 — re-judge the merge grey zone with Gemini (vs. the ollama baseline)

**Branch:** `feat/phase1.1.1-gemini-judge` → `main`

## Why

The Phase 1.1 merge (PR #2) resolved grey-zone equivalence pairs
(`0.85 ≤ cosine < 0.95`) with a **local ollama** model
(`qwen2.5:14b-instruct`). The verdicts looked weak — in particular a lot of
high-similarity *organism vs. disease* pairs were merged as `parent_child`
when they are genuinely **different** concepts. This phase re-judges the same
pairs with **Gemini** under an identical eval, to measure how much the local
judge cost us and which edges to fix.

## What shipped

- `scripts/judge/gemini_judge.py` — re-judges the grey-zone pairs with
  `gemini-2.5-pro` (auto-fallback to `gemini-2.5-flash` on 429/5xx), holding the
  eval **constant** vs. ollama: same pairs, same prompt wording (adapted to
  Gemini's JSON-schema response mode), same definitions reconstructed from
  `raw/` (mostly `(none)`, exactly as ollama saw them), temperature 0.
  Idempotent/resumable (skips already-judged pairs), with a hard **$5 cost cap**
  enforced from each response's `usageMetadata` before every call.
- `scripts/judge/compare.py` — writes `diagnostics.md`: agreement rate, every
  flipped pair (and to what), edge cases, per-model + cost summary.
- `data/phase1.1.1/ollama-grey-zone.json` — the **213** input pairs (the
  `parent_child` grey-zone slice, vendored from
  `origin/feat/phase1-merge:docs/diagnostics/phase1-merge-low-confidence.json`).
- `docs/diagnostics/phase1.1.1/judged-pairs.jsonl` — full per-pair record
  (both verdicts, confidences, rationales, model, tokens, cost).
- `docs/diagnostics/phase1.1.1/diagnostics.md` — the writeup.

## Result

- **Agreement with ollama: 186/213 (87.3%)** within the `parent_child` slice.
- Gemini reclassified **19 as `different`** and **8 as `same`** — 0 errors.
- The 19 `different` flips are almost entirely the **organism ≠ disease**
  conflation ollama got wrong (e.g. *Plasmodium vivax* the parasite vs.
  *Plasmodium vivax malaria* the disease; *Taenia saginata* vs. *taeniasis*;
  *Klebsiella pneumoniae* vs. *pneumonia due to Klebsiella pneumoniae*) — false
  parent_child edges that would have polluted the DAG.
- The 8 `same` flips are true synonyms ollama over-split (e.g.
  *Anthropology, Medical* ≡ *medical anthropology*; *science* ≡ *sciences*).
- Every Gemini verdict ≥ 0.6 confidence (no low-confidence edge cases).

## Cost

**$0.4788** of the $5.00 Phase 1.1.1 cap; all 213 on `gemini-2.5-pro`, no
fallback, not stopped on cap. (Running taxonomy-build cash total stays well
within the $10 budget.)

## Scope caveat

These 213 are **only** the grey-zone pairs ollama labelled `parent_child` — the
slice persisted in the repo. The pairs ollama called `same`/`different`, and
the full ~600-pair grey zone, were never committed and need the mac's nomic
embeddings (absent on this host). So agreement is measured **within the
`parent_child` slice**, not across the whole grey zone.

## Actionable next step (Phase 1.1.2 / merge fix)

Feed the 27 flips back into the merge DAG: **drop the 19 false-neighbour
`parent_child` edges** and **collapse the 8 synonym pairs** to a single node.
This is best done on the mac where the full merge + embeddings live; the 27
edits are enumerated in `diagnostics.md`. Longer-term, Gemini's clean
organism/disease separation argues for using it (not the local model) as the
grey-zone judge when the full ~600-pair set is available.
