#!/usr/bin/env python3
"""Harvest the arXiv category taxonomy.

Source: https://arxiv.org/category_taxonomy (HTML).

Structure on the page:
  h2  -> group        e.g. "Computer Science"            (top level, no code)
  h3  -> archive      e.g. "Astrophysics (astro-ph)"     (mostly Physics)
  h4  -> category     e.g. "cs.AI (Artificial Intelligence)"  (the leaves)

For h4 the code comes BEFORE the parenthesised name; for h3 the code is the
parenthesised part. h4 leaves attach to the nearest preceding h3 within their
group, or directly to the group if that group has no archive subdivision.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

import _common as c

URL = "https://arxiv.org/category_taxonomy"


def _slug(text: str) -> str:
    return "group:" + re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _split_span(header) -> tuple[str, str]:
    """Return (main_text, span_text) for an h3/h4 header."""
    span = header.find("span")
    span_text = span.get_text(" ", strip=True) if span else ""
    full = header.get_text(" ", strip=True)
    main = full.replace(span_text, "").strip() if span_text else full
    return main, span_text.strip().strip("()").strip()


def parse(logger) -> None:
    with c.make_client() as client:
        resp = c.fetch(client, URL, logger)
    logger.info("fetched %s (%d bytes)", URL, len(resp.text))

    soup = BeautifulSoup(resp.text, "lxml")
    root = soup.select_one("#category_taxonomy_list")
    if root is None:
        raise RuntimeError("could not locate #category_taxonomy_list")

    nodes: list[dict] = []
    seen: set[str] = set()
    current_group: str | None = None
    current_archive: str | None = None

    def add(node: dict) -> None:
        if node["id"] in seen:
            logger.warning("duplicate id %s skipped", node["id"])
            return
        seen.add(node["id"])
        nodes.append(node)

    for header in root.find_all(["h2", "h3", "h4"]):
        if header.name == "h2":
            name = header.get_text(" ", strip=True)
            gid = _slug(name)
            current_group = gid
            current_archive = None
            add(c.normalize_node(id=gid, name=name, parents=[],
                                 extras={"kind": "group"}))
        elif header.name == "h3":
            name, code = _split_span(header)
            arch_id = code or _slug(name)
            current_archive = arch_id
            add(c.normalize_node(
                id=arch_id, name=name,
                parents=[current_group] if current_group else [],
                extras={"kind": "archive"}))
        else:  # h4 -- leaf category
            code, name = _split_span(header)
            parent = current_archive or current_group
            # definition: the <p> in the sibling column of this row
            definition = None
            row = header.find_parent("div", class_="columns")
            if row is not None:
                p = row.find("p")
                if p is not None:
                    definition = p.get_text(" ", strip=True) or None
            # Single-category archives (e.g. gr-qc) appear as both an h3
            # archive head and an h4 leaf with the same code. Merge: keep the
            # one node, enrich it with the leaf's definition + name.
            if code == current_archive and code in seen:
                existing = next(n for n in nodes if n["id"] == code)
                existing["definition"] = definition
                existing["name"] = name
                existing["extras"]["kind"] = "category"
                continue
            add(c.normalize_node(
                id=code, name=name,
                parents=[parent] if parent else [],
                definition=definition,
                extras={"kind": "category"}))

    if not nodes:
        raise RuntimeError("parsed zero nodes")

    leaves = sum(1 for n in nodes if n["extras"]["kind"] == "category")
    logger.info("groups=%d archives=%d categories=%d",
                sum(1 for n in nodes if n["extras"]["kind"] == "group"),
                sum(1 for n in nodes if n["extras"]["kind"] == "archive"),
                leaves)
    c.write_raw("arxiv", c.now_iso()[:10], nodes, logger)


if __name__ == "__main__":
    raise SystemExit(c.run_parser("arxiv", parse))
