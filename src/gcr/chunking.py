"""Sentence-aware chunking.

Splits on paragraph then sentence boundaries and packs up to TARGET_TOKENS,
never exceeding MAX_TOKENS, with a small overlap so a fact spanning a boundary
is still retrievable. Chunking decisions are recorded as CHUNKING_VERSION
because changing them forces a full re-embed.

Token counting uses the real bge-m3 tokenizer when the embed extra is
installed, and a calibrated character heuristic otherwise, so the pipeline is
testable without the GPU stack.
"""

from __future__ import annotations

import re
from functools import lru_cache

from .config import MAX_TOKENS, OVERLAP_TOKENS, TARGET_TOKENS

# English averages close to 4 characters per token on XLM-R style vocabularies.
_CHARS_PER_TOKEN = 4.0

_PARA_RE = re.compile(r"\n\s*\n+")

# Candidate sentence boundary: . ! ? then whitespace then something that can
# open a sentence. Abbreviations are rejected afterwards in code, because a
# variable-width alternation is not allowed inside a Python lookbehind.
_CANDIDATE_RE = re.compile(r'(?<=[.!?])\s+(?=["\u201c(\u2018\']?[A-Z0-9])')
_TRAILING_WORD_RE = re.compile(r"([A-Za-z][A-Za-z.]*)\.\s*$")

# Abbreviations that routinely precede a digit or capital in EU funding text,
# where splitting would strand a reference from the rule it introduces.
_ABBREVIATIONS = frozenset(
    {
        "art", "arts", "artt", "no", "nos", "nr", "p", "pp", "para", "paras",
        "cf", "e.g", "i.e", "etc", "vs", "viz", "fig", "figs", "tbl", "ann",
        "annex", "reg", "regs", "dir", "dec", "chap", "ch", "sec", "sect",
        "subsec", "approx", "incl", "excl", "min", "max", "resp", "al", "ibid",
        "op", "cit", "ed", "eds", "vol", "vols", "ref", "refs", "eur", "mio",
        "mr", "mrs", "ms", "dr", "prof", "st", "jan", "feb", "mar", "apr",
        "jun", "jul", "aug", "sep", "sept", "oct", "nov",
    }
)


def _is_abbreviation(left: str) -> bool:
    """True when the period ending `left` closes an abbreviation, not a sentence.

    Erring towards "not a boundary" is the safer bias: an over-long sentence is
    still split later by token budget, whereas a wrongly split one separates a
    figure or article number from its context and retrieves poorly.
    """
    match = _TRAILING_WORD_RE.search(left)
    if match is None:
        return False
    word = match.group(1).rstrip(".").lower()
    if word in _ABBREVIATIONS:
        return True
    # A single letter is an initial or a section label ("Annex I."), and a
    # dotted acronym ("U.S.") ends in one too.
    return len(word) == 1 or len(word.split(".")[-1]) == 1


