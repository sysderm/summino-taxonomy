#!/usr/bin/env python3
"""Harvest the OpenAlex taxonomy (Topics hierarchy).

Important: OpenAlex deprecated **Concepts** in 2024. The Concepts endpoint
still lists ~65k entries, but its `ancestors` and `related_concepts` fields are
now null across the board (verified on both the list and single-entity
endpoints), so Concepts no longer carries any hierarchy -- a flat bag of terms
with no parent edges. Its hierarchical successor is **Topics**, a clean
four-level classification that is exactly the "broad scaffold, ~4 levels" role
the README assigns to OpenAlex:

  4 domains -> 26 fields -> 252 subfields -> ~4,516 topics   (~4,798 nodes)

We harvest all four levels via the polite pool (mailto + 100ms sleep, $0).
Topics carry description (-> definition), keywords (-> aliases), and a
Wikipedia/Wikidata link (-> extras) for later cross-source linking.

Ids are namespaced by level to stay collision-free: domain:N, field:N,
subfield:N, topic:TN.
"""
from __future__ import annotations

import re
import time

import _common as c

BASE = "https://api.openalex.org"
MAILTO = "alexander.navarini@gmail.com"
VERSION = "OpenAlex Topics (api.openalex.org)"
SLEEP = 0.1


def _num(url: str) -> str:
    return str(url).rstrip("/").rsplit("/", 1)[-1]


def _params(**extra) -> dict:
    p = {"mailto": MAILTO, "per-page": "200"}
    p.update(extra)
    return p


def _fetch_all(client, logger, entity: str) -> list[dict]:
    """Cursor-paginate an OpenAlex entity list fully."""
    out: list[dict] = []
    cursor = "*"
    while cursor:
        resp = c.fetch(client, f"{BASE}/{entity}", logger,
                       params=_params(cursor=cursor))
        d = resp.json()
        out.extend(d["results"])
        cursor = d["meta"].get("next_cursor")
        logger.info("  %s: %d/%d", entity, len(out), d["meta"]["count"])
        if not d["results"]:
            break
        time.sleep(SLEEP)
    return out


def _wiki_ids(ids: dict) -> dict:
    ext: dict = {}
    wp = ids.get("wikipedia")
    if wp:
        ext["wikipedia"] = wp
    wd = ids.get("wikidata")
    if wd:
        m = re.search(r"(Q\d+)", wd)
        ext["wikidata"] = m.group(1) if m else wd
    return ext


def parse(logger) -> None:
    nodes: list[dict] = []
    with c.make_client(timeout=90) as client:
        domains = _fetch_all(client, logger, "domains")
        fields = _fetch_all(client, logger, "fields")
        subfields = _fetch_all(client, logger, "subfields")
        topics = _fetch_all(client, logger, "topics")

    for d in domains:
        nodes.append(c.normalize_node(
            id=f"domain:{_num(d['id'])}", name=d["display_name"], parents=[],
            definition=d.get("description"),
            extras={"kind": "domain", **_wiki_ids(d.get("ids", {}))}))
    for f in fields:
        nodes.append(c.normalize_node(
            id=f"field:{_num(f['id'])}", name=f["display_name"],
            parents=[f"domain:{_num(f['domain']['id'])}"] if f.get("domain") else [],
            definition=f.get("description"),
            extras={"kind": "field", **_wiki_ids(f.get("ids", {}))}))
    for s in subfields:
        nodes.append(c.normalize_node(
            id=f"subfield:{_num(s['id'])}", name=s["display_name"],
            parents=[f"field:{_num(s['field']['id'])}"] if s.get("field") else [],
            definition=s.get("description"),
            extras={"kind": "subfield", **_wiki_ids(s.get("ids", {}))}))
    for t in topics:
        ext = {"kind": "topic", **_wiki_ids(t.get("ids", {}))}
        if t.get("works_count") is not None:
            ext["works_count"] = t["works_count"]
        nodes.append(c.normalize_node(
            id=f"topic:{_num(t['id'])}", name=t["display_name"],
            parents=[f"subfield:{_num(t['subfield']['id'])}"] if t.get("subfield") else [],
            aliases=t.get("keywords") or [],
            definition=t.get("description"),
            extras=ext))

    ids = {n["id"] for n in nodes}
    unresolved = sum(1 for n in nodes for p in n["parents"] if p not in ids)
    if unresolved:
        logger.warning("%d unresolved parent refs", unresolved)
    from collections import Counter
    kinds = Counter(n["extras"]["kind"] for n in nodes)
    logger.info("nodes=%d kinds=%s unresolved=%d", len(nodes), dict(kinds),
                unresolved)
    if kinds["topic"] < 4000:
        raise RuntimeError(f"only {kinds['topic']} topics; expected ~4.5k")
    c.write_raw("openalex", VERSION, nodes, logger)


if __name__ == "__main__":
    raise SystemExit(c.run_parser("openalex", parse))
