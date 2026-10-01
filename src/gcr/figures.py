"""Figure extraction and verification: the no-hallucinated-figures rule, in code.

CLAUDE.md: "Refuse to state amounts, funding rates, or deadlines that are not
present in the retrieved text; show the supporting quote; flag stale documents."
A prompt instruction is the first line of defence, not the enforcement. This
module is the enforcement: pull every amount, rate and date out of a generated
answer, pull the same out of the retrieved context, and report the ones that have
no counterpart.

**Normalisation is the whole difficulty.** A model writing "EUR 12 million"
against a source saying "EUR 12,000,000" is quoting correctly, and a guard that
flags it will be switched off within a day. So comparison happens on normalised
values, never on surface strings: thousands separators are stripped, scale words
expanded, percentages reduced to a number, dates reduced to ISO.

**Two things this does not do, stated here rather than discovered later:**

1. A figure that appears *coincidentally* in the context passes. If a source
   mentions 70 in an unrelated sentence and the model claims a 70% funding rate,
   this is satisfied. It verifies presence, not correct use.
2. A false claim made in words -- "the deadline has passed", "SMEs are
   ineligible" -- carries no figure and is invisible here.

It narrows the failure mode to one that can be counted across an evaluation set.
It does not close it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# Scale words, so "12 million" and "12,000,000" compare equal.
_SCALES = {
    "thousand": Decimal(1_000),
    "k": Decimal(1_000),
    "million": Decimal(1_000_000),
    "m": Decimal(1_000_000),
    "mio": Decimal(1_000_000),
    "billion": Decimal(1_000_000_000),
    "bn": Decimal(1_000_000_000),
}

_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ],
        start=1,
    )
}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})

# A number, either grouped with thousands separators or plain.
#
# The grouped branch requires at least one group (`+`, not `*`). With `*` it
# matches only a three-digit PREFIX of an ungrouped number -- "12000000" came
# out as 120 -- because alternation takes the first branch that matches at all,
# not the longest. Separators include the non-breaking and narrow spaces that
# pasted EU documents are full of.
_NUMBER = r"\d{1,3}(?:[ \xa0\u202f.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"

# Currency either side of the number: "EUR 12,000,000", "12 000 000 EUR", "€12m".
_CURRENCY = r"(?:EUR|eur|€|USD|\$|GBP|£)"
_MONEY_RE = re.compile(
    rf"(?:{_CURRENCY}\s*(?P<pre>{_NUMBER})(?:\s*(?P<prescale>thousand|million|billion|bn|mio|[km])\b)?"
    rf"|(?P<post>{_NUMBER})(?:\s*(?P<postscale>thousand|million|billion|bn|mio|[km])\b)?\s*{_CURRENCY})",
    re.IGNORECASE,
)

_PERCENT_RE = re.compile(
    rf"(?P<value>{_NUMBER})\s*(?:%|per\s*cent(?:um)?|percent)", re.IGNORECASE
)

_ISO_DATE_RE = re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b")
_LONG_DATE_RE = re.compile(
    r"\b(?P<d>\d{1,2})\s+(?P<month>[A-Za-z]{3,9})\.?\s+(?P<y>\d{4})\b"
)
_US_DATE_RE = re.compile(
    r"\b(?P<month>[A-Za-z]{3,9})\.?\s+(?P<d>\d{1,2}),?\s+(?P<y>\d{4})\b"
)
_YEAR_RE = re.compile(r"\b(?P<y>(?:19|20)\d{2})\b")

MONEY = "money"
PERCENTAGE = "percentage"
DATE = "date"


@dataclass(frozen=True)
class Figure:
    """One amount, rate or date, as written and as compared."""

    kind: str
    raw: str
    normalised: str

    def __str__(self) -> str:
        return self.raw


def _to_decimal(text: str) -> Decimal | None:
    """Parse a number that may use either convention for separators.

    `1.234,56` is European and `1,234.56` is Anglo, and both appear in EU
    material. The rule used: whichever of comma or dot appears last is the
    decimal separator, and anything before it that looks like grouping is
    stripped. A lone separator followed by exactly three digits is grouping.
    """
    cleaned = re.sub(r"[ \xa0\u202f]", "", text.strip())
    if not cleaned:
        return None

    last_comma, last_dot = cleaned.rfind(","), cleaned.rfind(".")
    if last_comma == -1 and last_dot == -1:
        candidate = cleaned
    else:
        sep_at = max(last_comma, last_dot)
        sep = cleaned[sep_at]
        tail = cleaned[sep_at + 1 :]
        if len(tail) == 3 and cleaned.count(sep) >= 1 and "." not in tail and "," not in tail:
            # Three trailing digits: grouping, not a decimal.
            candidate = re.sub(r"[.,]", "", cleaned)
        else:
            candidate = re.sub(r"[.,]", "", cleaned[:sep_at]) + "." + tail
    try:
        return Decimal(candidate)
    except InvalidOperation:
        return None


def _normalise_amount(value: Decimal) -> str:
    """A canonical string for an amount, so 12000000 and 12000000.00 match.

    `format(..., "f")` rather than `str(value.normalize())`: normalize() returns
    scientific notation for round numbers, so 12000000 became "1.2E+7" and
    70 became "7E+1" -- which compare unequal to the same value written any
    other way, defeating the whole point of normalising.
    """
    return format(value.normalize(), "f")


def _iso(year: str, month: int, day: str) -> str | None:
    try:
        y, d = int(year), int(day)
    except ValueError:
        return None
    if not (1 <= month <= 12 and 1 <= d <= 31 and 1900 <= y <= 2100):
        return None
    return f"{y:04d}-{month:02d}-{d:02d}"


def extract_figures(text: str) -> list[Figure]:
    """Every amount, rate and date in `text`, in the order they appear.

    Dates are matched before bare years so that "14 November 2024" yields one
    date rather than a date and a stray year.
    """
    found: list[Figure] = []
    claimed: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < e and s < end for s, e in claimed)

    def take(match: re.Match[str], kind: str, normalised: str) -> None:
        if overlaps(match.start(), match.end()):
            return
        claimed.append((match.start(), match.end()))
        found.append(Figure(kind, match.group(0).strip(), normalised))

    for match in _MONEY_RE.finditer(text):
        number = match.group("pre") or match.group("post")
        scale = match.group("prescale") or match.group("postscale")
        value = _to_decimal(number) if number else None
        if value is None:
            continue
        if scale:
            value *= _SCALES[scale.lower()]
        take(match, MONEY, _normalise_amount(value))

    for match in _PERCENT_RE.finditer(text):
        value = _to_decimal(match.group("value"))
        if value is not None:
            take(match, PERCENTAGE, _normalise_amount(value))

    for match in _ISO_DATE_RE.finditer(text):
        iso = _iso(match.group("y"), int(match.group("m")), match.group("d"))
        if iso:
            take(match, DATE, iso)

    for regex in (_LONG_DATE_RE, _US_DATE_RE):
        for match in regex.finditer(text):
            month = _MONTHS.get(match.group("month").lower())
            if month is None:
                continue
            iso = _iso(match.group("y"), month, match.group("d"))
            if iso:
                take(match, DATE, iso)

    for match in _YEAR_RE.finditer(text):
        take(match, DATE, match.group("y"))

    return found


def _supported_values(context: str) -> set[tuple[str, str]]:
    """What the retrieved text vouches for, as (kind, normalised) pairs.

    A date in the context also vouches for its year on its own, because an answer
    may reasonably say "in 2024" where the source says "14 November 2024".
    """
    supported: set[tuple[str, str]] = set()
    for figure in extract_figures(context):
        supported.add((figure.kind, figure.normalised))
        if figure.kind == DATE and len(figure.normalised) == 10:
            supported.add((DATE, figure.normalised[:4]))
    return supported


def unsupported(answer: str, context: str) -> list[Figure]:
    """Figures in `answer` that `context` does not vouch for.

    Deduplicated by (kind, normalised): a model repeating the same unsupported
    rate four times is one defect to fix, not four.
    """
    supported = _supported_values(context)
    seen: set[tuple[str, str]] = set()
    out: list[Figure] = []
    for figure in extract_figures(answer):
        key = (figure.kind, figure.normalised)
        if key in supported or key in seen:
            continue
        seen.add(key)
        out.append(figure)
    return out


def annotate(answer: str, unsupported_figures: list[Figure]) -> str:
    """Mark unsupported figures inline, leaving the rest of the answer intact.

    Chosen over refusing the whole answer or silently stripping the figure: a
    refusal throws away correct work over one stray number, and stripping hides
    the defect, which is precisely what an evaluation set needs to see.
    """
    marked = answer
    for figure in unsupported_figures:
        # Replace only the first occurrence, so the marker is not repeated for a
        # figure the model stated several times.
        marked = marked.replace(figure.raw, f"{figure.raw} [⚠ unsupported]", 1)
    return marked
