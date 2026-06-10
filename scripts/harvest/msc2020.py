#!/usr/bin/env python3
"""Harvest MSC2020 (Mathematics Subject Classification 2020).

Source: https://msc2020.org/MSC_2020.csv -- a tab-separated file with columns
(code, text, description), ~6600 rows.

MSC code shape and the hierarchy we reconstruct:
  NN-XX   two-digit primary class      e.g. 00-XX   -> top level
  NN-NN   exposition subdivision       e.g. 00-01   -> parent NN-XX
  NNLxx   second-level (letter) class  e.g. 00Axx   -> parent NN-XX
  NNLNN   five-character leaf          e.g. 00A05   -> parent NNLxx

The "description" column sometimes adds cross-reference notes (e.g.
"{For ..., see NNX}"); we keep it as the node definition when it differs from
the plain text label.
"""
from __future__ import annotations

import csv
import io
import re

import _common as c

URL = "https://msc2020.org/MSC_2020.csv"

RE_TOP = re.compile(r"^(\d\d)-XX$")
RE_EXPO = re.compile(r"^(\d\d)-\d\d$")
RE_LETTER = re.compile(r"^(\d\d)([A-Z])xx$")
RE_LEAF = re.compile(r"^(\d\d)([A-Z])\d\d$")


def _parent_of(code: str) -> list[str]:
    if RE_TOP.match(code):
        return []
    m = RE_EXPO.match(code)
    if m:
        return [f"{m.group(1)}-XX"]
    m = RE_LETTER.match(code)
    if m:
        return [f"{m.group(1)}-XX"]
    m = RE_LEAF.match(code)
    if m:
        return [f"{m.group(1)}{m.group(2)}xx"]
    return []


def parse(logger) -> None:
    with c.make_client() as client:
        resp = c.fetch(client, URL, logger)
    text = resp.text
    logger.info("fetched %s (%d bytes)", URL, len(text))

    reader = csv.reader(io.StringIO(text), delimiter="\t", quotechar='"')
    header = next(reader)
    if [h.strip().lower() for h in header] != ["code", "text", "description"]:
        raise RuntimeError(f"unexpected header: {header}")

    nodes: list[dict] = []
    seen: set[str] = set()
    levels = {"top": 0, "letter": 0, "expo": 0, "leaf": 0, "other": 0}
    for row in reader:
        if len(row) < 2 or not row[0].strip():
            continue
        code = row[0].strip()
        name = row[1].strip()
        desc = row[2].strip() if len(row) > 2 else ""
        if code in seen:
            continue
        seen.add(code)

        if RE_TOP.match(code):
            kind = "top"
        elif RE_LETTER.match(code):
            kind = "letter"
        elif RE_EXPO.match(code):
            kind = "expo"
        elif RE_LEAF.match(code):
            kind = "leaf"
        else:
            kind = "other"
        levels[kind] += 1

        definition = desc if (desc and desc != name) else None
        nodes.append(c.normalize_node(
            id=code, name=name, parents=_parent_of(code),
            definition=definition, extras={"kind": kind}))

    # Validate: every non-root parent reference resolves.
    ids = {n["id"] for n in nodes}
    orphans = [(n["id"], n["parents"][0]) for n in nodes
               if n["parents"] and n["parents"][0] not in ids]
    if orphans:
        logger.warning("%d nodes with unresolved parent: %s",
                       len(orphans), orphans[:10])

    logger.info("counts %s total=%d", levels, len(nodes))
    if levels["leaf"] < 4000:
        raise RuntimeError(f"only {levels['leaf']} leaves; expected ~5000")
    c.write_raw("msc2020", "MSC2020 (msc2020.org)", nodes, logger)


if __name__ == "__main__":
    raise SystemExit(c.run_parser("msc2020", parse))
