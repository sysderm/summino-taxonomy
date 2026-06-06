#!/usr/bin/env python3
"""Harvest academic disciplines from Wikidata via WDQS SPARQL.

Source: https://query.wikidata.org/sparql

We take the set of items that are either an *instance of* (wdt:P31) or a
transitive *subclass of* (wdt:P279*) "academic discipline" (wd:Q11862829).
This yields the cross-domain discipline/sub-discipline graph Wikidata models,
~10-20k items, with full multi-parent subClassOf edges.

WDQS has a hard ~60s server-side query timeout, so we do NOT re-run the
transitive P279* closure on every paged query (which would recompute the whole
tree per page and time out at deep offsets). Instead:

  1. Membership: two cheap single-column queries (P31 instances, P279*
     subclasses), each paged ORDER BY ?x LIMIT 1000, unioned in Python.
  2. Decoration: the QID set is split into bounded VALUES batches; per batch we
     fetch labels + descriptions + P279 parents in one query and altLabels in a
     second (kept separate so aliases x parents don't cross-multiply rows).

Mapping (all @en):
  rdfs:label        -> name
  wdt:P279          -> parents (QIDs, multi-parent kept, may point outside set)
  skos:altLabel     -> aliases
  schema:description-> definition

ids are the bare QID (e.g. Q413); the full entity URI is kept in extras.

If a membership page fails after retries we stop paging and harvest what we
have (partial), rather than aborting -- the count is logged and surfaced.
"""
from __future__ import annotations

import time

import _common as c

EP = "https://query.wikidata.org/sparql"
VERSION = "Wikidata (WDQS SPARQL, Q11862829 academic discipline)"
ROOT = "wd:Q11862829"  # academic discipline
PREFIXES = (
    "PREFIX wd: <http://www.wikidata.org/entity/> "
    "PREFIX wdt: <http://www.wikidata.org/prop/direct/> "
    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
    "PREFIX schema: <http://schema.org/> "
    "PREFIX skos: <http://www.w3.org/2004/02/skos/core#> "
)
PAGE = 1000     # membership rows per page (per user spec)
BATCH = 200     # QIDs per decoration VALUES block
SLEEP = 1.0     # polite gap between requests


def _local(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def _sparql(client, logger, query: str) -> list[dict]:
    """One SPARQL query (POST); retry up to 3x on a non-JSON body (WDQS emits
    an HTML/text Java exception page on timeout or throttle)."""
    last = ""
    for attempt in range(3):
        resp = c.fetch(
            client, EP, logger, method="POST",
            data={"query": PREFIXES + query, "format": "json"},
            headers={"Accept": "application/sparql-results+json"},
        )
        try:
            return resp.json()["results"]["bindings"]
        except Exception:  # noqa: BLE001 -- non-JSON body (timeout/throttle)
            last = resp.text[:200].replace("\n", " ")
            logger.warning("non-JSON WDQS response (attempt %d): %s",
                           attempt + 1, last)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"WDQS kept returning non-JSON: {last}")


def _paginate(client, logger, body: str, label: str) -> list[str]:
    """Page `SELECT ?x WHERE { body } ORDER BY ?x` by LIMIT/OFFSET, returning
    QID URIs. Stops early (partial) if a page keeps failing."""
    out: list[str] = []
    offset = 0
    while True:
        q = f"SELECT ?x WHERE {{ {body} }} ORDER BY ?x LIMIT {PAGE} OFFSET {offset}"
        try:
            page = _sparql(client, logger, q)
        except RuntimeError as e:
            logger.warning("  %s: page at offset %d failed, stopping early "
                           "(partial): %s", label, offset, e)
            break
        out.extend(r["x"]["value"] for r in page)
        logger.info("  %s: +%d (total %d, offset %d)",
                    label, len(page), len(out), offset)
        if len(page) < PAGE:
            break
        offset += PAGE
        time.sleep(SLEEP)
    return out


def _batches(items: list[str], n: int):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def parse(logger) -> None:
    names: dict[str, str] = {}
    descs: dict[str, str] = {}
    parents: dict[str, set[str]] = {}
    aliases: dict[str, set[str]] = {}

    with c.make_client(timeout=120) as client:
        # 1. membership: instances + transitive subclasses of academic discipline
        members = set(_paginate(
            client, logger, f"?x wdt:P31 {ROOT}", "instances"))
        time.sleep(SLEEP)
        members |= set(_paginate(
            client, logger, f"?x wdt:P279* {ROOT}", "subclasses"))
        qids = sorted(members, key=lambda u: int(_local(u)[1:]))
        logger.info("members=%d (unique QIDs); decorating in batches of %d",
                    len(qids), BATCH)
        if not qids:
            raise RuntimeError("WDQS returned zero members; aborting")

        # 2. decoration via bounded VALUES batches
        for bi, batch in enumerate(_batches(qids, BATCH)):
            values = " ".join(f"<{u}>" for u in batch)
            ld = _sparql(client, logger,
                         "SELECT ?x ?l ?d ?p WHERE { VALUES ?x { " + values + " } "
                         "OPTIONAL { ?x rdfs:label ?l FILTER(lang(?l)='en') } "
                         "OPTIONAL { ?x schema:description ?d FILTER(lang(?d)='en') } "
                         "OPTIONAL { ?x wdt:P279 ?p } }")
            for r in ld:
                u = r["x"]["value"]
                if "l" in r:
                    names.setdefault(u, r["l"]["value"])
                if "d" in r:
                    descs.setdefault(u, r["d"]["value"])
                if "p" in r:
                    parents.setdefault(u, set()).add(r["p"]["value"])
            time.sleep(SLEEP)

            al = _sparql(client, logger,
                         "SELECT ?x ?a WHERE { VALUES ?x { " + values + " } "
                         "?x skos:altLabel ?a FILTER(lang(?a)='en') }")
            for r in al:
                aliases.setdefault(r["x"]["value"], set()).add(r["a"]["value"])
            logger.info("  batch %d/%d decorated (%d qids)",
                        bi + 1, (len(qids) + BATCH - 1) // BATCH, len(batch))
            time.sleep(SLEEP)

    nodes: list[dict] = []
    for u in qids:
        nodes.append(c.normalize_node(
            id=_local(u),
            name=names.get(u, _local(u)),
            parents=sorted((_local(p) for p in parents.get(u, ())),
                           key=lambda q: int(q[1:])),
            aliases=sorted(aliases.get(u, ())),
            definition=descs.get(u),
            extras={"uri": u}))

    ids = {n["id"] for n in nodes}
    unresolved = sum(1 for n in nodes for p in n["parents"] if p not in ids)
    logger.info("nodes=%d named=%d with_parents=%d aliased=%d defined=%d "
                "unresolved_parents=%d",
                len(nodes), sum(1 for n in nodes if n["name"] != n["id"]),
                sum(1 for n in nodes if n["parents"]),
                sum(1 for n in nodes if n["aliases"]),
                sum(1 for n in nodes if n["definition"]), unresolved)
    if len(nodes) < 2000:
        raise RuntimeError(
            f"only {len(nodes)} nodes; expected ~10-20k (likely WDQS failure)")
    c.write_raw("wikidata", VERSION, nodes, logger)


if __name__ == "__main__":
    raise SystemExit(c.run_parser("wikidata", parse))
