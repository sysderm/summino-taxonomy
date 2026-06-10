#!/usr/bin/env python3
"""Harvest the WHO ICD classification.

Choice (2026-06): the ICD-11 API requires registering an OAuth client account
(https://icd.who.int/icdapi/Account/Register is a sign-up form with email
verification) before any token can be issued. Creating an identity-bound
account is a heavy, outward-facing step, so per the Phase 1.0 hard rules we
FALL BACK to ICD-10.

ICD-10 (2019) is harvested from the public, auth-free JSON API that backs the
official browser at https://icd.who.int/browse10/2019/en :
  JsonGetRootConcepts                 -> chapter roots
  JsonGetChildrenConcepts?ConceptId=X -> children of concept X
We crawl the tree breadth-first. Each node carries ID (the code, e.g. "C00-C97"
or "C50"), a label, and isLeaf. Parent edges come from the traversal; adopted
(cross-referenced) children are kept as additional parents -> a DAG.
"""
from __future__ import annotations

import time
from collections import deque

import _common as c

BASE = "https://icd.who.int/browse10/2019/en"
ROOTS = f"{BASE}/JsonGetRootConcepts?useHtml=false"
CHILDREN = (BASE + "/JsonGetChildrenConcepts?ConceptId={cid}"
            "&useHtml=false&showAdoptedChildren=true")
VERSION = "ICD-10 2019 (icd.who.int/browse10)"
SLEEP = 0.12
MAX_REQUESTS = 30000


def _name(label: str, cid: str) -> str:
    """Labels embed the code, e.g. 'C00-C97 Malignant neoplasms'. Strip it."""
    label = label.strip()
    if label.startswith(cid):
        rest = label[len(cid):].lstrip(" -–")
        return rest or label
    return label


def parse(logger) -> None:
    nodes: dict[str, dict] = {}
    parents: dict[str, set[str]] = {}
    requests = 0

    with c.make_client(timeout=60) as client:
        roots = c.fetch(client, ROOTS, logger,
                        headers={"X-Requested-With": "XMLHttpRequest"}).json()
        requests += 1
        queue: deque[str] = deque()

        def record(item: dict, parent: str | None) -> bool:
            cid = item["ID"]
            new = cid not in nodes
            if new:
                nodes[cid] = c.normalize_node(
                    id=cid, name=_name(item.get("label", cid), cid),
                    parents=[], extras={"is_leaf": bool(item.get("isLeaf"))})
            if parent:
                parents.setdefault(cid, set()).add(parent)
            return new

        for r in roots:
            if record(r, None) and not r.get("isLeaf"):
                queue.append(r["ID"])

        while queue:
            if requests >= MAX_REQUESTS:
                raise RuntimeError(f"hit MAX_REQUESTS={MAX_REQUESTS}; aborting")
            cid = queue.popleft()
            time.sleep(SLEEP)
            children = c.fetch(
                client, CHILDREN.format(cid=cid), logger,
                headers={"X-Requested-With": "XMLHttpRequest"}).json()
            requests += 1
            for ch in children:
                first_time = record(ch, cid)
                # Only descend the first time we see a non-leaf node, so each
                # subtree is fetched once even though it may have many parents.
                if first_time and not ch.get("isLeaf"):
                    queue.append(ch["ID"])
            if requests % 250 == 0:
                logger.info("  crawled %d concepts in %d requests",
                            len(nodes), requests)

    for cid, ps in parents.items():
        nodes[cid]["parents"] = sorted(ps)

    out = list(nodes.values())
    leaves = sum(1 for n in out if n["extras"]["is_leaf"])
    roots_n = sum(1 for n in out if not n["parents"])
    logger.info("concepts=%d leaves=%d roots=%d requests=%d",
                len(out), leaves, roots_n, requests)
    if len(out) < 8000:
        raise RuntimeError(f"only {len(out)} concepts; expected ~12k")
    c.write_raw("icd", VERSION, out, logger)


if __name__ == "__main__":
    raise SystemExit(c.run_parser("icd", parse))
