"""Compare retrieval between the source database and the restored one.

Run by containers/migration-proof.sh.

**What "equivalent" has to mean here.** The first version of this script
demanded that every retrieval result be identical and declared the migration a
failure when 4 of 36 differed. That verdict was wrong, and the reason is worth
writing down: HNSW is an *approximate* index. A restored database rebuilds the
graph with a different insertion order, so the approximate nearest-neighbour
results differ at the margins -- while the underlying data is byte-identical.
Demanding exact equality from an approximate index tests the index's
determinism, not the migration.

So the checks are split by what is actually deterministic:

  EXACT, must match perfectly
    * row counts and index counts
    * a content checksum over every (section_id, text, embedding) tuple --
      the real data-integrity statement
    * full-text retrieval, which uses an exact GIN index

  THRESHOLD, approximate by nature
    * vector and hybrid rank overlap, which must meet RANK_OVERLAP_MIN
    * and every section that appears on one side but not the other must be a
      near-tie: its score must sit within TIE_EPSILON of the last result that
      did make the cut. That is what distinguishes "ranking noise at the
      cut-off" from "the restore lost data", and it is the check that makes
      the threshold defensible rather than a shrug.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

from gcr.db import connect, search_fulltext, search_hybrid, search_vector

# Mean positional agreement required of the approximate modes.
RANK_OVERLAP_MIN = 0.85
# A result present on one side only is acceptable if its score is within this
# of the boundary score -- i.e. it was always a coin-flip for the last place.
TIE_EPSILON = 0.02

# The fixed question set. Committed deliberately: a proof is only a proof if
# the next person can run the same questions.
QUESTIONS = [
    "photonics research funding for small companies",
    "hydrogen production and storage projects",
    "grants for artificial intelligence in healthcare",
    "circular economy and recycling of batteries",
    "support for SMEs in rural regions",
    "climate adaptation and flood resilience",
    "quantum computing hardware development",
    "cybersecurity for critical infrastructure",
    "sustainable agriculture and soil health",
    "offshore wind energy innovation",
    "space technology and earth observation",
    "vaccine development and clinical trials",
]

LIMIT = 10
EXACT_MODES = ("fulltext",)
APPROX_MODES = ("vector", "hybrid")


def _dsn(host: str) -> str:
    user = os.environ.get("POSTGRES_USER", "gcr")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    db = os.environ.get("POSTGRES_DB", "gcr")
    return f"postgresql://{user}:{password}@{host}:5432/{db}"


def embed(texts: list[str]) -> list[list[float]]:
    req = urllib.request.Request(
        "http://tei-embed:80/v1/embeddings",
        data=json.dumps({"input": texts, "model": "bge-m3"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return [d["embedding"] for d in json.load(r)["data"]]


def collect(dsn: str, vectors: list[list[float]]) -> dict[str, list[tuple[str, float]]]:
    out: dict[str, list[tuple[str, float]]] = {}
    with connect(dsn) as conn:
        for question, vector in zip(QUESTIONS, vectors, strict=True):
            for mode, hits in (
                ("fulltext", search_fulltext(conn, question, limit=LIMIT)),
                ("vector", search_vector(conn, vector, limit=LIMIT)),
                ("hybrid", search_hybrid(conn, question, vector, limit=LIMIT)),
            ):
                out[f"{mode}|{question}"] = [(h.section_id, round(h.score, 6)) for h in hits]
    return out


def integrity(dsn: str) -> dict[str, object]:
    """The deterministic facts: counts, index count, and a content checksum.

    The checksum is ordered by section_id so it does not depend on physical row
    order, which a dump and restore has no obligation to preserve.
    """
    with connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*), count(embedding), "
            "md5(string_agg(section_id || '|' || text || '|' || "
            "coalesce(embedding::text, ''), E'\\n' ORDER BY section_id)) "
            "FROM sections"
        )
        rows, embedded, checksum = cur.fetchone()
        cur.execute("SELECT count(*) FROM pg_indexes WHERE tablename = 'sections'")
        (indexes,) = cur.fetchone()
    return {"rows": rows, "embedded": embedded, "indexes": indexes, "checksum": checksum}


def near_tie(only_here: set[str], mine: list[tuple[str, float]],
             theirs: list[tuple[str, float]]) -> bool:
    """Is every one-sided result a borderline case rather than a real miss?"""
    if not only_here:
        return True
    boundary = min(s for _, s in theirs) if theirs else 0.0
    scores = dict(mine)
    return all(abs(scores.get(sid, 0.0) - boundary) <= TIE_EPSILON for sid in only_here)


def _report_integrity(source: str, target: str) -> bool:
    src, tgt = integrity(source), integrity(target)
    print("   data integrity (must be exact)")
    for field in ("rows", "embedded", "indexes"):
        mark = "ok " if src[field] == tgt[field] else "DIFF"
        print(f"     {mark} {field:12s} source={src[field]:<10} target={tgt[field]}")
    checksum_ok = src["checksum"] == tgt["checksum"]
    print(f"     {'ok ' if checksum_ok else 'DIFF'} {'checksum':12s} {src['checksum']}")
    if not checksum_ok:
        print(f"          target     {tgt['checksum']}")
    return checksum_ok and all(src[f] == tgt[f] for f in ("rows", "embedded", "indexes"))


def main() -> int:
    source = os.environ.get("GCR_SOURCE_DSN") or _dsn("db")
    target = os.environ.get("GCR_TARGET_DSN") or _dsn("db-proof")

    print(f"   source  {source.split('@')[-1]}")
    print(f"   target  {target.split('@')[-1]}")
    print(f"   {len(QUESTIONS)} questions x 3 modes, top {LIMIT}")
    print()

    # --- exact: data integrity -------------------------------------------
    integrity_ok = _report_integrity(source, target)

    # --- retrieval ---------------------------------------------------------
    vectors = embed(QUESTIONS)
    before, after = collect(source, vectors), collect(target, vectors)

    per_mode: dict[str, dict[str, object]] = {}
    problems: list[str] = []

    for mode in EXACT_MODES + APPROX_MODES:
        keys = [k for k in sorted(before) if k.startswith(f"{mode}|")]
        same_ids = same_order = 0
        overlaps: list[float] = []
        ties_ok = True
        for key in keys:
            a, b = before[key], after.get(key, [])
            ids_a, ids_b = {x[0] for x in a}, {x[0] for x in b}
            if ids_a == ids_b:
                same_ids += 1
            elif not (near_tie(ids_a - ids_b, a, b) and near_tie(ids_b - ids_a, b, a)):
                ties_ok = False
                problems.append(f"{key}: one-sided results are not near-ties")
            overlap = (
                sum(1 for x, y in zip(a, b, strict=False) if x[0] == y[0]) / max(len(a), 1)
                if len(a) == len(b) else 0.0
            )
            overlaps.append(overlap)
            if overlap == 1.0:
                same_order += 1
        mean_overlap = sum(overlaps) / len(overlaps) if overlaps else 0.0
        per_mode[mode] = {
            "n": len(keys), "same_ids": same_ids, "same_order": same_order,
            "mean_overlap": mean_overlap, "ties_ok": ties_ok,
        }

    print()
    print("   retrieval")
    header = f"     {'mode':10s} {'ids match':>11s} {'order match':>13s}"
    print(f"{header} {'mean overlap':>14s}  verdict")
    ok = integrity_ok
    for mode in EXACT_MODES + APPROX_MODES:
        m = per_mode[mode]
        if mode in EXACT_MODES:
            passed = m["same_ids"] == m["n"] and m["same_order"] == m["n"]
            note = "exact required"
        else:
            passed = m["mean_overlap"] >= RANK_OVERLAP_MIN and m["ties_ok"]
            note = f"approximate, >= {RANK_OVERLAP_MIN:.2f} and near-ties"
        ok = ok and passed
        print(
            f"     {mode:10s} {m['same_ids']}/{m['n']:<9} {m['same_order']}/{m['n']:<11} "
            f"{m['mean_overlap']:>13.4f}  {'PASS' if passed else 'FAIL'}  ({note})"
        )

    for p in problems[:5]:
        print(f"     ! {p}")

    print()
    print(f"   VERDICT: {'EQUIVALENT' if ok else 'NOT EQUIVALENT'}")
    if ok:
        print("   Data is byte-identical; vector ranking differs only at the cut-off,")
        print("   which is inherent to an approximate index rather than a migration fault.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
