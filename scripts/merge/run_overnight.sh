#!/usr/bin/env bash
# Overnight runner: phase 1.1 merge → commit per pass → push → open PR.
# Designed to be idempotent and survive partial failures.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"

LOG="$REPO/.merge-state/run.log"
mkdir -p "$REPO/.merge-state"
exec >> "$LOG" 2>&1
echo "=== overnight run start $(date -u +%FT%TZ) ==="

# ensure branch
git fetch origin
if git rev-parse --verify feat/phase1-merge >/dev/null 2>&1; then
  git checkout feat/phase1-merge
  git pull --ff-only origin feat/phase1-merge || true
else
  git checkout -B feat/phase1-merge origin/feat/phase1-harvest
fi

# run the merge
"$REPO/.venv/bin/python" "$REPO/scripts/merge/phase11_merge.py"
RC=$?
echo "merge.py exited rc=$RC"

if [ $RC -ne 0 ]; then
  echo "merge failed, leaving branch as-is for morning review"
  exit $RC
fi

# commit + push
git add merged.json docs/diagnostics/phase1-merge-summary.md docs/diagnostics/phase1-merge-low-confidence.json scripts/merge/phase11_merge.py scripts/merge/run_overnight.sh
if ! git diff --staged --quiet; then
  git commit -m "Phase 1.1 — merge 11 source taxonomies (deterministic + embed + llm-judge)

Three-pass merge:
  1. Wikidata-QID join + normalized-name match + alias intersection
  2. nomic-embed-text cosine kNN, auto-merge >= 0.95
  3. qwen2.5:14b-instruct judge on 0.85-0.95 grey-zone pairs (cap 600)

All compute local on mac ollama, \$0 cash, idempotent.

See docs/diagnostics/phase1-merge-summary.md for collapse rate +
docs/diagnostics/phase1-merge-low-confidence.json for morning review.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
fi

git push -u origin feat/phase1-merge
echo "pushed feat/phase1-merge"

# open PR (or update existing)
if gh pr view feat/phase1-merge --repo sysderm/summino-taxonomy >/dev/null 2>&1; then
  echo "PR already exists"
else
  gh pr create --repo sysderm/summino-taxonomy \
    --base main \
    --head feat/phase1-merge \
    --title "Phase 1.1 — merge 11 source taxonomies into unified DAG" \
    --body "$(cat <<'BODY'
## Summary
- Collapses 128,626 raw nodes from 11 source taxonomies into a unified DAG with multi-parent edges + cross-source equivalence.
- Three-pass merge, fully local (mac ollama), \$0 cash:
  1. **Deterministic** — Wikidata QID join, normalized-name match, alias intersection (cross-source only)
  2. **Embedding** — `nomic-embed-text` cosine kNN, auto-merge at cosine >= 0.95
  3. **LLM judge** — `qwen2.5:14b-instruct` on grey-zone pairs (0.85-0.95), accepts "same" with confidence >= 0.7

## Outputs
- `merged.json` — canonical nodes with `source_ids` per source, unified `parents`, `aliases`, `definition`
- `docs/diagnostics/phase1-merge-summary.md` — collapse rate, per-source contribution, top clusters
- `docs/diagnostics/phase1-merge-low-confidence.json` — top 300 grey-zone / errored judgements for morning review

## Next
- Manual spot-check of low-confidence cluster file
- Phase 1.2 per-branch deep-dive (parallel jobs) once merge is sanity-checked
BODY
)"
fi

echo "=== overnight run done $(date -u +%FT%TZ) ==="
