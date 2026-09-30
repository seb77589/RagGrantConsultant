"""bge-m3 embedding and a throughput benchmark.

The report's timings are estimates; its own caveat says to measure on about
10,000 sections before committing. `benchmark` is that measurement, and it
extrapolates to the corpus sizes the report tabulates so the two can be
compared directly.

Imports of the GPU stack are deferred so the rest of the pipeline works
without the embed extra installed.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from .config import CORE_SECTION_CAP, EMBED_BATCH_SIZE, EMBED_DIM, EMBED_MODEL


@dataclass
class BenchmarkResult:
    n_sections: int
    total_tokens: int
    wall_seconds: float
    batch_size: int
    device: str
    fp16: bool
    peak_vram_gb: float | None
    extrapolation: dict[int, float] = field(default_factory=dict)

    @property
    def sections_per_second(self) -> float:
        return self.n_sections / self.wall_seconds if self.wall_seconds else 0.0

    def render(self) -> str:
        lines = [
            f"device            : {self.device} (fp16={self.fp16})",
            f"model             : {EMBED_MODEL} ({EMBED_DIM}-d)",
            f"sections embedded : {self.n_sections:,}",
            f"tokens            : {self.total_tokens:,}",
            f"wall time         : {self.wall_seconds:.1f} s",
            f"throughput        : {self.sections_per_second:.1f} sections/s",
            f"batch size        : {self.batch_size}",
        ]
        if self.peak_vram_gb is not None:
            lines.append(f"peak VRAM         : {self.peak_vram_gb:.2f} GB")
        if self.extrapolation:
            lines.append("")
            lines.append("extrapolated full-corpus embedding time:")
            for n, hours in sorted(self.extrapolation.items()):
                flag = "  <- over the core cap" if n > CORE_SECTION_CAP else ""
                lines.append(f"  {n:>9,} sections : {hours:5.1f} h{flag}")
        return "\n".join(lines)


def load_model(fp16: bool = True):
    """Load bge-m3. Raises ImportError with a hint when the extra is missing."""
    try:
        from FlagEmbedding import BGEM3FlagModel
    except ImportError as exc:  # pragma: no cover - depends on install state
        raise ImportError(
            "FlagEmbedding is not installed. Run: uv sync --extra embed"
        ) from exc
    return BGEM3FlagModel(EMBED_MODEL, use_fp16=fp16)


def embed_texts(
    model, texts: Sequence[str], batch_size: int = EMBED_BATCH_SIZE
) -> list[list[float]]:
    """Dense vectors only. bge-m3 also emits sparse and ColBERT outputs, which
    we do not store yet: PostgreSQL full-text search covers the keyword half of
    hybrid retrieval."""
    out = model.encode(list(texts), batch_size=batch_size, return_dense=True,
                       return_sparse=False, return_colbert_vecs=False)
    return out["dense_vecs"].tolist()


def benchmark(
    texts: Sequence[str],
    batch_size: int = EMBED_BATCH_SIZE,
    fp16: bool = True,
    extrapolate_to: Sequence[int] = (300_000, 500_000, 1_000_000),
) -> BenchmarkResult:
    """Embed `texts` and report throughput plus extrapolated corpus timings."""
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()

    model = load_model(fp16=fp16)

    # Warm up so kernel compilation and weight transfer do not land in the
    # measured window.
    if texts:
        embed_texts(model, texts[: min(8, len(texts))], batch_size=min(8, batch_size))

    start = time.perf_counter()
    embed_texts(model, texts, batch_size=batch_size)
    if device == "cuda":
        torch.cuda.synchronize()
    wall = time.perf_counter() - start

    peak = (
        torch.cuda.max_memory_allocated() / (1024**3) if device == "cuda" else None
    )
    rate = len(texts) / wall if wall else 0.0
    extrapolation = {n: (n / rate) / 3600 for n in extrapolate_to} if rate else {}

    from .chunking import count_tokens

    return BenchmarkResult(
        n_sections=len(texts),
        total_tokens=sum(count_tokens(t) for t in texts),
        wall_seconds=wall,
        batch_size=batch_size,
        device=device,
        fp16=fp16,
        peak_vram_gb=peak,
        extrapolation=extrapolation,
    )
