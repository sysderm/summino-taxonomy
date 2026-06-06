# summino-taxonomy

Universal scientific taxonomy for summino. The goal: thousands of fine-grained,
multi-parent, multi-label nodes covering **all of science** — so every paper
can be tagged with one or more leaves at the right level of specificity.

This is the **strategic asset** behind summino's classification quality.
Rivals stop at ~50 disciplines; we go to thousands.

## Output shape

`taxonomy.yaml` (versioned, semver), assembled in three steps:

1. **Harvest** raw snapshots of every major scientific classification system
   into `raw/<source>.json`.
2. **Merge + DAG-build** across sources into `merged/dag.json`, identifying
   cross-source equivalences and cross-cutting nodes.
3. **Deepen** each branch with LLM-driven recursive decomposition into
   `taxonomy.yaml`. Final artifact.

## Node schema

Each node:

```yaml
- slug: psoriasis-genetics                       # canonical, kebab-case, unique
  name: Psoriasis genetics                       # human-readable
  parents: [psoriasis, dermatology-genetics, autoimmune-disease-genetics]
  level: 5                                       # depth of the SHORTEST path to a root
  definition: "Genetic and genomic determinants of psoriasis vulgaris and variants."
  aliases: [psoriasis genomics, PsO genetics]
  example_titles:
    - "GWAS identifies HLA-Cw6 as primary risk locus in psoriasis"
    - "IL-23 receptor variants in pustular psoriasis"
  source_ids:
    mesh: D011565
    icd11: EA90
    openalex: T11783
  related: [psoriasis-immunology, hla-genetics]   # informational links, NOT parents
```

Key properties:

- **DAG, not tree:** `parents` is a list. A node like `bioinformatics` has
  parents in both `biology` and `computer-science`.
- **Multi-label by construction:** any paper can carry an arbitrary set of
  leaf slugs.
- **Stopping rule:** a leaf must plausibly have **≥ 20 papers/year** in the
  literature. Smaller niches roll up.
- **Target size:** ~2,000–5,000 leaves, max ~6 levels deep.
- **Modern fields explicitly covered:** CRISPR genome editing, LLM safety,
  mRNA therapeutics, photonic computing, etc. — anything that didn't exist
  10 years ago but is now load-bearing science.

## Source taxonomies harvested

See `raw/` for parsed snapshots, schema common across sources:

```json
{
  "source": "mesh",
  "version": "2026",
  "harvested_at": "2026-06-06T...",
  "nodes": [
    {"id": "D011565", "name": "Psoriasis",
     "parents": ["D003872"], "aliases": ["..."],
     "definition": "...", "extras": {"tree_numbers": ["C17.800.859.675"]}}
  ]
}
```

| Source | Coverage | Granularity | Role |
|---|---|---|---|
| **MeSH** (NLM) | biomedical | ~30k descriptors | medicine + biology depth |
| **OpenAlex Concepts** | all science | ~65k concepts, 4 levels | broad scaffold |
| **arXiv categories** | CS/physics/math | ~150 leaves | CS/physics/math leaves |
| **MSC2020** | mathematics | ~5,000 codes | math depth |
| **PhySH** | physics | ~3,000 nodes | physics depth |
| **PhilPapers** | philosophy | ~5,000 | humanities |
| **CSO** (Computer Science Ontology) | CS | ~14k concepts | CS depth |
| **ICD-11** | clinical | ~17k | medical specifics |
| **AGRIS** (FAO) | agriculture | ag/forestry | ag depth |
| **Scopus ASJC** | all science | ~340 mid-level | scaffold cross-check |
| **OECD FOS / Frascati** | all science | ~40 high-level | top-level scaffold |
| **Wikidata Q-items** | everything | inconsistent but exhaustive | gap-fill, modern fields |

EMTREE (Embase) is paid-only — skipped unless we get a license.

## Build process

| Phase | Job | Owner | Output |
|---|---|---|---|
| 1.0 | Harvest all sources to `raw/<source>.json` | hetz·s1 | `raw/` |
| 1.1 | Merge + DAG construction, cross-source equivalence map | hetz | `merged/dag.json` |
| 1.2a | Medicine branch deep-dive (MeSH + ICD-11 + UMLS-grounded LLM) | hetz | `branches/medicine.yaml` |
| 1.2b | Biology branch deep-dive | hetz | `branches/biology.yaml` |
| 1.2c | Physics branch (PhySH + arXiv) | hetz | `branches/physics.yaml` |
| 1.2d | Chemistry branch (IUPAC + PubChem) | hetz | `branches/chemistry.yaml` |
| 1.2e | CS branch (CSO + ACM CCS + arXiv) | hetz | `branches/computer-science.yaml` |
| 1.2f | Math branch (MSC2020 + arXiv) | hetz | `branches/mathematics.yaml` |
| 1.2g | Earth & environment | hetz | `branches/earth-env.yaml` |
| 1.2h | Engineering (IEEE + ASTM) | hetz | `branches/engineering.yaml` |
| 1.2i | Social sciences (PsycINFO + LCC) | hetz | `branches/social-sciences.yaml` |
| 1.2j | Humanities (PhilPapers + LCC) | hetz | `branches/humanities.yaml` |
| 1.3 | Cross-cutting nodes (multi-parent) | hetz | `branches/cross-cutting.yaml` |
| 1.4 | Modern-field sweep (LLM-driven, last 10 years) | hetz | `branches/modern-fields.yaml` |
| 1.5 | Coverage validator: sample 1000 random crossref papers; report miss rate | mac | `reports/coverage-v1.md` |
| 1.6 | Alex manual derm + clinical review | operator | (PR review) |
| 1.7 | Assemble final `taxonomy.yaml` v1.0.0 | hetz | `taxonomy.yaml` + `CHANGELOG.md` |

After Phase 1 ships → Phase 2 (gold-label ~10-50k abstracts with a paid model
using the taxonomy as cached context) → Phase 3 (train multi-label local
classifier — SPECTER2 / ModernBERT base + sigmoid heads).

## Versioning

Semver. v1.0.0 = first usable. Breaking changes (renamed slug, removed node,
changed parent edges) bump major. Additive changes bump minor. Definition /
example tweaks bump patch. Each release is a git tag with a CHANGELOG entry
listing slug additions / deletions / renames.
