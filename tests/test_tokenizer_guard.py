"""The corpus-building path must refuse the character heuristic.

Background: the containerised pipeline initially lacked the bge-m3 tokenizer and
silently fell back to counting ~4 characters per token. That over-estimates by
about 17%, so it forced splits the real tokenizer would not, and produced a
different corpus from the host while reporting success. The guard turns that
into a loud failure; these tests keep it loud.
"""

from __future__ import annotations

import pytest

from gcr import chunking


class _FakeTokenizer:
    """Stands in for the real XLM-RoBERTa tokenizer; only its presence matters."""


def _present() -> _FakeTokenizer:
    return _FakeTokenizer()


def _absent() -> None:
    return None


def test_tokenizer_name_reports_the_heuristic_when_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(chunking, "_hf_tokenizer", _absent)
    assert chunking.tokenizer_name() == "character-heuristic"


def test_tokenizer_name_reports_bge_m3_when_available(monkeypatch) -> None:
    monkeypatch.setattr(chunking, "_hf_tokenizer", _present)
    assert chunking.tokenizer_name() == "bge-m3"


def test_require_real_tokenizer_raises_without_one(monkeypatch) -> None:
    monkeypatch.setattr(chunking, "_hf_tokenizer", _absent)
    with pytest.raises(RuntimeError) as excinfo:
        chunking.require_real_tokenizer()
    message = str(excinfo.value)
    # The error has to say what to do about it, not merely that it happened.
    assert "17%" in message
    assert "--extra tokenize" in message
    assert "--allow-token-heuristic" in message


def test_require_real_tokenizer_passes_with_one(monkeypatch) -> None:
    monkeypatch.setattr(chunking, "_hf_tokenizer", _present)
    chunking.require_real_tokenizer()  # must not raise


def test_count_tokens_still_degrades_for_tests(monkeypatch) -> None:
    """The fallback itself stays: the test suite and lint path must run without
    the GPU stack. It is only the recorded-output path that refuses it."""
    monkeypatch.setattr(chunking, "_hf_tokenizer", _absent)
    assert chunking.count_tokens("a" * 40) == 10
