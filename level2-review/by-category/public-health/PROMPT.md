# Design the level-2 subspecialties for: Public Health & Epidemiology

You are designing **level 2** for a scientific paper reader app. The user
already picked their level-1 category at onboarding (Public Health & Epidemiology). On the
next screen they see a grid of subspecialties under it. Your job is to
design that grid.

## Level-1 context

**Category:** Public Health & Epidemiology
**Tagline:** Populations, prevention, policy, global health.
**Covers:** epidemiology, biostatistics, health policy, global health, environmental health; Cochrane reviews; WHO data; outbreak modeling
**Audience size at level 1:** 5% of all new science papers
**Explicitly excludes (goes to other level-1 categories):** individual-patient care → Medicine; lab pathogen work → Biology

## Hard constraints

- **Count: between 8 and 25 subspecialties.** Fewer than 8 feels thin
  for Public Health & Epidemiology ("only 5 things in all of X?"). More than 25 makes the
  picker grid noisy.
- **MECE-leaning.** A paper that fits Public Health & Epidemiology should map to exactly
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
{
  "level1_slug": "public-health",
  "level1_name": "Public Health & Epidemiology",
  "count": 14,
  "rationale": "One paragraph (3-5 sentences) explaining your structural choice for THIS level-1 category. Why this count? What did you deliberately NOT split that you considered? What did you split that's controversial?",
  "subspecialties": [
    {
      "slug": "kebab-case-id",
      "name": "Working Title (how practitioners say it)",
      "tagline": "5-12 words for the picker card",
      "audience_pct_within_level1": 18.5,
      "covers": ["one-line description", "specific examples"],
      "explicitly_excludes": ["adjacent thing that goes elsewhere — name the other level-2 category"]
    }
  ],
  "uncovered_concerns": ["one-line notes for anything you considered but didn't ship, with reasoning"]
}
```

## How your output will be used

Three models will be asked the same question (Opus 4.8, Gemini 2.5 Pro,
GPT-5). The operator will diff the three. Where 2 of 3 agree on a
subspecialty, it ships. Where you disagree, Fable (Opus) arbitrates.
