# Phase 1.0 harvest summary

**11 sources harvested, 1 skipped, 128,626 total raw nodes.**

Each source is a faithful, idempotent snapshot under `raw/<source>.json` in the shared normalized schema (`id, name, parents, aliases, definition, extras`). Counts are raw node counts before the Phase 1.1 merge/dedup.

| source | version | node_count | notes |
|---|---|---:|---|
| `arxiv` | 2026-06-06 | 167 | arXiv category taxonomy scraped from the public HTML (group / archive / category). |
| `oecd-fos` | FOS-2007 (Frascati Manual 2015) | 48 | Frascati Manual 2015 FOS-2007 standard transcribed verbatim (OECD publishes no machine-readable file). |
| `scopus-asjc` | ASJC1.xlsx (Elsevier a_id/15181) | 361 | Elsevier public ASJC1.xlsx (support a_id/15181): 27 subject areas + 334 categories. |
| `msc2020` | MSC2020 (msc2020.org) | 6,603 | Mathematics Subject Classification 2020 TSV from msc2020.org. |
| `openalex` | OpenAlex Topics (api.openalex.org) | 4,798 | Topics hierarchy (4 domains -> 26 fields -> 252 subfields -> ~4.5k topics). Concepts deprecated 2024 -- its ancestors are now null, so it carries no hierarchy; Topics replaces it. |
| `physh` | PhySH SKOS (physh-org/PhySH master) | 3,988 | PhySH SKOS Turtle from the physh-org/PhySH GitHub repo (physh.org has no public API). |
| `cso` | CSO 3.5 | 14,636 | Computer Science Ontology 3.5 CSV of RDF triples. |
| `icd` | ICD-10 2019 (icd.who.int/browse10) | 12,597 | WHO ICD-10 2019 via the public auth-free browser JSON API. ICD-11 requires registering an OAuth client account, so per the $0 / no-account rule we fell back to ICD-10. |
| `mesh` | MeSH 2026 | 31,110 | MeSH 2026 descriptor XML via NLM FTP (gzip, streamed). UMLS semantic types are licensed/auth-walled and were not harvested. |
| `agris` | AGROVOC (SPARQL, agrovoc.fao.org) | 41,825 | AGRIS OAI-PMH endpoint is dead (serves the search webpage), so we harvested AGROVOC -- the FAO thesaurus the README points to -- from its public SPARQL endpoint instead. |
| `wikidata` | Wikidata (WDQS SPARQL, Q11862829 academic discipline) | 12,493 | WDQS SPARQL: items that are instance-of or transitive subclass-of Q11862829 (academic discipline), with multi-parent subClassOf edges. |
| `philpapers` | - | SKIPPED | SKIPPED: every path sits behind a Cloudflare anti-bot challenge (403) and robots.txt disallows automated collection; no standalone mirror of the category tree exists. Humanities coverage comes from OECD-FOS + Wikidata. |
| **total** | | **128,626** | 11 harvested + 1 skipped |
