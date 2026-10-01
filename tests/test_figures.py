"""Figure extraction and the no-hallucinated-figures guard.

The guard is only useful if it is quiet when the model quotes correctly and loud
when it does not. A guard that flags "EUR 12 million" against a source saying
"EUR 12,000,000" would be switched off within a day, so most of these tests are
about notation rather than about catching invention.

No network, no database: this is the part of the answer path that can be tested
exactly.
"""

from __future__ import annotations

from gcr.figures import (
    DATE,
    MONEY,
    PERCENTAGE,
    annotate,
    extract_figures,
    unsupported,
)


def _normalised(text: str, kind: str) -> list[str]:
    return [f.normalised for f in extract_figures(text) if f.kind == kind]


# --- amounts ---------------------------------------------------------------


def test_money_with_currency_before_and_after() -> None:
    assert _normalised("EUR 12000000", MONEY) == ["12000000"]
    assert _normalised("12000000 EUR", MONEY) == ["12000000"]
    assert _normalised("€12000000", MONEY) == ["12000000"]


def test_thousands_separators_all_compare_equal() -> None:
    """Comma, dot and space grouping are all used in EU material."""
    for written in ("EUR 12,000,000", "EUR 12.000.000", "EUR 12 000 000"):
        assert _normalised(written, MONEY) == ["12000000"], written


def test_non_breaking_space_grouping() -> None:
    """Pasted EU documents are full of these, and they must not split a number."""
    assert _normalised("EUR 12\u00a0000\u00a0000", MONEY) == ["12000000"]


def test_scale_words_expand() -> None:
    assert _normalised("EUR 12 million", MONEY) == ["12000000"]
    assert _normalised("€1.5 million", MONEY) == ["1500000"]
    assert _normalised("EUR 300 thousand", MONEY) == ["300000"]


def test_decimal_conventions_both_ways() -> None:
    """1.234,56 is European; 1,234.56 is Anglo. Both appear."""
    assert _normalised("EUR 1.234,56", MONEY) == ["1234.56"]
    assert _normalised("EUR 1,234.56", MONEY) == ["1234.56"]


# --- rates -----------------------------------------------------------------


def test_percentage_notations() -> None:
    for written in ("70%", "70 %", "70 per cent", "70 percent"):
        assert _normalised(written, PERCENTAGE) == ["70"], written


def test_fractional_percentage() -> None:
    assert _normalised("67.5%", PERCENTAGE) == ["67.5"]


# --- dates -----------------------------------------------------------------


def test_date_notations_normalise_to_iso() -> None:
    for written in ("14 November 2024", "2024-11-14", "November 14, 2024", "14 Nov 2024"):
        assert DATE in {f.kind for f in extract_figures(written)}, written
        assert "2024-11-14" in _normalised(written, DATE), written


def test_a_full_date_does_not_also_yield_a_stray_year() -> None:
    """Otherwise every deadline would produce a spurious second figure."""
    assert _normalised("14 November 2024", DATE) == ["2024-11-14"]


def test_bare_year_is_a_date() -> None:
    assert _normalised("the 2021-2027 programme", DATE) == ["2021", "2027"]


# --- the guard -------------------------------------------------------------


CONTEXT = (
    "Call HORIZON-CL4-2024-DIGITAL-01 has a budget of EUR 12,000,000 and a "
    "deadline of 14 November 2024. The funding rate is 70% for innovation actions."
)


def test_correctly_quoted_figures_are_not_flagged() -> None:
    answer = "The budget is EUR 12,000,000, the rate 70%, and the deadline 14 November 2024."
    assert unsupported(answer, CONTEXT) == []


def test_different_notation_is_still_supported() -> None:
    """The point of normalising: this is a correct quotation, not an invention."""
    answer = "The budget is EUR 12 million at a 70 per cent rate, closing 2024-11-14."
    assert unsupported(answer, CONTEXT) == []


def test_an_invented_amount_is_flagged() -> None:
    flagged = unsupported("The budget is EUR 15,000,000.", CONTEXT)
    assert [f.normalised for f in flagged] == ["15000000"]
    assert flagged[0].kind == MONEY


def test_an_invented_rate_is_flagged() -> None:
    flagged = unsupported("The funding rate is 85%.", CONTEXT)
    assert [f.normalised for f in flagged] == ["85"]


def test_an_invented_deadline_is_flagged() -> None:
    flagged = unsupported("Applications close on 3 March 2025.", CONTEXT)
    assert [f.normalised for f in flagged] == ["2025-03-03"]


def test_a_year_implied_by_a_full_date_in_context_is_supported() -> None:
    """"in 2024" is a fair reading of a source saying 14 November 2024."""
    assert unsupported("The call closes in 2024.", CONTEXT) == []


def test_repeated_unsupported_figure_is_reported_once() -> None:
    """One defect to fix, not four."""
    answer = "85% applies. At 85% the rate is high. 85%. Really, 85%."
    assert len(unsupported(answer, CONTEXT)) == 1


def test_empty_context_flags_everything() -> None:
    """The failure mode must be closed: no retrieved text vouches for nothing."""
    flagged = unsupported("The rate is 70% and the budget EUR 12,000,000.", "")
    assert {f.kind for f in flagged} == {MONEY, PERCENTAGE}


def test_an_answer_with_no_figures_is_clean() -> None:
    assert unsupported("The context does not state a funding rate.", CONTEXT) == []


# --- annotation ------------------------------------------------------------


def test_annotate_marks_only_the_unsupported_figure() -> None:
    answer = "The budget is EUR 12,000,000 but the rate is 85%."
    marked = annotate(answer, unsupported(answer, CONTEXT))
    assert "85% [⚠ unsupported]" in marked
    assert "EUR 12,000,000 [⚠" not in marked


def test_annotate_marks_a_repeated_figure_once() -> None:
    answer = "85% and again 85%."
    marked = annotate(answer, unsupported(answer, CONTEXT))
    assert marked.count("[⚠ unsupported]") == 1


def test_annotate_leaves_a_clean_answer_untouched() -> None:
    answer = "The rate is 70%."
    assert annotate(answer, unsupported(answer, CONTEXT)) == answer
