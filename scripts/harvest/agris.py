#!/usr/bin/env python3
"""Harvest FAO agriculture taxonomy via AGROVOC.

The AGRIS OAI-PMH endpoint (agris.fao.org/oai) no longer serves OAI XML -- it
returns the AGRIS search web page for every verb, and AGRIS is a bibliographic
record set rather than a concept taxonomy anyway. We therefore use AGROVOC, the
FAO agricultural thesaurus and the linked-open-data concept hierarchy the
README points to, harvested from its public SPARQL endpoint.

Source: https://agrovoc.fao.org/sparql  (~41,825 skos:Concepts)
We page through three queries and join in Python:
  prefLabel@en  -> name
  skos:broader  -> parents (multi-parent kept)
  skos:altLabel@en -> aliases
AGROVOC does not expose skos:definition in the default graph (count = 0), so
definitions are left null.

Concept ids are the URI suffix (e.g. c_4788); the full URI is kept in extras.
"""
from __future__ import annotations

import time

import _common as c

EP = "https://agrovoc.fao.org/sparql"
VERSION = "AGROVOC (SPARQL, agrovoc.fao.org)"
PREFIX = "PREFIX skos: <http://www.w3.org/2004/02/skos/core#> "
PAGE = 10000
SLEEP = 1.5  # polite gap between pages; the endpoint rate-limits bursts (403)


def _local(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def _sparql_page(client, logger, query: str) -> list[dict]:
    """Issue one SPARQL query; retry up to 3x if the endpoint returns a
    non-JSON body (transient timeout/HTML error pages happen under load)."""
    last = ""
    for attempt in range(3):
        resp = c.fetch(client, EP, logger, params={"query": PREFIX + query},
                       headers={"Accept": "application/sparql-results+json"})
        try:
            return resp.json()["results"]["bindings"]
        except Exception:  # noqa: BLE001 -- non-JSON body
            last = resp.text[:200].replace("\n", " ")
            logger.warning("non-JSON SPARQL response (attempt %d): %s",
                           attempt + 1, last)
            time.sleep(15 * (attempt + 1))  # rate-limit (403) cooldown
    raise RuntimeError(f"SPARQL endpoint kept returning non-JSON: {last}")


def _paginate(client, logger, body: str, label: str) -> list[dict]:
    """Run `SELECT ... WHERE { body } ORDER BY ...` paged by LIMIT/OFFSET."""
    rows: list[dict] = []
    offset = 0
    while True:
        q = f"{body} LIMIT {PAGE} OFFSET {offset}"
        page = _sparql_page(client, logger, q)
        rows.extend(page)
        logger.info("  %s: +%d (total %d, offset %d)",
                    label, len(page), len(rows), offset)
        if len(page) < PAGE:
            break
        offset += PAGE
        time.sleep(SLEEP)
    return rows


def parse(logger) -> None:
    with c.make_client(timeout=120) as client:
        labels = _paginate(
            client, logger,
            "SELECT ?c ?l WHERE { ?c a skos:Concept ; skos:prefLabel ?l "
            "FILTER(lang(?l)='en') } ORDER BY ?c ?l", "prefLabel")
        broaders = _paginate(
            client, logger,
            "SELECT ?c ?b WHERE { ?c a skos:Concept ; skos:broader ?b } "
            "ORDER BY ?c ?b", "broader")
        alts = _paginate(
            client, logger,
            "SELECT ?c ?a WHERE { ?c a skos:Concept ; skos:altLabel ?a "
            "FILTER(lang(?a)='en') } ORDER BY ?c ?a", "altLabel")

    names: dict[str, str] = {}
    for r in labels:
        uri = r["c"]["value"]
        names.setdefault(uri, r["l"]["value"])

    parents: dict[str, set[str]] = {}
    for r in broaders:
        parents.setdefault(r["c"]["value"], set()).add(r["b"]["value"])

    aliases: dict[str, set[str]] = {}
    for r in alts:
        aliases.setdefault(r["c"]["value"], set()).add(r["a"]["value"])

    nodes: list[dict] = []
    for uri in sorted(names):
        nodes.append(c.normalize_node(
            id=_local(uri), name=names[uri],
            parents=sorted(_local(p) for p in parents.get(uri, ())),
            aliases=sorted(aliases.get(uri, ())),
            extras={"uri": uri}))

    ids = {n["id"] for n in nodes}
    unresolved = sum(1 for n in nodes for p in n["parents"] if p not in ids)
    with_parents = sum(1 for n in nodes if n["parents"])
    logger.info("concepts=%d with_parents=%d aliased=%d unresolved_parents=%d",
                len(nodes), with_parents,
                sum(1 for n in nodes if n["aliases"]), unresolved)
    if len(nodes) < 30000:
        raise RuntimeError(f"only {len(nodes)} concepts; expected ~41.8k")
    c.write_raw("agris", VERSION, nodes, logger)


if __name__ == "__main__":
    raise SystemExit(c.run_parser("agris", parse))
