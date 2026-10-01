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

## Model serving, containerised

Measured 2026-10-01 on the containerised stack (see `containerisation-plan.md`). All three model
services run on the one RTX 3080 Laptop simultaneously; the driver time-slices between them.

### What is actually served

The feasibility report says "Qwen3.5-9B" and leaves it there, which is not enough to reproduce a run.
The model exists, but it is not the plain dense 9B that wording suggests: it is a hybrid **Gated
DeltaNet + sparse MoE** model, multimodal, with 262,144 native context and reasoning enabled by
default.

| Role | Served by | Image |
|---|---|---|
| Generation | `unsloth/Qwen3.5-9B-GGUF` → `Qwen3.5-9B-UD-Q4_K_XL.gguf` (5,966,095,584 B) | `ghcr.io/ggml-org/llama.cpp:server-cuda-b11206` |
| Embeddings | `BAAI/bge-m3`, 1024-d, **CLS pooling** | `ghcr.io/huggingface/text-embeddings-inference:86-1.9.4` |
| Reranking | `BAAI/bge-reranker-v2-m3`, via TEI's native `/rerank` | same TEI image |

Generation flags that matter: `--ctx-size 16384` (never the native 262144), `--n-gpu-layers 999`,
`--cache-type-k q8_0 --cache-type-v q8_0`, `--flash-attn auto`, `--reasoning off`, `--host 0.0.0.0`.

### VRAM: the stack is far lighter than the report assumed

| Process | VRAM |
|---|---|
| llama.cpp (Qwen3.5-9B Q4_K_XL, 16k ctx, q8_0 KV) | 5,958 MiB |
| TEI bge-m3 | 1,362 MiB |
| TEI bge-reranker-v2-m3 | 1,330 MiB |
| **Total resident** | **8,732 MiB of 16,384** |
| **Free** | **7,244 MiB** |

The report estimated 9–12 GB for the same three roles, and the containerisation plan budgeted
11–14 GB. Actual is **8.5 GB, with 7.2 GB spare** — so the GPU is not the binding constraint it was
treated as. Two consequences:

- **The report's advice to stop the chat model during bulk embedding is unnecessary.** Embedding
  peaks at 1.42 GB; with the full serving stack resident there is more than four times that free.
  This settles the question left open in the embedding-throughput section above.
- There is room to raise `--ctx-size` beyond 16k if a future retrieval path ever needs it, though
  6–10 reranked sections do not.

### The two embedding paths agree

The index is built by the pipeline's local FlagEmbedding and queried through the TEI service. If
those disagree the vectors are incomparable, and retrieval degrades in a way that looks like a weak
corpus rather than a configuration fault. Cosine similarity between the two, same input:

| Text | Cosine |
|---|---|
| "Funding for photonics research in Ireland." | 0.999995 |
| "The call has a budget of EUR 12,000,000 and a 70% funding rate." | 0.999994 |
| "Kis- és középvállalkozások támogatása." (non-ASCII) | 0.999988 |

Worst case 0.999988 against a 0.99 bar. This also confirms `--pooling cls` is correct: bge-m3 is
CLS-pooled, and a silent fall-through to mean pooling would have shown here as a much lower cosine.

### Generation quality on this hardware

llama.cpp's support for Gated DeltaNet is recent, with open issues covering a CUDA kernel crash on
sm_70, silent instant-EOS past ~130k context, and HIP context corruption. None is confirmed for
sm_86, so the model was smoke-tested for coherence before anything was built on it:

- Grounded extraction from a supplied context returned the correct funding rate and deadline.
- Asked for a deadline the context did not contain, it said so rather than inventing one — the
  behaviour the no-hallucinated-figures rule depends on.
- A sustained 400-token completion stayed coherent and accurate (the 250-employee and €50 million
  ceilings of Recommendation 2003/361/EC) with no drift and no premature EOS.

Model load takes 2.8 s from the local GGUF. No `<think>` tags appear with `--reasoning off`.

**Caveat:** this is a smoke test at ~16k context, not a systematic evaluation, and it does not clear
the known GDN defects at long context. The fallback if problems appear later is a plain-dense
Qwen3-8B-class GGUF, which avoids the GDN code path entirely.
