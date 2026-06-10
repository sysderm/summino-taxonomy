#!/usr/bin/env python3
"""Phase 1.1.1 — re-judge the grey-zone pairs with the Gemini API.

Background: the Phase 1.1 merge (PR #2) judged grey-zone equivalence pairs
(0.85 <= cosine < 0.95) with a local ollama model (qwen2.5:14b-instruct). The
result was unsatisfactory, so this re-runs the SAME pairs with Gemini, holding
the eval setup constant so the two judges are directly comparable:

  - same pairs            data/phase1.1.1/ollama-grey-zone.json (the committed
                          213 pairs ollama labelled "parent_child" -- the only
                          grey-zone slice persisted; the full ~600 needs the
                          mac's nomic embeddings, absent here)
  - same prompt structure identical wording to phase11_merge.JUDGE_PROMPT,
                          adapted to Gemini's native JSON-schema response mode
  - same inputs           name + definition + source per side; definitions are
                          reconstructed from raw/ exactly as ollama saw them
                          (mostly "(none)", matching the original run)
  - same decoding         temperature 0.0

Model: gemini-2.5-pro (quality), with automatic fallback to gemini-2.5-flash
on quota/429 or if the running cost would otherwise breach the cap. The model
actually used is recorded per pair.

Cost: hard cap $5 (Phase 1.1.1 budget). Token usage is read from each
response's usageMetadata and priced; the run stops before any call that would
exceed the cap. Idempotent/resumable: already-judged pairs in the output
JSONL are skipped and their cost counted.

Output: docs/diagnostics/phase1.1.1/judged-pairs.jsonl
"""
from __future__ import annotations

import glob
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
PAIRS_IN = REPO / "data" / "phase1.1.1" / "ollama-grey-zone.json"
OUT_DIR = REPO / "docs" / "diagnostics" / "phase1.1.1"
OUT_JSONL = OUT_DIR / "judged-pairs.jsonl"
COST_STATE = REPO / ".cost-state"

PRIMARY = "gemini-2.5-pro"
FALLBACK = "gemini-2.5-flash"
CAP_USD = 5.0
THINKING_BUDGET = 256
MAX_OUTPUT = 1024

# USD per 1M tokens (input, output). Output includes thinking tokens.
PRICE = {
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.30, 2.50),
}

ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
            "{model}:generateContent?key={key}")

