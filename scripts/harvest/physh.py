#!/usr/bin/env python3
"""Harvest PhySH (Physics Subject Headings).

physh.org has no public API; the authoritative data is published as RDF in the
physh-org/PhySH GitHub repo. We use the SKOS-compatible Turtle
(physh_skos_compat.ttl), ~3,969 concepts + 19 concept schemes (top-level
physics disciplines).

SKOS mapping:
  skos:broader / skos:topConceptOf  -> parents
  skos:prefLabel                    -> name
  skos:altLabel / skos:hiddenLabel  -> aliases
  skos:scopeNote                    -> definition
  skos:related                      -> extras.related

Concept/scheme ids are UUIDs (the suffix of the https://doi.org/10.29172/<uuid>
identifier); the full URI is kept in extras.
"""
from __future__ import annotations

import rdflib
from rdflib.namespace import RDF, SKOS, DCTERMS, RDFS

import _common as c

URL = "https://raw.githubusercontent.com/physh-org/PhySH/master/physh_skos_compat.ttl"
VERSION = "PhySH SKOS (physh-org/PhySH master)"


def _local(uri: str) -> str:
    s = str(uri)
    for sep in ("#", "/"):
        if sep in s:
            tail = s.rsplit(sep, 1)[-1]
            if tail:
                s = tail
    return s


def parse(logger) -> None:
    with c.make_client() as client:
        resp = c.fetch(client, URL, logger)
    logger.info("fetched %s (%d bytes)", URL, len(resp.content))

    g = rdflib.Graph()
    g.parse(data=resp.content, format="turtle")
    logger.info("parsed graph: %d triples", len(g))

    subjects = set(g.subjects(RDF.type, SKOS.Concept))
    subjects |= set(g.subjects(RDF.type, SKOS.ConceptScheme))

    nodes: list[dict] = []
    n_schemes = 0
    for s in sorted(subjects, key=str):
        is_scheme = (s, RDF.type, SKOS.ConceptScheme) in g
        if is_scheme:
            n_schemes += 1

        name = (g.value(s, SKOS.prefLabel) or g.value(s, DCTERMS.title)
                or g.value(s, RDFS.label))
        name = str(name) if name is not None else _local(s)

        parents = sorted({_local(o) for o in g.objects(s, SKOS.broader)}
                         | {_local(o) for o in g.objects(s, SKOS.topConceptOf)})

        aliases = sorted({str(o) for o in g.objects(s, SKOS.altLabel)}
                         | {str(o) for o in g.objects(s, SKOS.hiddenLabel)})

        note = g.value(s, SKOS.scopeNote)
        definition = str(note) if note is not None else None

        related = sorted({_local(o) for o in g.objects(s, SKOS.related)})
        ext: dict = {"uri": str(s),
                     "kind": "scheme" if is_scheme else "concept"}
        if related:
            ext["related"] = related

        nodes.append(c.normalize_node(
            id=_local(s), name=name, parents=parents,
            aliases=aliases, definition=definition, extras=ext))

    ids = {n["id"] for n in nodes}
    unresolved = sum(1 for n in nodes for p in n["parents"] if p not in ids)
    if unresolved:
        logger.warning("%d parent refs not in node set", unresolved)
    logger.info("concepts=%d schemes=%d roots=%d",
                len(nodes) - n_schemes, n_schemes,
                sum(1 for n in nodes if not n["parents"]))
    if len(nodes) < 3000:
        raise RuntimeError(f"only {len(nodes)} nodes; expected ~3.9k")
    c.write_raw("physh", VERSION, nodes, logger)


if __name__ == "__main__":
    raise SystemExit(c.run_parser("physh", parse))
