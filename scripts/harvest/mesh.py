#!/usr/bin/env python3
"""Harvest MeSH descriptors (NLM Medical Subject Headings).

Source: the bulk descriptor XML at
  https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc<YEAR>.xml
(falls back 2026 -> 2025 -> 2024). We download the gzip sibling (desc<YEAR>.gz,
~17 MB vs ~313 MB uncompressed) and stream it through defusedxml's iterparse,
clearing each <DescriptorRecord> after processing so memory stays flat.

Hierarchy: MeSH descriptors are positioned by dotted TreeNumbers
(e.g. D02.705.400.625.800). We first build a TreeNumber -> DescriptorUI map,
then resolve each descriptor's parents by dropping the last dotted segment of
each of its tree numbers and looking up the owning descriptor. A descriptor
with several tree numbers gets several parents (multi-parent DAG). Top-of-tree
descriptors (single-letter category, no dotted parent) become roots.

Per node:
  id         DescriptorUI (e.g. D000001)
  name       DescriptorName/String
  aliases    all TermList/Term/String across concepts (minus the name)
  definition preferred Concept's ScopeNote (else any ScopeNote)
  extras     tree_numbers

Note: MeSH semantic types are NOT present in the descriptor XML -- they are
distributed only via the UMLS Semantic Network mapping, which is licensed and
auth-walled, so per the $0 rule they are not harvested here. The 1.1 merge can
join them later from UMLS if a licence is obtained.
"""
from __future__ import annotations

import gzip
import tempfile

from defusedxml.ElementTree import iterparse

import _common as c

BASE = "https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh"
YEARS = [2026, 2025, 2024]


def _download_gz(client, logger) -> tuple[str, str]:
    """Stream the first available desc<year>.gz to a temp file. Returns
    (temp_path, version). httpx transparently decodes Content-Encoding: gzip,
    so the temp file may end up as plain XML or as a raw gzip payload; the
    caller detects which by magic bytes."""
    for year in YEARS:
        url = f"{BASE}/desc{year}.gz"
        with client.stream("GET", url, follow_redirects=True) as resp:
            ctype = resp.headers.get("content-type", "")
            if resp.status_code != 200 or "html" in ctype.lower():
                logger.warning("desc%d.gz unavailable (status=%s ctype=%s)",
                               year, resp.status_code, ctype)
                continue
            tmp = tempfile.NamedTemporaryFile(
                prefix=f"mesh{year}_", suffix=".bin", delete=False)
            total = 0
            for chunk in resp.iter_bytes(chunk_size=1 << 20):
                tmp.write(chunk)
                total += len(chunk)
            tmp.close()
            logger.info("downloaded %s -> %s (%d bytes on disk)",
                        url, tmp.name, total)
            return tmp.name, f"MeSH {year}"
    raise RuntimeError("no MeSH descriptor file available for any year")


def _open_xml(path: str):
    """Open path as an XML byte stream whether it is gzip or already-plain."""
    with open(path, "rb") as fh:
        magic = fh.read(2)
    if magic == b"\x1f\x8b":
        return gzip.open(path, "rb")
    return open(path, "rb")


def _text(elem, path) -> str | None:
    node = elem.find(path)
    return node.text.strip() if (node is not None and node.text) else None


def parse(logger) -> None:
    with c.make_client(timeout=180) as client:
        path, version = _download_gz(client, logger)

    descriptors: list[dict] = []
    tn_to_ui: dict[str, str] = {}

    with _open_xml(path) as fh:
        for event, elem in iterparse(fh, events=("end",)):
            if elem.tag != "DescriptorRecord":
                continue
            ui = _text(elem, "DescriptorUI")
            name = _text(elem, "DescriptorName/String")
            if not ui or not name:
                elem.clear()
                continue

            tree_numbers = [t.text.strip() for t in
                            elem.findall("TreeNumberList/TreeNumber")
                            if t.text]
            for tn in tree_numbers:
                tn_to_ui[tn] = ui

            aliases: set[str] = set()
            definition: str | None = None
            for concept in elem.findall("ConceptList/Concept"):
                preferred = concept.get("PreferredConceptYN") == "Y"
                note = _text(concept, "ScopeNote")
                if note and (preferred or definition is None):
                    definition = note
                for term in concept.findall("TermList/Term/String"):
                    if term.text:
                        aliases.add(term.text.strip())
            aliases.discard(name)

            descriptors.append({
                "ui": ui, "name": name, "tree_numbers": tree_numbers,
                "aliases": sorted(aliases), "definition": definition,
            })
            elem.clear()

    if not descriptors:
        raise RuntimeError("parsed zero descriptors")
    logger.info("parsed %d descriptors, %d tree numbers",
                len(descriptors), len(tn_to_ui))

    nodes: list[dict] = []
    multi_parent = 0
    for d in descriptors:
        parents: set[str] = set()
        for tn in d["tree_numbers"]:
            if "." in tn:
                parent_tn = tn.rsplit(".", 1)[0]
                puid = tn_to_ui.get(parent_tn)
                if puid and puid != d["ui"]:
                    parents.add(puid)
        if len(parents) > 1:
            multi_parent += 1
        nodes.append(c.normalize_node(
            id=d["ui"], name=d["name"], parents=sorted(parents),
            aliases=d["aliases"], definition=d["definition"],
            extras={"tree_numbers": d["tree_numbers"]}))

    ids = {n["id"] for n in nodes}
    unresolved = sum(1 for n in nodes for p in n["parents"] if p not in ids)
    roots = sum(1 for n in nodes if not n["parents"])
    logger.info("descriptors=%d roots=%d multi_parent=%d unresolved=%d",
                len(nodes), roots, multi_parent, unresolved)
    if len(nodes) < 25000:
        raise RuntimeError(f"only {len(nodes)} descriptors; expected ~30k")
    c.write_raw("mesh", version, nodes, logger)


if __name__ == "__main__":
    raise SystemExit(c.run_parser("mesh", parse))
