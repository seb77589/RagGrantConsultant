"""Reranking: does the cross-encoder's verdict actually reach the caller.

The failure to guard against is subtle. `db.search_hybrid` returns hits whose
`score` is a reciprocal-rank-fusion artefact, and the reranker returns
`(index, score)` pairs against the list it was given. Mapping those back wrongly
produces results that look plausible -- right number of hits, descending scores --
while the text no longer matches the score beside it.

`services.rerank` is monkeypatched, so no network and no GPU.
"""

from __future__ import annotations

from gcr import retrieve as retrieve_mod
from gcr.db import Hit


def _hit(section_id: str, text: str, score: float = 0.0) -> Hit:
    return Hit(
        section_id=section_id,
        source_system="cordis",
        source_id=section_id.split(":")[1],
        source_url=f"https://cordis.europa.eu/project/id/{section_id.split(':')[1]}",
        source_date=None,
        fetch_date=None,
        country="IE",
        programme="HORIZON",
        programme_period="2021-2027",
        origin="english_origin",
        licence="CC-BY-4.0",
        attribution="© European Union, CORDIS",
        text=text,
        score=score,
    )


HITS = [
    _hit("cordis:1:0", "hydrogen storage", score=0.9),
    _hit("cordis:2:0", "photonics research", score=0.8),
    _hit("cordis:3:0", "soil health", score=0.7),
]


def test_rerank_reorders_and_scores_follow_the_text(monkeypatch) -> None:
    """The reranker prefers the third hit; it must come first, with its score."""

    def fake_rerank(query, texts):
        assert list(texts) == [h.text for h in HITS]
        return [(2, 0.95), (0, 0.40), (1, 0.10)]

    monkeypatch.setattr(retrieve_mod.services, "rerank", fake_rerank)
    out = retrieve_mod.rerank_hits("soil", HITS, top_k=3)

    assert [h.section_id for h in out] == ["cordis:3:0", "cordis:1:0", "cordis:2:0"]
    assert [h.score for h in out] == [0.95, 0.40, 0.10]
    # The score must belong to the text beside it, not to the old RRF ordering.
    assert out[0].text == "soil health"


def test_rerank_truncates_to_top_k(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieve_mod.services, "rerank", lambda q, t: [(0, 0.9), (1, 0.8), (2, 0.7)]
    )
    assert len(retrieve_mod.rerank_hits("q", HITS, top_k=2)) == 2


def test_rerank_sorts_even_if_the_service_does_not(monkeypatch) -> None:
    """TEI returns sorted results, but the guarantee should be ours."""
    monkeypatch.setattr(
        retrieve_mod.services, "rerank", lambda q, t: [(0, 0.1), (2, 0.9), (1, 0.5)]
    )
    out = retrieve_mod.rerank_hits("q", HITS, top_k=3)
    assert [h.score for h in out] == [0.9, 0.5, 0.1]


def test_rerank_replaces_the_rrf_score(monkeypatch) -> None:
    """Leaving an RRF score in the same field invites comparing unlike numbers."""
    monkeypatch.setattr(retrieve_mod.services, "rerank", lambda q, t: [(0, 0.42)])
    out = retrieve_mod.rerank_hits("q", HITS, top_k=1)
    assert out[0].score == 0.42
    assert out[0].score != HITS[0].score


def test_no_hits_means_no_service_call(monkeypatch) -> None:
    """An empty candidate set must not cost an HTTP round trip."""

    def explode(query, texts):  # pragma: no cover - must not run
        raise AssertionError("rerank called with no candidates")

    monkeypatch.setattr(retrieve_mod.services, "rerank", explode)
    assert retrieve_mod.rerank_hits("q", [], top_k=5) == []
