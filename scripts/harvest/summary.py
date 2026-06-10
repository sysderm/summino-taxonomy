#!/usr/bin/env python3
"""Summarize the Phase 1.0 harvest.

Reads every raw/<source>.json that the parsers produced and prints a table of
(source | version | node_count | notes), plus the grand total. Sources that
were attempted but produced no file (e.g. PhilPapers behind a bot wall) are
listed as SKIPPED. Also writes the same table to
docs/diagnostics/phase1-harvest-summary.md so the snapshot is reviewable in the
PR without re-running anything.

Run after scripts/harvest/all.sh (or standalone any time).
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "raw"
OUT = REPO_ROOT / "docs" / "diagnostics" / "phase1-harvest-summary.md"

# Ordered (raw-file slug, one-line note). Order = harvest order in all.sh.
SOURCES: list[tuple[str, str]] = [
    ("arxiv", "arXiv category taxonomy scraped from the public HTML "
              "(group / archive / category)."),
    ("oecd-fos", "Frascati Manual 2015 FOS-2007 standard transcribed verbatim "
                 "(OECD publishes no machine-readable file)."),
    ("scopus-asjc", "Elsevier public ASJC1.xlsx (support a_id/15181): "
                    "27 subject areas + 334 categories."),
    ("msc2020", "Mathematics Subject Classification 2020 TSV from msc2020.org."),
    ("openalex", "Topics hierarchy (4 domains -> 26 fields -> 252 subfields -> "
                 "~4.5k topics). Concepts deprecated 2024 -- its ancestors are "
                 "now null, so it carries no hierarchy; Topics replaces it."),
    ("physh", "PhySH SKOS Turtle from the physh-org/PhySH GitHub repo "
              "(physh.org has no public API)."),
    ("cso", "Computer Science Ontology 3.5 CSV of RDF triples."),
    ("icd", "WHO ICD-10 2019 via the public auth-free browser JSON API. "
            "ICD-11 requires registering an OAuth client account, so per the "
            "$0 / no-account rule we fell back to ICD-10."),
    ("mesh", "MeSH 2026 descriptor XML via NLM FTP (gzip, streamed). UMLS "
             "semantic types are licensed/auth-walled and were not harvested."),
    ("agris", "AGRIS OAI-PMH endpoint is dead (serves the search webpage), so "
              "we harvested AGROVOC -- the FAO thesaurus the README points to "
              "-- from its public SPARQL endpoint instead."),
    ("wikidata", "WDQS SPARQL: items that are instance-of or transitive "
                 "subclass-of Q11862829 (academic discipline), with multi-"
                 "parent subClassOf edges."),
    ("philpapers", "SKIPPED: every path sits behind a Cloudflare anti-bot "
                   "challenge (403) and robots.txt disallows automated "
                   "collection; no standalone mirror of the category tree "
                   "exists. Humanities coverage comes from OECD-FOS + Wikidata."),
]


def main() -> int:
    rows: list[tuple[str, str, str, str]] = []
    total = 0
    for slug, note in SOURCES:
        path = RAW_DIR / f"{slug}.json"
        if path.exists():
            d = json.loads(path.read_text(encoding="utf-8"))
            count = int(d.get("node_count", len(d.get("nodes", []))))
            version = str(d.get("version", "?"))
            total += count
            rows.append((slug, version, f"{count:,}", note))
        else:
            rows.append((slug, "-", "SKIPPED", note))

    n_ok = sum(1 for _, _, c, _ in rows if c != "SKIPPED")
    n_skip = len(rows) - n_ok

    header = (
        "# Phase 1.0 harvest summary\n\n"
        f"**{n_ok} sources harvested, {n_skip} skipped, "
        f"{total:,} total raw nodes.**\n\n"
        "Each source is a faithful, idempotent snapshot under `raw/<source>.json` "
        "in the shared normalized schema "
        "(`id, name, parents, aliases, definition, extras`). Counts are raw "
        "node counts before the Phase 1.1 merge/dedup.\n\n"
        "| source | version | node_count | notes |\n"
        "|---|---|---:|---|\n"
    )
    body = "".join(
        f"| `{s}` | {v} | {c} | {n} |\n" for s, v, c, n in rows
    )
    footer = f"| **total** | | **{total:,}** | {n_ok} harvested + {n_skip} skipped |\n"
    md = header + body + footer

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(md, encoding="utf-8")

    # Plain-text echo to stdout.
    print(f"{'source':14} {'count':>8}  version")
    print("-" * 60)
    for s, v, c, _ in rows:
        print(f"{s:14} {c:>8}  {v}")
    print("-" * 60)
    print(f"{'TOTAL':14} {total:>8,}  ({n_ok} harvested + {n_skip} skipped)")
    print(f"\nwrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
