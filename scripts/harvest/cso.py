#!/usr/bin/env python3
"""Harvest the Computer Science Ontology (CSO).

Source: https://cso.kmi.open.ac.uk/download/version-3.5/CSO.3.5.csv.zip
A zipped CSV of RDF triples (subject, predicate, object), ~166k rows over
~14.6k topics.

Predicates used:
  cso#superTopicOf        A superTopicOf B  -> B has parent A   (hierarchy)
  rdfs:label              topic -> human label
  owl:sameAs              topic -> external URI (DBpedia/Wikidata/...)
  cso#preferentialEquivalent  variant -> canonical surface form

This is a faithful raw snapshot: all labelled topics are kept as nodes; the
preferential-equivalent and sameAs links are recorded in `extras` for the
later merge/DAG phase to fold and cross-link (Wikidata Q-ids are pulled out
explicitly since they are the most useful cross-source key).
"""
from __future__ import annotations

import csv
import io
import re
import zipfile

import _common as c

URL = "https://cso.kmi.open.ac.uk/download/version-3.5/CSO.3.5.csv.zip"
VERSION = "CSO 3.5"

TOPIC_PREFIX = "https://cso.kmi.open.ac.uk/topics/"
P_SUPER = "http://cso.kmi.open.ac.uk/schema/cso#superTopicOf"
P_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
P_SAME = "http://www.w3.org/2002/07/owl#sameAs"
P_PREF = "http://cso.kmi.open.ac.uk/schema/cso#preferentialEquivalent"

_LANG_TAIL = re.compile(r'@[A-Za-z-]+\s*\.?\s*$')
_WIKIDATA = re.compile(r"wikidata\.org/entity/(Q\d+)")


def _uri(field: str) -> str:
    s = field.strip()
    if s.startswith("<") and s.endswith(">"):
        return s[1:-1]
    return s


def _literal(field: str) -> str:
    """Clean an N-Triples literal that survived CSV parsing, e.g.
    'zoogeography@en .' -> 'zoogeography'."""
    s = field.strip()
    if s.endswith("."):
        s = s[:-1].rstrip()
    s = _LANG_TAIL.sub("", s).strip()
    return s.strip('"').replace("_", " ").strip()


def _local(uri: str) -> str:
    return uri.rsplit("/topics/", 1)[-1] if "/topics/" in uri else uri


def parse(logger) -> None:
    with c.make_client() as client:
        resp = c.fetch(client, URL, logger)
    logger.info("fetched %s (%d bytes)", URL, len(resp.content))

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
    data = zf.read(csv_name).decode("utf-8", errors="replace")

    labels: dict[str, str] = {}
    parents: dict[str, set[str]] = {}
    same_as: dict[str, list[str]] = {}
    pref: dict[str, str] = {}

    reader = csv.reader(io.StringIO(data))
    for row in reader:
        if len(row) < 3:
            continue
        s = _uri(row[0])
        p = _uri(row[1])
        if p == P_LABEL:
            labels[s] = _literal(row[2])
        elif p == P_SUPER:
            child = _uri(row[2])
            parents.setdefault(child, set()).add(s)
        elif p == P_SAME:
            same_as.setdefault(s, []).append(_uri(row[2]))
        elif p == P_PREF:
            o = _uri(row[2])
            if o != s:
                pref[s] = o

    if not labels:
        raise RuntimeError("no labels parsed from CSO")

    nodes: list[dict] = []
    for uri, label in sorted(labels.items()):
        lid = _local(uri)
        node_parents = sorted(_local(p) for p in parents.get(uri, ()))
        ext: dict = {"uri": uri}
        sa = same_as.get(uri)
        if sa:
            ext["same_as"] = sorted(sa)
            qids = sorted({m.group(1) for u in sa
                           for m in [_WIKIDATA.search(u)] if m})
            if qids:
                ext["wikidata"] = qids
        if uri in pref:
            ext["preferential_equivalent"] = _local(pref[uri])
        nodes.append(c.normalize_node(
            id=lid, name=label, parents=node_parents, extras=ext))

    # Validate parent references resolve to known topics.
    ids = {n["id"] for n in nodes}
    unresolved = sum(1 for n in nodes for p in n["parents"] if p not in ids)
    if unresolved:
        logger.warning("%d parent references not in node set", unresolved)
    with_parents = sum(1 for n in nodes if n["parents"])
    logger.info("topics=%d with_parents=%d sameAs=%d pref_variants=%d",
                len(nodes), with_parents, len(same_as), len(pref))
    if len(nodes) < 10000:
        raise RuntimeError(f"only {len(nodes)} topics; expected ~14.6k")
    c.write_raw("cso", VERSION, nodes, logger)


if __name__ == "__main__":
    raise SystemExit(c.run_parser("cso", parse))
