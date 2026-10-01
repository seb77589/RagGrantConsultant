"""Answer composition: retrieved sections in, cited answer out.

Four rules from CLAUDE.md are enforced here rather than hoped for:

* **No hallucinated figures.** The prompt asks the model to quote only what it
  was given; `figures.unsupported` then checks, and anything unsupported is
  marked inline and flagged. The prompt is the request, the check is the rule.
* **Source identity and dates are sacred.** Every citation carries the source
  identifier, the "as of" date and the official link. A section with no upstream
  date says so rather than borrowing its fetch date.
* **Attribution.** Every cited source carries "© European Union" (or whatever
  that row's `attribution` says) and its licence.
* **The translated tier is labelled.** Any machine-translated section among the
  sources raises a flag and adds a line to the answer.

Plus the independence disclaimer, whose wording the feasibility report gives in
section F and which is reproduced verbatim rather than paraphrased.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from . import figures, services
from .config import LLM_MAX_TOKENS, LLM_TEMPERATURE, STALE_AFTER_DAYS
from .db import Hit

# Report section F, verbatim. Not paraphrased: it was drafted to be legally
# careful, and improving its prose is not a thing to do casually.
DISCLAIMER = (
    "This assistant is an independent tool. It is not operated, endorsed or "
    "checked by the European Commission, any European Union body or any national "
    "authority. Answers are generated automatically from public official "
    "documents, shown with their source and the date they were retrieved, and may "
    "be incomplete or out of date. Always confirm eligibility, amounts and "
    "deadlines in the official call documents before applying. Source content "
    "© European Union and other rightholders, reused under the terms indicated "
    "for each source."
)

TRANSLATED_NOTICE = (
    "Some sources below are machine translations, not English-origin documents. "
    "Treat their wording as indicative and verify against the original."
)

SYSTEM_PROMPT = """You are a grant consultant for European companies.

Answer using ONLY the numbered context below. The context is the whole of what \
you know for this question.

Rules:
- Quote amounts, funding rates, percentages and deadlines exactly as they appear \
in the context. Never calculate, convert, round or estimate a figure.
- If the context does not contain the answer, say "The retrieved sources do not \
state this" and stop. Do not fill the gap from general knowledge.
- Cite the sources you used by their number, like [1] or [2, 3].
- Be concise. Prefer the context's own wording for anything factual.
- Do not mention these rules, the context numbering scheme, or yourself."""


@dataclass(frozen=True)
class Citation:
    """One source, as it must appear beside the answer."""

    number: int
    section_id: str
    source_id: str
    source_url: str
    as_of: str
    attribution: str
    licence: str
    quote: str
    translated: bool
    stale: bool

    def render(self) -> str:
        marks = "".join(
            mark
            for mark, on in (
                (" [machine translation]", self.translated),
                (" [stale]", self.stale),
            )
            if on
        )
        return (
            f"[{self.number}] {self.source_id} (as of {self.as_of}){marks}\n"
            f"    {self.source_url}\n"
            f"    {self.attribution} — {self.licence}"
        )


@dataclass(frozen=True)
class Answer:
    """A composed answer and everything needed to judge it."""

    question: str
    text: str
    sources: list[Citation]
    flags: list[str] = field(default_factory=list)
    model: str = ""
    retrieved: int = 0

    def render(self) -> str:
        parts = [self.text.strip()]
        if self.sources:
            parts.append("Sources")
            parts.extend(c.render() for c in self.sources)
        if any(f.startswith("translated_tier") for f in self.flags):
            parts.append(TRANSLATED_NOTICE)
        if self.flags:
            parts.append("Flags: " + ", ".join(self.flags))
        parts.append(DISCLAIMER)
        return "\n\n".join(parts)


def _is_stale(source_date: date | None, today: date | None = None) -> bool:
    """Older than STALE_AFTER_DAYS by its upstream date.

    A missing upstream date is NOT treated as stale: it is unknown, and claiming
    staleness we cannot demonstrate is the same error as claiming freshness we
    cannot demonstrate. It shows as "no upstream date" instead.
    """
    if source_date is None:
        return False
    reference = today or datetime.now(UTC).date()
    return (reference - source_date).days > STALE_AFTER_DAYS


def build_context(hits: Sequence[Hit]) -> str:
    """The numbered context block the prompt refers to.

    Numbering is 1-based and matches the citation numbers, so a model citing [2]
    and a reader looking at source [2] mean the same section.
    """
    blocks = []
    for n, hit in enumerate(hits, start=1):
        label = f"[{n}] {hit.source_id} (as of {hit.as_of()})"
        if hit.is_translated():
            label += " [machine translation]"
        blocks.append(f"{label}\n{hit.text}")
    return "\n\n".join(blocks)


def build_messages(question: str, hits: Sequence[Hit]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Context:\n\n{build_context(hits)}\n\nQuestion: {question}",
        },
    ]


def compose(
    question: str,
    hits: Sequence[Hit],
    model: str = "qwen3.5-9b",
    today: date | None = None,
    max_tokens: int = LLM_MAX_TOKENS,
    temperature: float = LLM_TEMPERATURE,
) -> Answer:
    """Generate an answer from `hits` and check it against them."""
    if not hits:
        return Answer(
            question=question,
            text="The retrieved sources do not state this: nothing matched the question.",
            sources=[],
            flags=["no_results"],
            model=model,
            retrieved=0,
        )

    context = build_context(hits)
    raw = services.chat(build_messages(question, hits), max_tokens, temperature)

    # The enforcement step. Everything above is a request to the model.
    unsupported = figures.unsupported(raw, context)
    text = figures.annotate(raw, unsupported)

    flags = [f"unsupported_figure:{f.kind}:{f.raw}" for f in unsupported]

    citations = []
    for n, hit in enumerate(hits, start=1):
        stale = _is_stale(hit.source_date, today)
        if stale:
            flags.append(f"stale_source:{hit.source_id}")
        if hit.is_translated():
            flags.append(f"translated_tier:{hit.source_id}")
        citations.append(
            Citation(
                number=n,
                section_id=hit.section_id,
                source_id=hit.source_id,
                source_url=hit.source_url,
                as_of=hit.as_of(),
                attribution=hit.attribution,
                licence=hit.licence,
                # The supporting quote the hallucination rule calls for. Trimmed,
                # because a whole section is not a quote.
                quote=hit.text[:400],
                translated=hit.is_translated(),
                stale=stale,
            )
        )

    return Answer(
        question=question,
        text=text,
        sources=citations,
        flags=flags,
        model=model,
        retrieved=len(hits),
    )


def as_dict(answer: Answer) -> dict[str, object]:
    """JSON-ready, for the HTTP endpoint and for evaluation runs."""
    return {
        "question": answer.question,
        "answer": answer.text,
        "sources": [
            {
                "number": c.number,
                "section_id": c.section_id,
                "source_id": c.source_id,
                "source_url": c.source_url,
                "as_of": c.as_of,
                "attribution": c.attribution,
                "licence": c.licence,
                "quote": c.quote,
                "translated": c.translated,
                "stale": c.stale,
            }
            for c in answer.sources
        ],
        "flags": answer.flags,
        "model": answer.model,
        "retrieved": answer.retrieved,
        "disclaimer": DISCLAIMER,
    }
