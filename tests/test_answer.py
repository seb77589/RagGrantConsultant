"""Answer composition: the rules that must hold whatever the model says.

The model is monkeypatched throughout. That is the point — these tests check the
parts that do not depend on the model behaving: that an unsupported figure is
caught even when the model states it confidently, that every citation carries
attribution, that a stale source is flagged, and that a machine-translated source
is labelled.
"""

from __future__ import annotations

from datetime import date

from gcr import answer as answer_mod
from gcr.db import Hit

TODAY = date(2026, 10, 1)


def _hit(
    source_id: str = "101101415",
    text: str = "The call has a budget of EUR 12,000,000 and a 70% funding rate.",
    source_date: date | None = date(2026, 9, 1),
    origin: str = "english_origin",
) -> Hit:
    return Hit(
        section_id=f"cordis:{source_id}:0",
        source_system="cordis",
        source_id=source_id,
        source_url=f"https://cordis.europa.eu/project/id/{source_id}",
        source_date=source_date,
        fetch_date=None,
        country="IE",
        programme="HORIZON",
        programme_period="2021-2027",
        origin=origin,
        licence="CC-BY-4.0",
        attribution="© European Union, CORDIS",
        text=text,
        score=0.9,
    )


def _say(monkeypatch, reply: str) -> None:
    monkeypatch.setattr(answer_mod.services, "chat", lambda *a, **k: reply)


# --- the prompt ------------------------------------------------------------


def test_context_is_numbered_from_one_and_matches_citation_numbers() -> None:
    context = answer_mod.build_context([_hit("1"), _hit("2")])
    assert context.startswith("[1] 1 (as of")
    assert "[2] 2 (as of" in context


def test_prompt_forbids_outside_knowledge_and_names_the_refusal() -> None:
    messages = answer_mod.build_messages("q", [_hit()])
    system = messages[0]["content"]
    assert "ONLY the numbered context" in system
    assert "The retrieved sources do not state this" in system
    assert "Never calculate, convert, round or estimate" in system


def test_missing_upstream_date_is_stated_not_substituted() -> None:
    context = answer_mod.build_context([_hit(source_date=None)])
    assert "no upstream date" in context


# --- the figure guard ------------------------------------------------------


def test_unsupported_figure_is_flagged_and_marked(monkeypatch) -> None:
    """The model states a rate the source does not. Confidence is irrelevant."""
    _say(monkeypatch, "The funding rate is definitely 85%.")
    result = answer_mod.compose("rate?", [_hit()], today=TODAY)
    assert "85% [⚠ unsupported]" in result.text
    assert any(f.startswith("unsupported_figure:percentage:85%") for f in result.flags)


def test_correctly_quoted_figures_produce_no_flags(monkeypatch) -> None:
    _say(monkeypatch, "The budget is EUR 12,000,000 at a 70% rate.")
    result = answer_mod.compose("budget?", [_hit()], today=TODAY)
    assert result.flags == []
    assert "[⚠" not in result.text


def test_a_differently_written_figure_is_not_flagged(monkeypatch) -> None:
    """EUR 12 million against a source saying EUR 12,000,000 is a quotation."""
    _say(monkeypatch, "The budget is EUR 12 million at 70 per cent.")
    result = answer_mod.compose("budget?", [_hit()], today=TODAY)
    assert result.flags == []


# --- citations -------------------------------------------------------------


def test_every_citation_carries_attribution_and_licence(monkeypatch) -> None:
    """CLAUDE.md requires this on every cited source, not once per page."""
    _say(monkeypatch, "Yes.")
    result = answer_mod.compose("q", [_hit("1"), _hit("2")], today=TODAY)
    assert len(result.sources) == 2
    for citation in result.sources:
        assert citation.attribution == "© European Union, CORDIS"
        assert citation.licence == "CC-BY-4.0"
        assert citation.source_url.startswith("https://cordis.europa.eu/")
        assert "© European Union" in citation.render()


def test_citation_carries_a_supporting_quote(monkeypatch) -> None:
    """The hallucination rule says to show the quote, so it must be carried."""
    _say(monkeypatch, "Yes.")
    result = answer_mod.compose("q", [_hit()], today=TODAY)
    assert "EUR 12,000,000" in result.sources[0].quote


def test_rendered_answer_always_carries_the_disclaimer(monkeypatch) -> None:
    _say(monkeypatch, "Yes.")
    rendered = answer_mod.compose("q", [_hit()], today=TODAY).render()
    assert "independent tool" in rendered
    assert "not operated, endorsed or checked by the European Commission" in rendered


# --- staleness -------------------------------------------------------------


def test_source_older_than_the_threshold_is_flagged(monkeypatch) -> None:
    _say(monkeypatch, "Yes.")
    old = _hit(source_date=date(2023, 1, 1))
    result = answer_mod.compose("q", [old], today=TODAY)
    assert any(f.startswith("stale_source:") for f in result.flags)
    assert result.sources[0].stale is True


def test_recent_source_is_not_flagged(monkeypatch) -> None:
    _say(monkeypatch, "Yes.")
    result = answer_mod.compose("q", [_hit(source_date=date(2026, 9, 1))], today=TODAY)
    assert not any(f.startswith("stale_source:") for f in result.flags)


def test_unknown_date_is_not_claimed_to_be_stale(monkeypatch) -> None:
    """Unknown is not old. Claiming staleness we cannot show is the same class of
    error as claiming freshness we cannot show."""
    _say(monkeypatch, "Yes.")
    result = answer_mod.compose("q", [_hit(source_date=None)], today=TODAY)
    assert not any(f.startswith("stale_source:") for f in result.flags)
    assert result.sources[0].as_of == "no upstream date"


# --- the translated tier ---------------------------------------------------


def test_machine_translated_source_is_labelled(monkeypatch) -> None:
    """The Kohesio rule: the translated tier is labelled in answers."""
    _say(monkeypatch, "Yes.")
    result = answer_mod.compose("q", [_hit(origin="machine_translated")], today=TODAY)
    assert any(f.startswith("translated_tier:") for f in result.flags)
    assert result.sources[0].translated is True
    assert "machine translation" in result.render()


def test_english_origin_source_is_not_labelled(monkeypatch) -> None:
    _say(monkeypatch, "Yes.")
    result = answer_mod.compose("q", [_hit()], today=TODAY)
    assert not any(f.startswith("translated_tier:") for f in result.flags)
    assert "machine translation" not in result.render()


# --- no results ------------------------------------------------------------


def test_no_hits_refuses_without_calling_the_model(monkeypatch) -> None:
    def explode(*a, **k):  # pragma: no cover - must not run
        raise AssertionError("generation attempted with no context")

    monkeypatch.setattr(answer_mod.services, "chat", explode)
    result = answer_mod.compose("q", [], today=TODAY)
    assert result.flags == ["no_results"]
    assert "do not state this" in result.text
    assert result.sources == []


def test_as_dict_is_json_ready(monkeypatch) -> None:
    import json

    _say(monkeypatch, "The rate is 70%.")
    payload = answer_mod.as_dict(answer_mod.compose("q", [_hit()], today=TODAY))
    json.dumps(payload)  # must not raise
    assert payload["sources"][0]["attribution"] == "© European Union, CORDIS"
    assert "disclaimer" in payload
