#!/usr/bin/env bash
# Phase 1.0 harvest orchestrator.
#
# Runs every source parser sequentially via the repo venv. Each parser is
# idempotent (overwrites raw/<source>.json) and self-contained: it fetches,
# normalizes, and writes its own snapshot, returning 0 on success OR on a
# documented skip (e.g. an auth/bot wall -> SkipSource, no raw file written),
# and non-zero only on an unexpected failure.
#
# Transient network/timeout failures are retried up to 3x with backoff per
# parser before we give up on that source. A genuine parser failure is logged
# and recorded but does NOT abort the whole run -- the other sources still
# harvest, and the final summary shows exactly which sources produced a file.
#
# Usage:
#   scripts/harvest/all.sh            # run all sources, then print summary
#   scripts/harvest/all.sh mesh icd   # run only the named sources
set -uo pipefail

cd "$(dirname "$0")/../.." || exit 1
PY="./.venv/bin/python"
HARVEST="scripts/harvest"

# Source slugs in a sensible order (small/fast first, big SPARQL/XML last).
ALL_SOURCES=(
  arxiv oecd_fos scopus_asjc msc2020 openalex
  physh cso icd mesh agris wikidata philpapers
)

SOURCES=("$@")
if [ ${#SOURCES[@]} -eq 0 ]; then
  SOURCES=("${ALL_SOURCES[@]}")
fi

MAX_RETRIES=3
failed=()

for src in "${SOURCES[@]}"; do
  script="$HARVEST/${src}.py"
  if [ ! -f "$script" ]; then
    echo "!! no parser for '$src' ($script missing), skipping" >&2
    failed+=("$src")
    continue
  fi
  echo "==> harvesting $src"
  attempt=1
  while true; do
    if "$PY" "$script"; then
      break
    fi
    if [ "$attempt" -ge "$MAX_RETRIES" ]; then
      echo "!! $src failed after $attempt attempts" >&2
      failed+=("$src")
      break
    fi
    wait=$((attempt * 10))
    echo "   $src attempt $attempt failed; retrying in ${wait}s" >&2
    sleep "$wait"
    attempt=$((attempt + 1))
  done
done

echo
echo "==> summary"
"$PY" "$HARVEST/summary.py"

if [ ${#failed[@]} -gt 0 ]; then
  echo
  echo "!! sources that failed: ${failed[*]}" >&2
  exit 1
fi
