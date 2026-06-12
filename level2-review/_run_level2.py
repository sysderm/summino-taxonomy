#!/usr/bin/env python3
"""Run the level-2 three-model design game for all 20 level-1 categories.

For each level-1 category, ask Opus 4.8 (via stored answer), Gemini 2.5 Pro,
and GPT-5 to propose the level-2 subspecialties. Save per-category JSON
files with all three answers + cost accounting.

Output structure:
  level2-review/
    by-category/
      medicine/
        opus-4-8.json
        gemini-2.5-pro.json
        gpt-5-mini.json
      biology/
        ...
    PROMPT_TEMPLATE.md
    cost-log.json     # cumulative spend
    summary.json      # per-category counts and convergence stats

Cost tracking:
  - Gemini 2.5 Pro: $1.25 input / $5.00 output per 1M tokens
  - GPT-5: $5.00 input / $25.00 output per 1M tokens (reasoning tokens
    counted as output)
  - Opus 4.8 (Fable): $0 — this script does NOT call Opus; the script
    is invoked by Fable, who writes opus answers in a follow-up turn
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("/Users/navarini/Projects/summino-taxonomy/level2-review")
ROOT.mkdir(parents=True, exist_ok=True)
(ROOT / "by-category").mkdir(exist_ok=True)

LEVEL1 = json.load(open("/Users/navarini/Projects/summino-taxonomy/level1-review/level1-converged.json"))

# Pricing (per 1M tokens) — June 2026
PRICE = {
    "gemini-2.5-pro": {"in": 1.25, "out": 5.00},
    "gpt-5-mini":     {"in": 0.25, "out": 2.00},
}

def ssh_secret(path: str) -> str:
    return subprocess.check_output(
        ["ssh", "vps", f"sudo cat {path}"], text=True
    ).strip()

GEMINI_KEY = ssh_secret("/opt/gemini.txt")
OPENAI_KEY = ssh_secret("/opt/openai.txt")


PROMPT_TEMPLATE = """# Design the level-2 subspecialties for: {l1_name}

You are designing **level 2** for a scientific paper reader app. The user
already picked their level-1 category at onboarding ({l1_name}). On the
next screen they see a grid of subspecialties under it. Your job is to
design that grid.

## Level-1 context

**Category:** {l1_name}
**Tagline:** {l1_tagline}
**Covers:** {l1_covers}
**Audience size at level 1:** {l1_pct}% of all new science papers
**Explicitly excludes (goes to other level-1 categories):** {l1_excludes}

## Hard constraints

- **Count: between 8 and 25 subspecialties.** Fewer than 8 feels thin
  for {l1_name} ("only 5 things in all of X?"). More than 25 makes the
  picker grid noisy.
- **MECE-leaning.** A paper that fits {l1_name} should map to exactly
  one of your subspecialties.
- **Each subspecialty must be how a working professional would
  introduce themselves.** "Cardiology", yes. "Cardiovascular Health
  Sciences", no. "Machine Learning", yes. "Pattern Recognition
  Engineering", no.
- **Audience size matters.** No subspecialty under 0.5% of new papers
  within this level-1 — too thin for a picker card. None over 35% —
  too coarse, the subspecialty should be split.