# Identical wording to phase11_merge.py's JUDGE_PROMPT (the ollama run).
JUDGE_PROMPT = """You are deciding whether two scientific concepts refer to the SAME thing across taxonomies.

A: "{name_a}"
   definition: {def_a}
   source: {src_a}

B: "{name_b}"
   definition: {def_b}
   source: {src_b}

Verdicts:
  "same"          — synonyms or aliases for the same concept
  "parent_child"  — one is a broader category of the other
  "different"     — distinct concepts that happen to share vocabulary

Decide the single best verdict, your confidence in [0,1], and one short sentence of rationale."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["same", "parent_child", "different"]},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["verdict", "confidence", "rationale"],
}


def load_key() -> str:
    for l in pathlib.Path("/root/.env").read_text().splitlines():
        l = l.strip()
        if l and not l.startswith("#") and "=" in l:
            k, v = l.split("=", 1)
            if k.strip() == "GEMINI_API_KEY":
                return v.strip().strip('"').strip("'")
    sys.exit("GEMINI_API_KEY not found in /root/.env")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().casefold())


def build_def_index() -> dict:
    idx: dict[tuple[str, str], str | None] = {}
    for f in glob.glob(str(REPO / "raw" / "*.json")):
        d = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        src = d["source"]
        for n in d["nodes"]:
            key = (src, norm(n.get("name")))
            # prefer the first node that carries a definition
            if key not in idx or (idx[key] is None and n.get("definition")):
                idx[key] = n.get("definition")
    return idx


def gemini_call(model: str, key: str, prompt: str) -> tuple[dict, int, int]:
    """Return (parsed_json, prompt_tokens, output_tokens). Raises on HTTP error."""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
            "maxOutputTokens": MAX_OUTPUT,
            "thinkingConfig": {"thinkingBudget": THINKING_BUDGET},
        },
    }
    req = urllib.request.Request(
        ENDPOINT.format(model=model, key=key),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.load(r)
    um = resp.get("usageMetadata", {})
    ptok = int(um.get("promptTokenCount", 0))
    otok = int(um.get("candidatesTokenCount", 0)) + int(um.get("thoughtsTokenCount", 0))
    try:
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
    except Exception as e:
        parsed = {"verdict": "error", "confidence": 0.0, "rationale": f"parse: {e}"}
    return parsed, ptok, otok


def cost_of(model: str, ptok: int, otok: int) -> float:
    pin, pout = PRICE[model]
    return (ptok * pin + otok * pout) / 1_000_000


def judge_with_retry(model: str, key: str, prompt: str):
    """Try `model`; on 429/5xx retry w/ backoff, then signal fallback."""
    for attempt in range(3):
        try:
            return model, *gemini_call(model, key, prompt)
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                if model == PRIMARY:
                    return ("__FALLBACK__", {}, 0, 0)  # caller switches to flash
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError:
            time.sleep(2 * (attempt + 1))
    return model, {"verdict": "error", "confidence": 0.0, "rationale": "retries exhausted"}, 0, 0


def main() -> int:
    key = load_key()
    pairs = json.loads(PAIRS_IN.read_text(encoding="utf-8"))
    defs = build_def_index()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    COST_STATE.mkdir(exist_ok=True)

    def pair_key(p):
        return f"{p['a_src']}::{p['a']}||{p['b_src']}::{p['b']}"

    done, total_cost = {}, 0.0
    if OUT_JSONL.exists():
        for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["pair_key"]] = rec
                total_cost += rec.get("cost_usd", 0.0)
        print(f"resuming: {len(done)} already judged, prior cost ${total_cost:.4f}")

    model = PRIMARY
    n_pro = n_flash = 0
    stopped = False
    with OUT_JSONL.open("a", encoding="utf-8") as out:
        for i, p in enumerate(pairs):
            pk = pair_key(p)
            if pk in done:
                continue
            da = defs.get((p["a_src"], norm(p["a"]))) or "(none)"
            db = defs.get((p["b_src"], norm(p["b"]))) or "(none)"
            prompt = JUDGE_PROMPT.format(
                name_a=p["a"], def_a=da[:400], src_a=p["a_src"],
                name_b=p["b"], def_b=db[:400], src_b=p["b_src"])

            # cap guard: stop before a call that could plausibly breach the cap
            est_max = cost_of(model, 1000, MAX_OUTPUT)
            if total_cost + est_max > CAP_USD:
                print(f"!! cost cap ${CAP_USD} would be exceeded "
                      f"(spent ${total_cost:.4f}); stopping at pair {i}/{len(pairs)}")
                stopped = True
                break

            used, parsed, ptok, otok = judge_with_retry(model, key, prompt)
            if used == "__FALLBACK__":
                model = FALLBACK
                print(f"  primary quota hit -> switching to {FALLBACK}")
                used, parsed, ptok, otok = judge_with_retry(model, key, prompt)

            c = cost_of(used, ptok, otok)
            total_cost += c
            n_pro += used == PRIMARY
            n_flash += used == FALLBACK

            rec = {
                "pair_key": pk,
                "a": p["a"], "a_src": p["a_src"],
                "b": p["b"], "b_src": p["b_src"],
                "sim": p.get("sim"),
                "def_a_present": da != "(none)",
                "def_b_present": db != "(none)",
                "ollama_verdict": p.get("verdict"),
                "ollama_confidence": p.get("confidence"),
                "ollama_rationale": p.get("rationale"),
                "gemini_verdict": parsed.get("verdict"),
                "gemini_confidence": parsed.get("confidence"),
                "gemini_rationale": parsed.get("rationale"),
                "model": used,
                "prompt_tokens": ptok, "output_tokens": otok,
                "cost_usd": round(c, 6),
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            if (i + 1) % 25 == 0:
                print(f"  judged {i+1}/{len(pairs)}  spent ${total_cost:.4f}  "
                      f"(pro={n_pro} flash={n_flash})")

    (COST_STATE / "phase1.1.1-cost.json").write_text(json.dumps({
        "total_cost_usd": round(total_cost, 6),
        "cap_usd": CAP_USD,
        "judged_this_run": {"pro": n_pro, "flash": n_flash},
        "total_in_output": len(done) + n_pro + n_flash,
        "stopped_on_cap": stopped,
    }, indent=2), encoding="utf-8")
    print(f"\ndone: {len(done)+n_pro+n_flash}/{len(pairs)} judged, "
          f"total cost ${total_cost:.4f} / ${CAP_USD} cap "
          f"(pro={n_pro} flash={n_flash}){' [STOPPED ON CAP]' if stopped else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
