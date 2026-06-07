#!/usr/bin/env python3
"""
Phase 1.1 — merge 11 source taxonomies into a unified DAG.

Three-pass merge, idempotent, $0 cash (mac ollama only):
  1. Deterministic: Wikidata-QID join, normalized-name match, alias intersection.
  2. Embedding: nomic-embed-text via ollama, hnswlib kNN, cosine>=0.95 auto-merge.
  3. LLM judge: qwen2.5:14b on grey-zone pairs (0.85 < cosine < 0.95).

Outputs:
  merged.json
  docs/diagnostics/phase1-merge-summary.md
  docs/diagnostics/phase1-merge-low-confidence.json

Run from repo root. Checkpoints to .merge-state/ between passes.
"""
import json
import os
import re
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np
import requests

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "raw"
STATE = REPO / ".merge-state"
STATE.mkdir(exist_ok=True)
LOG = open(STATE / "merge.log", "a", buffering=1)

OLLAMA = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
JUDGE_MODEL = "qwen2.5:14b-instruct"
COSINE_AUTO = 0.95
COSINE_GREY_LOW = 0.85
JUDGE_PAIR_CAP = 600  # hard cap on LLM judge calls overnight


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, file=LOG)
    print(line)


def norm_name(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s).casefold()
    s = re.sub(r"[\s\-_/]+", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    return s.strip()


# ---------- LOAD ----------

def load_all():
    nodes = []
    by_source = defaultdict(list)
    for path in sorted(RAW.glob("*.json")):
        d = json.loads(path.read_text())
        src = d["source"]
        for n in d.get("nodes", []):
            n = dict(n)
            n["_src"] = src
            n["_uid"] = f"{src}::{n['id']}"
            nodes.append(n)
            by_source[src].append(n["_uid"])
    log(f"loaded {len(nodes)} nodes from {len(by_source)} sources: {dict((k, len(v)) for k, v in by_source.items())}")
    return nodes


# ---------- UNION-FIND ----------

class UF:
    def __init__(self, items):
        self.p = {x: x for x in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb

    def groups(self):
        g = defaultdict(list)
        for x in self.p:
            g[self.find(x)].append(x)
        return g


# ---------- PASS 1: DETERMINISTIC ----------

def extract_wikidata_qid(n):
    src = n["_src"]
    if src == "wikidata":
        return n["id"]  # "Q123"
    wd = (n.get("extras") or {}).get("wikidata")
    if isinstance(wd, list):
        wd = wd[0] if wd else None
    if isinstance(wd, str) and re.match(r"^Q\d+$", wd):
        return wd
    return None


def pass1_deterministic(nodes):
    uf = UF([n["_uid"] for n in nodes])
    by_uid = {n["_uid"]: n for n in nodes}
    # 1a. Wikidata QID join — cross-source only; if a single source has many
    # nodes pointing at the same QID (e.g. CSO topic family all annotated
    # "ultra-wideband") that's a hierarchy artifact, not a dedup signal.
    qid_idx = defaultdict(list)
    for n in nodes:
        qid = extract_wikidata_qid(n)
        if qid:
            qid_idx[qid].append(n["_uid"])
    qid_merges = 0
    for qid, uids in qid_idx.items():
        srcs_to_rep = {}
        for u in uids:
            srcs_to_rep.setdefault(by_uid[u]["_src"], u)
        if len(srcs_to_rep) > 1:
            reps = list(srcs_to_rep.values())
            for u in reps[1:]:
                uf.union(reps[0], u)
                qid_merges += 1
    log(f"pass1 wikidata-qid: {qid_merges} cross-source unions over {len(qid_idx)} unique QIDs")

    # 1b. Exact normalized-name join (cross-source only — intra-source dupes are intentional siblings)
    # Require name length >= 5 chars AND >= 2 words OR >= 8 chars to avoid generic-string runaway
    # (e.g. "cnc", "model", "data" match dozens of unrelated rows)
    name_idx = defaultdict(list)
    for n in nodes:
        key = norm_name(n.get("name") or "")
        if len(key) >= 5 and (" " in key or len(key) >= 8):
            name_idx[key].append((n["_uid"], n["_src"]))
    name_merges = 0
    skipped_overloaded = 0
    for key, items in name_idx.items():
        srcs = {s for _, s in items}
        if len(srcs) > 1:
            # safety: if a normalized name maps to >8 cross-source candidates, treat as ambiguous, skip
            if len(srcs) > 8:
                skipped_overloaded += 1
                continue
            # union one rep per source
            reps = {}
            for u, s in items:
                reps.setdefault(s, u)
            anchors = list(reps.values())
            for u in anchors[1:]:
                uf.union(anchors[0], u)
                name_merges += 1
    log(f"pass1 normalized-name: {name_merges} cross-source unions over {len(name_idx)} unique names, skipped {skipped_overloaded} overloaded")

    # NOTE: alias-name intersection was dropped — it cascades runaway unions when
    # short generic aliases (e.g. "cnc", "model") appear as canonical names of
    # many unrelated concepts. Cross-source synonym detection is delegated to the
    # embedding pass which uses semantic similarity, not string matching.

    groups = uf.groups()
    multi = sum(1 for g in groups.values() if len(g) > 1)
    biggest = max((len(g) for g in groups.values()), default=0)
    log(f"pass1 result: {len(groups)} clusters, {multi} multi-node, biggest cluster has {biggest} members")
    if biggest > 50:
        log(f"  WARNING: biggest cluster suspiciously large, investigating...")
        for g in sorted(groups.values(), key=lambda x: -len(x))[:3]:
            log(f"  cluster size {len(g)}: sample={g[:5]}")
    return uf


# ---------- PASS 2: EMBEDDING ----------

def embed_text(text: str) -> list:
    r = requests.post(f"{OLLAMA}/api/embeddings",
                      json={"model": EMBED_MODEL, "prompt": text[:2000]}, timeout=60)
    r.raise_for_status()
    return r.json()["embedding"]


def pass2_embedding(nodes, uf):
    import hnswlib

    # one representative per cluster — pick the longest-name one for richer embedding
    groups = uf.groups()
    by_uid = {n["_uid"]: n for n in nodes}
    reps = []
    for root, members in groups.items():
        if not members:
            continue
        member_nodes = [by_uid[u] for u in members]
        member_nodes.sort(key=lambda x: -len(x.get("name") or ""))
        reps.append((root, member_nodes[0]))
    log(f"pass2 embedding {len(reps)} cluster representatives")

    ckpt = STATE / "embeddings.npy"
    ckpt_meta = STATE / "embeddings.meta.json"
    if ckpt.exists() and ckpt_meta.exists():
        meta = json.loads(ckpt_meta.read_text())
        if meta.get("count") == len(reps):
            vecs = np.load(ckpt)
            log(f"pass2 resumed from checkpoint {ckpt.name}, {len(vecs)} vectors")
        else:
            vecs = None
    else:
        vecs = None

    if vecs is None:
        vecs = np.zeros((len(reps), 768), dtype=np.float32)
        t0 = time.time()
        for i, (root, n) in enumerate(reps):
            text = (n.get("name") or "").strip()
            d = (n.get("definition") or "").strip()
            if d:
                text = f"{text}: {d[:500]}"
            try:
                vecs[i] = embed_text(text)
            except Exception as e:
                log(f"  embed err idx={i} {n['_uid']}: {e}")
            if (i + 1) % 500 == 0:
                rate = (i + 1) / (time.time() - t0)
                eta = (len(reps) - i - 1) / rate / 60
                log(f"  embedded {i+1}/{len(reps)} @ {rate:.1f}/s ETA {eta:.1f}min")
        np.save(ckpt, vecs)
        ckpt_meta.write_text(json.dumps({"count": len(reps)}))
        log(f"pass2 embedding done in {(time.time()-t0)/60:.1f}min")

    # normalize for cosine via inner product
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    nvecs = vecs / norms

    idx = hnswlib.Index(space="cosine", dim=768)
    idx.init_index(max_elements=len(nvecs), ef_construction=200, M=16)
    idx.add_items(nvecs, np.arange(len(nvecs)))
    idx.set_ef(50)
    log(f"pass2 hnsw index built")

    # kNN search
    labels, distances = idx.knn_query(nvecs, k=8)
    # cosine_sim = 1 - cosine_distance (hnswlib's "cosine" space returns 1-cos)
    sims = 1.0 - distances

    rep_uids = [r for r, _ in reps]
    rep_src = [n["_src"] for _, n in reps]

    auto_merges = []
    grey_pairs = []
    for i in range(len(reps)):
        for j_idx in range(1, 8):  # skip self
            j = int(labels[i, j_idx])
            if j == i:
                continue
            s = float(sims[i, j_idx])
            if rep_src[i] == rep_src[j]:
                continue  # don't merge intra-source clusters
            if s >= COSINE_AUTO:
                auto_merges.append((rep_uids[i], rep_uids[j], s))
            elif s >= COSINE_GREY_LOW:
                grey_pairs.append((i, j, s))

    # apply auto-merges
    auto_n = 0
    for a, b, _ in auto_merges:
        if uf.find(a) != uf.find(b):
            uf.union(a, b)
            auto_n += 1
    log(f"pass2 auto-merged {auto_n} clusters at cosine>={COSINE_AUTO}")
    log(f"pass2 grey-zone pairs collected: {len(grey_pairs)}")

    # dedupe grey pairs by (min,max) and rank by sim desc
    seen = set()
    deduped = []
    for i, j, s in sorted(grey_pairs, key=lambda x: -x[2]):
        key = (min(i, j), max(i, j))
        if key in seen:
            continue
        seen.add(key)
        deduped.append((i, j, s))
    return reps, deduped


# ---------- PASS 3: LLM JUDGE ----------

JUDGE_PROMPT = """You are deciding whether two scientific concepts refer to the SAME thing across taxonomies.

A: "{name_a}"
   definition: {def_a}
   source: {src_a}

B: "{name_b}"
   definition: {def_b}
   source: {src_b}

Verdicts:
  "same"          — synonyms or aliases for the same concept
  "parent_child"  — one is a broader category of the other
  "different"     — distinct concepts that happen to share vocabulary

Respond with ONLY this JSON, nothing else:
{{"verdict": "same|parent_child|different", "confidence": 0.0-1.0, "rationale": "<one short sentence>"}}"""


def judge_pair(reps, i, j):
    _, a = reps[i]
    _, b = reps[j]
    prompt = JUDGE_PROMPT.format(
        name_a=a.get("name") or "",
        def_a=(a.get("definition") or "")[:400] or "(none)",
        src_a=a["_src"],
        name_b=b.get("name") or "",
        def_b=(b.get("definition") or "")[:400] or "(none)",
        src_b=b["_src"],
    )
    r = requests.post(f"{OLLAMA}/api/generate",
                      json={"model": JUDGE_MODEL, "prompt": prompt, "stream": False,
                            "options": {"temperature": 0.0, "num_predict": 200}},
                      timeout=120)
    r.raise_for_status()
    raw = r.json().get("response", "")
    m = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if not m:
        return {"verdict": "error", "confidence": 0.0, "rationale": raw[:200]}
    try:
        return json.loads(m.group(0))
    except Exception as e:
        return {"verdict": "error", "confidence": 0.0, "rationale": f"parse err: {e}"}


def pass3_judge(reps, grey_pairs, uf):
    judgements = []
    cap = min(JUDGE_PAIR_CAP, len(grey_pairs))
    log(f"pass3 judging {cap} grey-zone pairs (cap={JUDGE_PAIR_CAP}, total={len(grey_pairs)})")
    t0 = time.time()
    for k, (i, j, sim) in enumerate(grey_pairs[:cap]):
        try:
            v = judge_pair(reps, i, j)
        except Exception as e:
            v = {"verdict": "error", "confidence": 0.0, "rationale": str(e)[:200]}
        v["sim"] = sim
        v["a"] = reps[i][1].get("name")
        v["a_src"] = reps[i][1]["_src"]
        v["b"] = reps[j][1].get("name")
        v["b_src"] = reps[j][1]["_src"]
        judgements.append(v)
        if v.get("verdict") == "same" and v.get("confidence", 0) >= 0.7:
            uf.union(reps[i][0], reps[j][0])
        if (k + 1) % 25 == 0:
            rate = (k + 1) / (time.time() - t0)
            eta = (cap - k - 1) / rate / 60
            log(f"  judged {k+1}/{cap} @ {rate:.2f}/s ETA {eta:.1f}min")
    log(f"pass3 done in {(time.time()-t0)/60:.1f}min")
    return judgements


# ---------- EMIT ----------

def emit_merged(nodes, uf, reps, judgements, source_counts):
    groups = uf.groups()
    by_uid = {n["_uid"]: n for n in nodes}

    canonical = []
    for root, members in groups.items():
        member_nodes = [by_uid[u] for u in members]
        # canonical_name: prefer the rep we used in embedding (longest), else first
        member_nodes_sorted = sorted(member_nodes, key=lambda x: -len(x.get("name") or ""))
        cn = member_nodes_sorted[0].get("name") or "(unnamed)"
        source_ids = defaultdict(list)
        all_aliases = set()
        all_defs = []
        all_parents_uid = set()
        for n in member_nodes:
            source_ids[n["_src"]].append(n["id"])
            for a in (n.get("aliases") or []):
                if a and norm_name(a) != norm_name(cn):
                    all_aliases.add(a)
            d = n.get("definition")
            if d:
                all_defs.append(d)
            for p in (n.get("parents") or []):
                all_parents_uid.add(f"{n['_src']}::{p}")
        canonical_id = f"cn::{root.replace('::','_')}"
        # parents — resolve via uf
        parent_canonicals = set()
        for puid in all_parents_uid:
            if puid in uf.p:
                parent_canonicals.add(uf.find(puid))
        canonical.append({
            "canonical_id": canonical_id,
            "canonical_name": cn,
            "source_ids": dict(source_ids),
            "parent_roots": sorted(parent_canonicals),  # rewrite to canonical_ids below
            "aliases": sorted(all_aliases)[:50],
            "definition": (all_defs[0] if all_defs else None),
            "member_count": len(member_nodes),
        })

    # rewrite parent_roots → canonical_ids
    root_to_cid = {c["canonical_id"].replace("cn::","").replace("_","::",1): c["canonical_id"] for c in canonical}
    # simpler: map root -> canonical_id
    root_to_cid = {}
    for c in canonical:
        r = c["canonical_id"][4:].replace("_","::",1)
        root_to_cid[r] = c["canonical_id"]
    for c in canonical:
        new_parents = []
        for pr in c["parent_roots"]:
            cid = root_to_cid.get(pr)
            if cid and cid != c["canonical_id"]:
                new_parents.append(cid)
        c["parents"] = sorted(set(new_parents))
        del c["parent_roots"]

    out = REPO / "merged.json"
    out.write_text(json.dumps({
        "version": "phase1.1-v0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_counts": source_counts,
        "canonical_count": len(canonical),
        "raw_node_count": sum(source_counts.values()),
        "nodes": canonical,
    }, indent=2, ensure_ascii=False))
    log(f"wrote {out} with {len(canonical)} canonical nodes")

    # diagnostics
    multi = [c for c in canonical if c["member_count"] > 1]
    by_size = sorted(multi, key=lambda c: -c["member_count"])
    by_breadth = sorted(multi, key=lambda c: -len(c["source_ids"]))

    summary = [
        "# Phase 1.1 merge summary",
        "",
        f"**Raw nodes in:** {sum(source_counts.values())}  ",
        f"**Canonical nodes out:** {len(canonical)}  ",
        f"**Collapse rate:** {(1 - len(canonical)/sum(source_counts.values()))*100:.1f}%  ",
        f"**Multi-source canonical nodes:** {sum(1 for c in canonical if len(c['source_ids']) > 1)}  ",
        "",
        "## Per-source contribution",
        "",
        "| source | raw nodes | canonical nodes touched |",
        "|---|---:|---:|",
    ]
    src_in_canonical = defaultdict(int)
    for c in canonical:
        for s in c["source_ids"]:
            src_in_canonical[s] += 1
    for s, cnt in sorted(source_counts.items(), key=lambda x: -x[1]):
        summary.append(f"| {s} | {cnt} | {src_in_canonical[s]} |")

    summary.extend([
        "",
        "## Top 20 clusters by member count",
        "",
    ])
    for c in by_size[:20]:
        srcs = ",".join(sorted(c["source_ids"]))
        summary.append(f"- **{c['canonical_name']}** ({c['member_count']} members across {srcs})")

    summary.extend([
        "",
        "## Top 20 clusters by cross-source breadth",
        "",
    ])
    for c in by_breadth[:20]:
        srcs = ",".join(sorted(c["source_ids"]))
        summary.append(f"- **{c['canonical_name']}** ({len(c['source_ids'])} sources: {srcs})")

    summary.append("")
    if judgements:
        summary.extend([
            "## LLM judge breakdown",
            "",
            f"- pairs judged: {len(judgements)}",
            f"- verdict same: {sum(1 for j in judgements if j.get('verdict')=='same')}",
            f"- verdict parent_child: {sum(1 for j in judgements if j.get('verdict')=='parent_child')}",
            f"- verdict different: {sum(1 for j in judgements if j.get('verdict')=='different')}",
            f"- verdict error/parse: {sum(1 for j in judgements if j.get('verdict')=='error')}",
        ])

    docs = REPO / "docs" / "diagnostics"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "phase1-merge-summary.md").write_text("\n".join(summary))
    log(f"wrote {docs/'phase1-merge-summary.md'}")

    low_conf = [j for j in judgements if j.get("confidence", 1.0) < 0.7 or j.get("verdict") in ("error", "parent_child")]
    (docs / "phase1-merge-low-confidence.json").write_text(json.dumps(low_conf[:300], indent=2, ensure_ascii=False))
    log(f"wrote {docs/'phase1-merge-low-confidence.json'} with {len(low_conf)} low-confidence judgements")


def main():
    log(f"=== phase 1.1 merge start ===")
    nodes = load_all()
    source_counts = defaultdict(int)
    for n in nodes:
        source_counts[n["_src"]] += 1
    source_counts = dict(source_counts)

    uf = pass1_deterministic(nodes)
    reps, grey = pass2_embedding(nodes, uf)
    judgements = pass3_judge(reps, grey, uf)
    emit_merged(nodes, uf, reps, judgements, source_counts)

    log(f"=== phase 1.1 merge done ===")


if __name__ == "__main__":
    main()
