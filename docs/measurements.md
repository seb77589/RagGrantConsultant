# Measurements

The report's timings are engineering estimates, and its own caveat says to measure on about 10,000
sections before committing. These are the measurements. Re-run them after any change to chunking,
the embedding model, or the hardware.

Machine: NVIDIA GeForce RTX 3080 Laptop GPU (15.6 GB usable VRAM), 61 GB system RAM,
385 GB free on NVMe. Note this is **not** the ~8 TB of disk the report assumed.

## Corpus profile: CORDIS Horizon Europe

Dataset `cordis-HORIZONprojects-csv.zip`, 36,908,998 bytes, upstream last modified 2026-09-22,
sha256 `1496a16e...`. Built 2026-10-01.

| Measure | Value |
|---|---|
| Projects | 23,613 |
| Sections | 50,940 |
| Sections per project | 2.16 |
| Tokens | 13,520,730 |
| Mean tokens per section | 265 |
| Sections with a country | 50,940 (100%) |
| Sections with no upstream update date | 384 (0.75%) |
| Distinct countries | 52 |
| Build time | 72 s |

Against the report: it cited a third-party count of 19,495 Horizon Europe projects, but upstream
now holds **23,613**. It estimated CORDIS project records at 55,000–110,000 sections across
Horizon Europe *and* H2020 combined, central estimate 80,000. Horizon Europe alone yields 50,940,
and H2020's ~35,000 projects should add roughly 75,000, for about **126,000** — well above the
central estimate. CORDIS is a larger share of the corpus than planned.

Token counting matters here: the character heuristic used before the bge-m3 tokenizer was
installed over-estimated tokens by about 17%, which inflated the section count to 59,647. Always
measure with the real tokenizer.

## Embedding throughput: bge-m3

fp16 on CUDA, 10,000 sections sampled with a seeded reservoir across the whole dataset.

| Batch size | Sections/s | Peak VRAM |
|---|---|---|
| 16 | 140.7 | 1.24 GB |
| 32 | 141.7 | 1.42 GB |
| 64 | 141.4 | 1.77 GB |
| 128 | 135.8 | 2.48 GB |

Throughput is flat from 16 to 64 and falls off at 128, so the card is compute-bound rather than
batch-bound. **Batch 32** is the default.

At 141 sections/s, or 37,125 tokens/s:

| Corpus | Report's estimate | Measured extrapolation |
|---|---|---|
| 300,000 sections | 3–8 h | **0.6 h** |
| 500,000 sections | 5–13 h | **1.0 h** |
| 1,000,000 sections | 10–26 h | **2.0 h** |

### What this changes

The report is pessimistic on embedding by roughly 5–13x. Two caveats before leaning on that:

- These sections average 265 tokens, not the 400 the report assumed. Normalising to 400 tokens per
  section gives about 93 sections/s, so 300,000 sections would take about 0.9 h — still far under
  the estimate.
- This is a 71-second run. The report warns that laptop cooling throttles long embedding runs, and
  a sustained multi-hour run has not been measured. Even at three times worse, 300,000 sections is
  about 2 h.

Peak VRAM of 1.42 GB against 15.6 GB available is the more useful finding: embedding leaves room
for the generation model to stay resident, so the report's advice to stop the chat model during
bulk embedding may be unnecessary. Not yet verified with Qwen loaded alongside.

**The 500,000-section core cap was justified partly by embedding cost, and that justification is
now much weaker.** Re-embedding after a chunking change costs about 1 h at 500,000 sections, not a
day. The cap should be revisited once HNSW build time and search latency are measured on real
data, which needs PostgreSQL and pgvector installed.