def _split_paragraph(para: str) -> list[str]:
    sentences: list[str] = []
    start = 0
    for m in _CANDIDATE_RE.finditer(para):
        if _is_abbreviation(para[start : m.start()]):
            continue
        piece = para[start : m.start()].strip()
        if piece:
            sentences.append(piece)
        start = m.end()
    tail = para[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


@lru_cache(maxsize=1)
def _hf_tokenizer():
    """bge-m3 tokenizer if available, else None. Cached: loading is slow."""
    try:
        from transformers import AutoTokenizer
    except ImportError:
        return None
    try:
        from .config import EMBED_MODEL

        return AutoTokenizer.from_pretrained(EMBED_MODEL)
    except Exception:  # noqa: BLE001 - any failure here must degrade, not abort
        # No local weights and no network: fall back to the character estimate
        # rather than fail an ingestion run that does not need exact counts.
        return None


def count_tokens(text: str) -> int:
    tok = _hf_tokenizer()
    if tok is not None:
        return len(tok.encode(text, add_special_tokens=False))
    return max(1, round(len(text) / _CHARS_PER_TOKEN))


def tokenizer_name() -> str:
    """Which counter is in force. Printed by `gcr sections` so a run says so."""
    return "bge-m3" if _hf_tokenizer() is not None else "character-heuristic"


def require_real_tokenizer() -> None:
    """Refuse to build a corpus with the character heuristic.

    The fallback in `_hf_tokenizer` is deliberate: tests and the lint path must
    run without the GPU stack. But the heuristic over-estimates by about 17%,
    which inflates token counts, forces splits that the real tokenizer would
    not, and so yields a *different corpus* — silently. Any path whose output
    is recorded, compared or embedded must therefore insist on the real thing.

    Discovered the hard way: the containerised pipeline produced different
    chunk boundaries from the host until this was enforced.
    """
    if _hf_tokenizer() is None:
        raise RuntimeError(
            "the real bge-m3 tokenizer is unavailable, so token counts would "
            "come from the character heuristic, which over-estimates by ~17% "
            "and produces a different corpus.\n"
            "  fix:      install the tokenizer   -> uv sync --extra tokenize\n"
            "  in a container: the 'tokenize' extra is in the pipeline image; "
            "a first run needs network to fetch the tokenizer into HF_HOME\n"
            "  override: --allow-token-heuristic (for a rough count only; "
            "never for a corpus that will be embedded or compared)"
        )


def split_sentences(text: str) -> list[str]:
    out: list[str] = []
    for block in _PARA_RE.split(text.strip()):
        para = block.strip()
        if para:
            out.extend(_split_paragraph(para))
    return out


def _force_split(sentence: str, max_tokens: int) -> list[str]:
    """Break one over-long sentence on whitespace as a last resort."""
    words = sentence.split()
    if not words:
        return []
    pieces: list[str] = []
    cur: list[str] = []
    for w in words:
        cur.append(w)
        if count_tokens(" ".join(cur)) >= max_tokens:
            pieces.append(" ".join(cur))
            cur = []
    if cur:
        pieces.append(" ".join(cur))
    return pieces


def chunk_text(
    text: str,
    target_tokens: int = TARGET_TOKENS,
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[str]:
    """Pack sentences into chunks of about `target_tokens`.

    Returns [] for blank input. Never returns a chunk over `max_tokens`.
    """
    if not text or not text.strip():
        return []

    sentences: list[str] = []
    for s in split_sentences(text):
        if count_tokens(s) > max_tokens:
            sentences.extend(_force_split(s, max_tokens))
        else:
            sentences.append(s)

    chunks: list[str] = []
    cur: list[str] = []
    cur_tokens = 0

    for s in sentences:
        n = count_tokens(s)
        if cur and cur_tokens + n > target_tokens:
            chunks.append(" ".join(cur))
            # Carry back whole trailing sentences up to the overlap budget.
            carry: list[str] = []
            carried = 0
            for prev in reversed(cur):
                pn = count_tokens(prev)
                if carried + pn > overlap_tokens:
                    break
                carry.insert(0, prev)
                carried += pn
            cur = carry
            cur_tokens = carried
        cur.append(s)
        cur_tokens += n

    if cur:
        chunks.append(" ".join(cur))

    chunks = _merge_short_tail(chunks, max_tokens)
    return [c for c in (c.strip() for c in chunks) if c]


def _merge_short_tail(chunks: list[str], max_tokens: int) -> list[str]:
    """Fold a small trailing chunk back into its predecessor.

    Packing to `target_tokens` leaves a short tail whenever a document is just
    over a multiple of the target - CORDIS objectives average about 456 tokens,
    so a 400-token target would otherwise emit a full chunk plus a ~60-token
    fragment. A fragment that small retrieves poorly and doubles the section
    count for no gain, so merge it whenever the result still fits `max_tokens`.
    """
    if len(chunks) < 2:
        return chunks
    merged = chunks[:-1]
    tail = chunks[-1]
    combined = merged[-1] + " " + tail
    if count_tokens(tail) < max_tokens // 4 and count_tokens(combined) <= max_tokens:
        merged[-1] = combined
        return merged
    return chunks
