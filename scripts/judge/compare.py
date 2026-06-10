#!/usr/bin/env python3
"""Phase 1.1.1 — compare the Gemini re-judge against the ollama baseline.

Reads docs/diagnostics/phase1.1.1/judged-pairs.jsonl and writes diagnostics.md:
agreement rate, the pairs that flipped (and to what), edge cases, per-model and
cost summary, and the scope caveat. All 213 baseline pairs carry the ollama
verdict "parent_child", so the comparison measures how often Gemini agrees vs.
reclassifies them as "same" (true synonyms ollama over-split) or "different"
(false neighbours ollama should not have linked).
"""
from __future__ import annotations

import collections
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
DIAG = REPO / "docs" / "diagnostics" / "phase1.1.1"
JSONL = DIAG / "judged-pairs.jsonl"
OUT = DIAG / "diagnostics.md"
COST = REPO / ".cost-state" / "phase1.1.1-cost.json"


def load():
    return [json.loads(l) for l in JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    recs = load()
    n = len(recs)
    agree = sum(1 for r in recs if r["gemini_verdict"] == r["ollama_verdict"])
    gem_dist = collections.Counter(r["gemini_verdict"] for r in recs)
    oll_dist = collections.Counter(r["ollama_verdict"] for r in recs)
    models = collections.Counter(r["model"] for r in recs)
    errors = [r for r in recs if r["gemini_verdict"] == "error"]

    flipped_same = [r for r in recs if r["gemini_verdict"] == "same"]
    flipped_diff = [r for r in recs if r["gemini_verdict"] == "different"]
    kept = [r for r in recs if r["gemini_verdict"] == "parent_child"]
    low_conf = sorted((r for r in recs if isinstance(r.get("gemini_confidence"), (int, float))
                       and r["gemini_confidence"] < 0.6),
                      key=lambda r: r["gemini_confidence"])

    cost = json.loads(COST.read_text()) if COST.exists() else {}
    total_cost = sum(r.get("cost_usd", 0) for r in recs)

    def tbl(rows):
        out = ["| A (src) | B (src) | sim | gemini conf | rationale |",
               "|---|---|---:|---:|---|"]
        for r in rows:
            out.append(f"| {r['a']} ({r['a_src']}) | {r['b']} ({r['b_src']}) | "
                       f"{r['sim']:.3f} | {r.get('gemini_confidence')} | "
                       f"{(r.get('gemini_rationale') or '').replace(chr(10),' ')[:160]} |")
        return "\n".join(out)

    md = []
    md.append("# Phase 1.1.1 — Gemini grey-zone re-judge vs. ollama baseline\n")
    md.append("## Scope & setup\n")
    md.append(
        f"- **{n} grey-zone pairs** re-judged with Gemini (primary "
        f"`gemini-2.5-pro`, fallback `gemini-2.5-flash`).\n"
        "- Baseline: the Phase 1.1 merge (PR #2) judged these with ollama "
        "`qwen2.5:14b-instruct`. Source of pairs: the committed "
        "`phase1-merge-low-confidence.json`.\n"
        "- **Caveat:** these 213 are the grey-zone pairs ollama labelled "
        "`parent_child` — the only slice persisted in the repo. The pairs "
        "ollama called `same`/`different`, and the full ~600-pair grey zone, "
        "were never committed and need the mac's nomic embeddings (absent on "
        "this host). So agreement here is measured **within the `parent_child` "
        "slice**.\n"
        "- Identical eval: same pairs, same prompt wording (adapted to Gemini's "
        "JSON-schema mode), same definitions reconstructed from `raw/` "
        "(mostly `(none)`, exactly as ollama saw them), temperature 0.\n")

    md.append("## Headline\n")
    md.append(
        f"- **Agreement with ollama: {agree}/{n} ({100*agree/n:.1f}%)** "
        "(both say `parent_child`).\n"
        f"- Gemini reclassified **{len(flipped_same)}** as `same` and "
        f"**{len(flipped_diff)}** as `different`.\n"
        f"- Gemini verdict distribution: "
        + ", ".join(f"`{k}`={v}" for k, v in gem_dist.most_common()) + ".\n"
        f"- ollama verdict distribution: "
        + ", ".join(f"`{k}`={v}" for k, v in oll_dist.most_common()) + ".\n"
        f"- Errors/parse failures: {len(errors)}.\n")

    md.append("## Cost\n")
    md.append(
        f"- **Total: ${total_cost:.4f}** of $5.00 cap.\n"
        f"- Models used: " + ", ".join(f"`{k}`={v}" for k, v in models.most_common()) + ".\n"
        f"- Stopped on cap: {cost.get('stopped_on_cap', False)}.\n")

    md.append(f"## Flipped → `same` ({len(flipped_same)}) — synonyms ollama over-split\n")
    md.append(tbl(sorted(flipped_same, key=lambda r: -(r.get("gemini_confidence") or 0))) if flipped_same else "_none_\n")
    md.append("")
    md.append(f"## Flipped → `different` ({len(flipped_diff)}) — false neighbours\n")
    md.append(tbl(sorted(flipped_diff, key=lambda r: -(r.get("gemini_confidence") or 0))) if flipped_diff else "_none_\n")
    md.append("")
    md.append(f"## Low Gemini confidence (<0.6) — genuine edge cases ({len(low_conf)})\n")
    md.append(tbl(low_conf) if low_conf else "_none_\n")
    md.append("")
    md.append(f"## Kept as `parent_child` ({len(kept)})\n")
    md.append(f"Gemini confirmed ollama on {len(kept)} pairs. "
              "Sample (first 15):\n")
    md.append(tbl(kept[:15]))
    md.append("")

    OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}")
    print(f"agree={agree}/{n} ({100*agree/n:.1f}%)  ->same={len(flipped_same)} "
          f"->different={len(flipped_diff)}  errors={len(errors)}  cost=${total_cost:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
