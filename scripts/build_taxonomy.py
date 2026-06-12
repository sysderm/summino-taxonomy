#!/usr/bin/env python3
"""
Build `built-taxonomy.json` + `HIERARCHY.md` from the per-level flat files.

Reads
-----
  level1-review/level1-converged.json              -> L1 (20)
  level2-review/by-category/<l1>/opus-4-8.json     -> L2 (parent_l1 = dir)
  level3/<l1>.json                                  -> L3 (parent_l2 = field)
  level4/<l1>.json                                  -> L4 (parent_l3 = field)
  level5/<l1>.json                                  -> L5 (parent_l4 = field)

Writes
------
  built-taxonomy.json
  HIERARCHY.md

App-shape per node:
  L1: {id, name, tagline, icon, color, bgColor, children}
  L2: {id, name, icon, children}
  L3: {id, name, children?}
  L4: {id, name, children?}
  L5: {id, name}

Usage:
  python3 scripts/build_taxonomy.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent

L1_FILE = REPO / "level1-review" / "level1-converged.json"
L2_BY_CATEGORY = REPO / "level2-review" / "by-category"
L3_DIR = REPO / "level3"
L4_DIR = REPO / "level4"
L5_DIR = REPO / "level5"

OUT_JSON = REPO / "built-taxonomy.json"
OUT_MD = REPO / "HIERARCHY.md"

# Visual defaults — the existing hand-built taxonomy used identical icon/color
# for every L1 and the book emoji for every L2. Preserve that until the picker
# UI assigns per-card art.
L1_ICON = "\U0001f52c"       # microscope
L1_COLOR = "#3b82f6"
L1_BGCOLOR = "#eff6ff"
L2_ICON = "\U0001f4da"       # books


def load_json(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return json.load(f)


def load_l1() -> list[dict[str, Any]]:
    data = load_json(L1_FILE)
    return data["categories"]


def load_l2(l1_slug: str) -> list[dict[str, Any]]:
    """Prefer opus-4-8.json; the v1-archived variants are ignored."""
    path = L2_BY_CATEGORY / l1_slug / "opus-4-8.json"
    if not path.exists():
        # Fallback to gpt-5-mini.json or gemini-2.5-pro.json (uncommon).
        for fb in ("gpt-5-mini.json", "gemini-2.5-pro.json"):
            cand = L2_BY_CATEGORY / l1_slug / fb
            if cand.exists():
                path = cand
                break
        else:
            return []
    data = load_json(path)
    # Some files use "subspecialties", some might use "subfields".
    return data.get("subspecialties") or data.get("subfields") or []


def load_l3(l1_slug: str) -> list[dict[str, Any]]:
    path = L3_DIR / f"{l1_slug}.json"
    if not path.exists():
        return []
    data = load_json(path)
    return data.get("subfields") or data.get("subspecialties") or []


def load_l4(l1_slug: str) -> list[dict[str, Any]]:
    path = L4_DIR / f"{l1_slug}.json"
    if not path.exists():
        return []
    data = load_json(path)
    return data.get("leaves") or data.get("subfields") or []


def load_l5(l1_slug: str) -> list[dict[str, Any]]:
    path = L5_DIR / f"{l1_slug}.json"
    if not path.exists():
        return []
    data = load_json(path)
    return data.get("leaves") or data.get("subfields") or []


def build_tree() -> tuple[list[dict[str, Any]], dict[str, int]]:
    counts = {"L1": 0, "L2": 0, "L3": 0, "L4": 0, "L5": 0}
    tree: list[dict[str, Any]] = []

    for l1 in load_l1():
        l1_slug = l1["slug"]
        l1_node: dict[str, Any] = {
            "id": l1_slug,
            "name": l1["name"],
            "tagline": l1.get("tagline", ""),
            "icon": L1_ICON,
            "color": L1_COLOR,
            "bgColor": L1_BGCOLOR,
            "children": [],
        }
        counts["L1"] += 1

        # --- L2 ---
        l2_entries = load_l2(l1_slug)
        l2_nodes_by_slug: dict[str, dict[str, Any]] = {}
        for l2 in l2_entries:
            l2_slug = l2["slug"]
            l2_node: dict[str, Any] = {
                "id": l2_slug,
                "name": l2["name"],
                "icon": L2_ICON,
                "children": [],
            }
            l1_node["children"].append(l2_node)
            l2_nodes_by_slug[l2_slug] = l2_node
            counts["L2"] += 1

        # --- L3 ---
        l3_nodes_by_slug: dict[str, dict[str, Any]] = {}
        for l3 in load_l3(l1_slug):
            l3_slug = l3["slug"]
            parent = l3.get("parent_l2")
            parent_node = l2_nodes_by_slug.get(parent)
            if parent_node is None:
                print(
                    f"  [warn] L3 {l1_slug}/{l3_slug} parent_l2={parent!r} not found",
                    file=sys.stderr,
                )
                continue
            l3_node: dict[str, Any] = {
                "id": l3_slug,
                "name": l3["name"],
                "children": [],
            }
            parent_node["children"].append(l3_node)
            l3_nodes_by_slug[l3_slug] = l3_node
            counts["L3"] += 1

        # --- L4 ---
        l4_nodes_by_slug: dict[str, dict[str, Any]] = {}
        for l4 in load_l4(l1_slug):
            l4_slug = l4["slug"]
            parent = l4.get("parent_l3")
            parent_node = l3_nodes_by_slug.get(parent)
            if parent_node is None:
                print(
                    f"  [warn] L4 {l1_slug}/{l4_slug} parent_l3={parent!r} not found",
                    file=sys.stderr,
                )
                continue
            l4_node: dict[str, Any] = {
                "id": l4_slug,
                "name": l4["name"],
                "children": [],
            }
            parent_node["children"].append(l4_node)
            l4_nodes_by_slug[l4_slug] = l4_node
            counts["L4"] += 1

        # --- L5 ---
        for l5 in load_l5(l1_slug):
            l5_slug = l5["slug"]
            parent = l5.get("parent_l4")
            parent_node = l4_nodes_by_slug.get(parent)
            if parent_node is None:
                print(
                    f"  [warn] L5 {l1_slug}/{l5_slug} parent_l4={parent!r} not found",
                    file=sys.stderr,
                )
                continue
            l5_node: dict[str, Any] = {
                "id": l5_slug,
                "name": l5["name"],
            }
            parent_node["children"].append(l5_node)
            counts["L5"] += 1

        # Strip empty children arrays at L3/L4 to match the hand-built shape:
        # nodes without descendants drop the `children` key entirely.
        def prune(node: dict[str, Any]) -> None:
            kids = node.get("children")
            if kids is None:
                return
            for c in kids:
                prune(c)
            if not kids:
                node.pop("children", None)

        for l2_node in l1_node["children"]:
            prune(l2_node)

        tree.append(l1_node)

    return tree, counts


def emit_json(tree: list[dict[str, Any]], counts: dict[str, int]) -> None:
    payload = {
        "schema_version": 2,
        "_note": (
            "Generated by scripts/build_taxonomy.py from "
            "summino-taxonomy/level{1..5} flat files. Five levels. "
            "L1=L1, L2=Discipline, L3=Specialty, L4=Subspecialty, "
            "L5=Leaf (drugs/devices/specific models/named entities)."
        ),
        "_source": "https://github.com/sysderm/summino-taxonomy/tree/feat/user-facing-taxonomy",
        "_levels": counts,
        "tree": tree,
    }
    with OUT_JSON.open("w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"wrote {OUT_JSON}")


def emit_md(tree: list[dict[str, Any]], counts: dict[str, int]) -> None:
    total = sum(counts.values())
    lines: list[str] = []
    lines.append("# Summino User-Facing Taxonomy — Full Hierarchy")
    lines.append("")
    lines.append(
        f"**Levels:** L1 = {counts['L1']}, L2 = {counts['L2']}, "
        f"L3 = {counts['L3']}, L4 = {counts['L4']}, L5 = {counts['L5']}"
    )
    lines.append(f"**Total nodes:** {total}")
    lines.append("")

    for l1 in tree:
        lines.append("---")
        lines.append("")
        lines.append(f"## L1: **{l1['name']}** (`{l1['id']}`)")
        if l1.get("tagline"):
            lines.append(f"_{l1['tagline']}_")
        lines.append("")
        for l2 in l1.get("children", []):
            lines.append(f"### L2: {l2['name']}  · `{l2['id']}`")
            for l3 in l2.get("children", []):
                lines.append(f"- **L3:** {l3['name']}  · `{l3['id']}`")
                for l4 in l3.get("children", []):
                    lines.append(f"    - L4: {l4['name']}  · `{l4['id']}`")
                    for l5 in l4.get("children", []):
                        lines.append(f"        - L5: {l5['name']}  · `{l5['id']}`")
            lines.append("")

    with OUT_MD.open("w") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    print(f"wrote {OUT_MD}")


def main() -> int:
    tree, counts = build_tree()
    print(
        "counts: L1={L1}  L2={L2}  L3={L3}  L4={L4}  L5={L5}  total={t}".format(
            t=sum(counts.values()), **counts
        )
    )
    emit_json(tree, counts)
    emit_md(tree, counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