- **Names must be the WORKING TITLES used by practitioners** (e.g.
  "Cardiology" not "Cardiovascular Medicine"; "NLP" or "Natural
  Language Processing", not "Language Engineering").

## Required output format

Return a single JSON object, no markdown fence:

```
{{
  "level1_slug": "{l1_slug}",
  "level1_name": "{l1_name}",
  "count": 14,
  "rationale": "One paragraph (3-5 sentences) explaining your structural choice for THIS level-1 category. Why this count? What did you deliberately NOT split that you considered? What did you split that's controversial?",
  "subspecialties": [
    {{
      "slug": "kebab-case-id",
      "name": "Working Title (how practitioners say it)",
      "tagline": "5-12 words for the picker card",
      "audience_pct_within_level1": 18.5,
      "covers": ["one-line description", "specific examples"],
      "explicitly_excludes": ["adjacent thing that goes elsewhere — name the other level-2 category"]
    }}
  ],
  "uncovered_concerns": ["one-line notes for anything you considered but didn't ship, with reasoning"]
}}
```

## How your output will be used

Three models will be asked the same question (Opus 4.8, Gemini 2.5 Pro,
GPT-5). The operator will diff the three. Where 2 of 3 agree on a
subspecialty, it ships. Where you disagree, Fable (Opus) arbitrates.
"""


def call_gemini(prompt: str) -> tuple[dict, dict]:
    """Return (parsed_json_response, usage_dict)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={GEMINI_KEY}"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "response_mime_type": "application/json"}
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        data = json.loads(r.read())
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(text)
    usage = data.get("usageMetadata", {})
    in_tok = usage.get("promptTokenCount", 0)
    out_tok = usage.get("candidatesTokenCount", 0)
    return parsed, {"input_tokens": in_tok, "output_tokens": out_tok}


def call_gpt5(prompt: str) -> tuple[dict, dict]:
    url = "https://api.openai.com/v1/chat/completions"
    body = json.dumps({
        "model": "gpt-5-mini",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        # gpt-5-mini supports a reasoning-effort knob; "low" cuts spend ~3x
        # without much quality loss for structured-JSON tasks like this.
        "reasoning_effort": "low",
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json"
    })
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    text = data["choices"][0]["message"]["content"]
    parsed = json.loads(text)
    usage = data.get("usage", {})
    # GPT-5 reasoning tokens count as output
    in_tok = usage.get("prompt_tokens", 0)
    out_tok = usage.get("completion_tokens", 0)
    return parsed, {"input_tokens": in_tok, "output_tokens": out_tok}


def cost(model: str, usage: dict) -> float:
    p = PRICE[model]
    return (usage["input_tokens"] * p["in"] + usage["output_tokens"] * p["out"]) / 1_000_000


def main():
    cost_log = []
    total_in = {"gemini-2.5-pro": 0, "gpt-5-mini": 0}
    total_out = {"gemini-2.5-pro": 0, "gpt-5-mini": 0}
    total_usd = 0.0

    # Save prompt template
    (ROOT / "PROMPT_TEMPLATE.md").write_text(PROMPT_TEMPLATE)

    categories = LEVEL1["categories"]
    print(f"Running level-2 game for {len(categories)} categories…\n")

    for i, cat in enumerate(categories, 1):
        slug = cat["slug"]
        outdir = ROOT / "by-category" / slug
        outdir.mkdir(parents=True, exist_ok=True)
        prompt = PROMPT_TEMPLATE.format(
            l1_slug=slug,
            l1_name=cat["name"],
            l1_tagline=cat["tagline"],
            l1_pct=cat["audience_size_pct"],
            l1_covers="; ".join(cat["covers"]),
            l1_excludes="; ".join(cat.get("explicitly_excludes", [])),
        )
        (outdir / "PROMPT.md").write_text(prompt)

        for model, fn in [("gemini-2.5-pro", call_gemini), ("gpt-5-mini", call_gpt5)]:
            outfile = outdir / f"{model}.json"
            if outfile.exists():
                print(f"[{i:>2}/{len(categories)}] {slug:30s} {model:15s} cached ✓")
                continue
            t0 = time.time()
            try:
                parsed, usage = fn(prompt)
                c = cost(model, usage)
                outfile.write_text(json.dumps(parsed, indent=2))
                total_in[model] += usage["input_tokens"]
                total_out[model] += usage["output_tokens"]
                total_usd += c
                cost_log.append({
                    "category": slug, "model": model,
                    "input_tokens": usage["input_tokens"],
                    "output_tokens": usage["output_tokens"],
                    "usd": round(c, 4),
                    "subspecialties_returned": len(parsed.get("subspecialties", [])),
                    "elapsed_s": round(time.time() - t0, 1),
                })
                print(f"[{i:>2}/{len(categories)}] {slug:30s} {model:15s} "
                      f"{len(parsed.get('subspecialties',[])):>2} subs  "
                      f"${c:.4f}  {usage['input_tokens']:>5}/{usage['output_tokens']:>5}  "
                      f"{time.time()-t0:.0f}s")
            except urllib.error.HTTPError as e:
                msg = e.read().decode()[:300] if hasattr(e, 'read') else str(e)
                print(f"[{i:>2}/{len(categories)}] {slug:30s} {model:15s} HTTP {e.code}: {msg[:120]}")
                cost_log.append({"category": slug, "model": model, "error": f"HTTP {e.code}", "msg": msg[:300]})
            except Exception as e:
                print(f"[{i:>2}/{len(categories)}] {slug:30s} {model:15s} ERROR: {e}")
                cost_log.append({"category": slug, "model": model, "error": str(e)[:300]})

    summary = {
        "total_usd": round(total_usd, 4),
        "by_model": {
            m: {
                "input_tokens": total_in[m],
                "output_tokens": total_out[m],
                "usd": round((total_in[m] * PRICE[m]["in"] + total_out[m] * PRICE[m]["out"]) / 1_000_000, 4),
            } for m in PRICE
        },
        "calls": cost_log,
    }
    (ROOT / "cost-log.json").write_text(json.dumps(summary, indent=2))
    print(f"\n{'='*60}")
    print(f"TOTAL: ${total_usd:.4f}")
    for m in PRICE:
        print(f"  {m:18s} ${summary['by_model'][m]['usd']:.4f}  "
              f"in={total_in[m]:>7,}  out={total_out[m]:>7,}")
    print(f"  Opus 4.8 (Fable):  $0 — answers written in follow-up turn")


if __name__ == "__main__":
    main()
