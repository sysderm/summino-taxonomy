#!/usr/bin/env python3
"""Harvest the OECD Frascati Fields of Science and Technology (FOS) classification.

The OECD does not publish FOS as a machine-readable file or API; it is a fixed
published standard (6 major fields, ~42 sub-fields) defined in the Frascati
Manual 2015 (Annex, Revised FOS 2007). We therefore transcribe the canonical
two-level list verbatim rather than scrape a fragile third-party republication.
This is fully reproducible: the list below matches the published standard and
changes only when OECD revises the manual.

Reference: OECD (2015), Frascati Manual 2015, Annex "Revised field of science
and technology (FOS) classification".
"""
from __future__ import annotations

import _common as c

VERSION = "FOS-2007 (Frascati Manual 2015)"

# (code, name) -- 1-level codes are major fields, 2-level codes are sub-fields.
FOS: list[tuple[str, str]] = [
    ("1", "Natural sciences"),
    ("1.1", "Mathematics"),
    ("1.2", "Computer and information sciences"),
    ("1.3", "Physical sciences"),
    ("1.4", "Chemical sciences"),
    ("1.5", "Earth and related environmental sciences"),
    ("1.6", "Biological sciences"),
    ("1.7", "Other natural sciences"),
    ("2", "Engineering and technology"),
    ("2.1", "Civil engineering"),
    ("2.2", "Electrical engineering, electronic engineering, information engineering"),
    ("2.3", "Mechanical engineering"),
    ("2.4", "Chemical engineering"),
    ("2.5", "Materials engineering"),
    ("2.6", "Medical engineering"),
    ("2.7", "Environmental engineering"),
    ("2.8", "Environmental biotechnology"),
    ("2.9", "Industrial biotechnology"),
    ("2.10", "Nano-technology"),
    ("2.11", "Other engineering and technologies"),
    ("3", "Medical and health sciences"),
    ("3.1", "Basic medicine"),
    ("3.2", "Clinical medicine"),
    ("3.3", "Health sciences"),
    ("3.4", "Health biotechnology"),
    ("3.5", "Other medical sciences"),
    ("4", "Agricultural sciences"),
    ("4.1", "Agriculture, forestry, and fisheries"),
    ("4.2", "Animal and dairy science"),
    ("4.3", "Veterinary science"),
    ("4.4", "Agricultural biotechnology"),
    ("4.5", "Other agricultural sciences"),
    ("5", "Social sciences"),
    ("5.1", "Psychology"),
    ("5.2", "Economics and business"),
    ("5.3", "Educational sciences"),
    ("5.4", "Sociology"),
    ("5.5", "Law"),
    ("5.6", "Political science"),
    ("5.7", "Social and economic geography"),
    ("5.8", "Media and communications"),
    ("5.9", "Other social sciences"),
    ("6", "Humanities"),
    ("6.1", "History and archaeology"),
    ("6.2", "Languages and literature"),
    ("6.3", "Philosophy, ethics and religion"),
    ("6.4", "Arts (arts, history of arts, performing arts, music)"),
    ("6.5", "Other humanities"),
]


def parse(logger) -> None:
    nodes: list[dict] = []
    for code, name in FOS:
        level = code.count(".") + 1
        parents = [code.rsplit(".", 1)[0]] if "." in code else []
        nodes.append(c.normalize_node(
            id=code, name=name, parents=parents,
            extras={"level": level}))
    logger.info("transcribed %d FOS nodes (%d major fields)",
                len(nodes), sum(1 for c_, _ in FOS if "." not in c_))
    c.write_raw("oecd-fos", VERSION, nodes, logger)


if __name__ == "__main__":
    raise SystemExit(c.run_parser("oecd-fos", parse))
