# Phase 1.0 — harvest source taxonomies

Harvests the public scientific/scholarly classification systems named in the
README into a single normalized raw layer that Phase 1.1 will merge into one
DAG. Each parser fetches, normalizes, and writes an idempotent snapshot to
`raw/<source>.json` in a shared schema:

```
{ source, version, harvested_at, node_count,
  nodes: [ { id, name, parents:[...], aliases:[...], definition, extras:{} } ] }
```

## What landed

**11 sources harvested, 1 skipped — 128,626 total raw nodes** (raw counts,
pre-merge). Full breakdown in
[`docs/diagnostics/phase1-harvest-summary.md`](phase1-harvest-summary.md).

| source | nodes | what it covers |
|---|---:|---|
| `agris` (AGROVOC) | 41,825 | agriculture / food / environment thesaurus |
| `mesh` | 31,110 | biomedical subject headings |
| `cso` | 14,636 | computer science ontology |
| `icd` | 12,597 | clinical / disease classification (ICD-10) |
| `wikidata` | 12,493 | cross-domain academic disciplines |
| `msc2020` | 6,603 | mathematics subject classification |
| `openalex` | 4,798 | broad 4-level scholarly scaffold |
| `physh` | 3,988 | physics subject headings |
| `scopus-asjc` | 361 | journal-level subject areas |
| `arxiv` | 167 | preprint category taxonomy |
| `oecd-fos` | 48 | top-level Frascati fields of science |
| `philpapers` | SKIPPED | philosophy (bot-walled — see below) |

## Source pivots & judgement calls

Four sources did not yield via the obvious route; each pivot is documented in
the parser docstring and the summary notes.

- **AGRIS → AGROVOC.** The AGRIS OAI-PMH endpoint (`agris.fao.org/oai`) no
  longer serves OAI XML — it returns the AGRIS search web page for every verb,
  and AGRIS is a bibliographic record set, not a concept taxonomy. We harvested
  **AGROVOC**, the FAO agricultural thesaurus the README points to, from its
  public SPARQL endpoint (~41.8k `skos:Concept`s, multi-parent `skos:broader`).

- **OpenAlex: Topics, not Concepts.** OpenAlex deprecated **Concepts** in 2024.
  The Concepts endpoint still lists ~65k entries but its `ancestors` /
  `related_concepts` fields are now null across the board — a flat bag of terms
  with no hierarchy. We harvested its successor, **Topics**: a clean 4-level
  tree (4 domains → 26 fields → 252 subfields → ~4.5k topics) — exactly the
  "broad scaffold" role the README assigns to OpenAlex.

- **ICD-11 → ICD-10 fallback.** The ICD-11 API requires registering an
  identity-bound OAuth client account (email-verified sign-up) before issuing
  any token. Per the Phase 1.0 hard rules ($0, no account creation) we fell
  back to **ICD-10 (2019)**, harvested from the public, auth-free JSON API that
  backs the official browser at `icd.who.int/browse10/2019/en`.

- **PhilPapers: skipped (bot wall).** Every PhilPapers path (`/browse/`,
  `/categories.html`, the `/utils/` JSON API) sits behind a Cloudflare
  "Just a moment…" anti-bot challenge returning 403 to non-browser clients, and
  `robots.txt` disallows automated collection; the `/utils/` API is explicitly
  Disallowed. We fail-fast on access walls (defeating the challenge is anti-bot
  evasion, out of scope) and never pay. Public GitHub mirrors hold only scraper
  scripts that themselves call the walled API — no standalone copy of the
  category tree. Recorded as a `SkipSource` (no raw file written). Humanities
  coverage is instead carried by **OECD-FOS (6.x)** and **Wikidata** academic
  disciplines, with an LCC-based humanities branch planned for Phase 1.2.

**Wikidata note.** Harvested cleanly: the membership set is the union of
`wdt:P31` instances and transitive `wdt:P279*` subclasses of `Q11862829`
(academic discipline), then decorated in bounded `VALUES` batches to avoid
re-running the transitive closure on every page (WDQS has a hard ~60s query
timeout). 12,493 nodes with multi-parent subClassOf edges.

Two other smaller judgement calls, fully reproducible:
- **OECD-FOS** is published only as prose in the Frascati Manual 2015, so the
  canonical two-level list (6 fields + ~42 subfields) is transcribed verbatim
  rather than scraped from a fragile third-party republication.
- **MeSH** descriptor XML does not carry UMLS semantic types — those ship only
  via the licensed, auth-walled UMLS Semantic Network — so they are not
  harvested here ($0 rule); the 1.1 merge can join them later if a licence is
  obtained.

## Manners

All fetches use the polite pool only: a descriptive `User-Agent` with a contact
email, retry-with-backoff on transient/5xx, per-page sleeps on SPARQL
endpoints, and `mailto` on OpenAlex. $0 spent; no account created; no wall
defeated.

## Reproducing

```
scripts/harvest/all.sh            # all sources, then prints the summary
scripts/harvest/all.sh mesh icd   # a subset
scripts/harvest/summary.py        # re-print/refresh the summary table
```

Each parser is idempotent (overwrites its snapshot); a documented skip exits 0
with no file, an unexpected failure is retried 3× then recorded without
aborting the rest of the run.

## What Phase 1.1 will consume

The 11 `raw/<source>.json` snapshots are the sole input to the Phase 1.1
merge: normalize/clean labels, cross-link via the keys captured in `extras`
(Wikidata Q-ids on CSO/OpenAlex, `owl:sameAs`, source URIs), dedup overlapping
concepts across sources, and resolve the union of multi-parent edges into a
single coherent discipline DAG. Counts above are raw and pre-dedup — the merged
node count will be lower where sources overlap (e.g. CSO ↔ Wikidata computing,
MeSH ↔ ICD clinical terms).
