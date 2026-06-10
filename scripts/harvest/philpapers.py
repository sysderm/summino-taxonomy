#!/usr/bin/env python3
"""Harvest the PhilPapers categorization taxonomy -- SKIPPED (bot wall).

Status (2026-06): every PhilPapers path (/browse/, /categories.html, the
/utils/ JSON API) sits behind a Cloudflare "Just a moment..." JavaScript
anti-bot challenge that returns HTTP 403 to any non-browser client. The site's
robots.txt also prohibits automated collection except for search-engine
indexing or AI RAG retrieval, and the /utils/ API path is Disallowed.

Per the Phase 1.0 hard rules we fail-fast on access walls: we do NOT defeat
the Cloudflare challenge (that is anti-bot evasion, out of scope) and we never
pay. A scan of public GitHub mirrors (BassP97/Philpapers-API,
inpho/philpapers-data, inpho/mocs-philpapers) found only scraper scripts that
themselves call the walled API -- no standalone copy of the category tree.

This parser attempts the polite fetch each run; if the wall is present it
records a SkipSource (no raw/philpapers.json is written). Humanities coverage
is instead carried by OECD-FOS (6.x), Wikidata academic disciplines, and the
LCC-based humanities branch planned for Phase 1.2j.

To enable later: obtain written permission / an API key from the PhilPapers
operator, then parse the category tree from the authorised endpoint.
"""
from __future__ import annotations

import _common as c

URL = "https://philpapers.org/browse/"


def parse(logger) -> None:
    with c.make_client() as client:
        resp = c.fetch(client, URL, logger)

    body_head = resp.text[:500].lower()
    challenged = ("just a moment" in body_head
                  or "challenges.cloudflare.com" in body_head)
    if resp.status_code == 403 or challenged:
        raise c.SkipSource(
            f"Cloudflare anti-bot wall (HTTP {resp.status_code}); robots.txt "
            "prohibits scraping. No free, permitted machine-readable source "
            "for the category tree. Skipped per $0/no-evasion rules.")

    # If PhilPapers ever drops the wall, this parser would need a real DOM
    # parser here. Until then, a non-403 response is unexpected -- surface it.
    raise c.SkipSource(
        f"Unexpected non-challenge response (HTTP {resp.status_code}); "
        "no parser implemented because the source has always been walled. "
        "Revisit if access is granted.")


if __name__ == "__main__":
    raise SystemExit(c.run_parser("philpapers", parse))
