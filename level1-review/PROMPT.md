# Design the first level of an "all of science" reader taxonomy

You are designing **level 1** (top-level categories) for a scientific paper
reader app. The app aggregates ~5,000 new papers per day from PubMed, arXiv,
OpenAlex, Crossref, bioRxiv, Cochrane, Bluesky academic feed, and ~30 other
sources. Users are professional researchers, clinicians, engineers, and
graduate students; the app surfaces papers with AI-generated headlines and
summaries on a personalized "today" feed.

## What you are designing

The **user-facing level 1**. When a new user signs up, they see a single
screen with a grid of category cards and pick the ones they care about.
This list IS that grid. There is a separate ~120,000-node deep taxonomy
the classifier uses internally; users never see it. Your job is the
**human-facing top.**

## Hard constraints

- **Count: between 12 and 25 categories.** Fewer than 12 feels insulting
  ("only 8 sciences?"). More than 25 turns the picker into a scrolling
  list. The sweet spot is "feels impressively broad on one screen."
- **Cover ALL of science.** Pure science, applied science/engineering,
  medicine + clinical practice, social sciences, humanities-adjacent
  fields that publish empirical work (linguistics, economics,
  experimental psychology, archaeology). If a Nature paper, an arXiv
  preprint, a Cochrane review, an INSPEC engineering report, and an
  Annual Review of Anthropology paper all came in tomorrow, **every one
  must map to exactly one of your categories.**
- **MECE-leaning.** Categories should not visibly overlap to a user.
  ("Chemistry" and "Biochemistry" overlap; pick one or distinguish them
  clearly. "Medicine" and "Public Health" overlap; same.)
- **Each category must feel like something a smart 22-year-old
  graduate student would actually pick as their identity.** "Computer
  Science", yes. "Knowledge Engineering", no. "Medicine", yes.
  "Health Sciences", no — it sounds bureaucratic.
- **Audience size matters.** A category with <1% of new papers is wasted
  space on the picker. A category with >25% is too coarse and forces
  splitting later.

## What you are NOT designing

- Level 2 (subspecialties) — that's a separate prompt. Stay at level 1.
- The deep classifier taxonomy — that already exists.
- Icons, colors, taglines for the UI — those come after the names are
  fixed.

## Reference data — what other taxonomies put at this level

Just for calibration. Do not adopt verbatim:

| Source taxonomy | # of top-level categories |
|---|---|
| arXiv | 3 (math, physics, CS) |
| Scopus ASJC | 2 (life sciences, physical sciences) |
| OECD-FoS | 2 (natural, social) |
| AGRIS | 21 (agricultural sciences) |
| MeSH | 76 (medical) |
| MSC 2020 | 42 (math) |
| ICD-11 | 18 (clinical) |
| PhySH | 11 (physics) |

The summino harvest merged 11 source taxonomies into a 120,689-node DAG
with 1,714 roots, but most of those roots are nonsense artifacts
(Wikidata alone contributes 1,540). The professional curators converge
around 11–25 top-level categories. Aim there.

## Required output format

Return a single JSON object with this exact shape, no markdown fence:

```
{
  "count": 18,
  "rationale": "One paragraph (3-5 sentences) explaining your structural choice. Why this count? What's the principle that distinguishes one category from the next? What did you deliberately NOT split that you considered?",
  "categories": [
    {
      "slug": "kebab-case-id",
      "name": "Title Case Display Name",
      "tagline": "A short 5-12 word description for the picker card.",
      "audience_size_pct": 12.5,
      "covers": ["one-line description of what fits here", "specific examples of papers/journals"],
      "explicitly_excludes": ["adjacent thing that goes elsewhere — name the other category"]
    }
  ],
  "uncovered_concerns": ["one-line note for anything you considered including but didn't, with reasoning"]
}
```

## How your output will be used

Three models will be asked the same question (you, Gemini 2.5 Pro, GPT-5).
The operator will diff the three outputs. Where 2 of 3 agree on a
category, it ships. Where you disagree, the operator decides.

So: don't try to be uniquely creative. Try to be **right.** Aim at the
answer a senior university librarian, a med-school dean, and an arXiv
moderator would all converge on.
