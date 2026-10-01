# Containerisation plan

Tracked, resumable checklist for moving the whole runtime stack into containers.

The name is engine-neutral on purpose: the stack targets Docker Compose today (see
[Why Docker](#why-docker-and-what-it-trades-away)), and nothing here should make a later move to
rootless Podman harder than it needs to be.

---

## How to resume this work

If a session ends abruptly, a fresh session should do exactly this:

1. Read the **[Status](#status)** table below to see which phase was in flight.
2. Find the **first unticked `- [ ]` step** in that phase.
3. Re-run the **previous** step's validation to confirm it still holds. Do not trust the checkbox —
   the checkbox is only a claim, and the claim may predate a `docker compose down -v`.
4. Continue from the first unticked step.

This work lives on the **`containerisation`** branch, not `main`. Each phase is committed as it
completes, and the commit is recorded in the Status table — so a step's checkbox can always be traced
to the change that earned it.

**Ground truth is the machine, not this file.** These three commands say what actually exists:

```bash
docker compose ps -a            # what is running, and whether it is healthy
docker volume ls | grep gcr_    # what state survives
docker image ls                 # what has been pulled or built
```

A step is ticked **only when its validation has been run and passed** — not when the code was
written. Writing a compose service is not the same as proving it comes up.

Measured numbers live in [`measurements.md`](measurements.md), the project's existing home for them.
This file links to them rather than duplicating them.

---

## Status

| Phase | What it delivers | State | Date | Commit |
|---|---|---|---|---|
| 0 | Preflight and baseline | **done** | 2026-10-01 | `b703ba8` |
| 1 | Scaffolding, `.env`, secrets, doc amendments | **done** | 2026-10-01 | `48607dc` |
| 2 | Database tier (PostgreSQL + pgvector) | **done** | 2026-10-01 | `35da3b1` |
| 3 | Pipeline image | **done** | 2026-10-01 | `9606587` |
| 4 | Parity gate | **done** | 2026-10-01 | `78c3964` |
| 5 | Model tier (embed, rerank, generate) | **done** | 2026-10-01 | `0da4802` |
| 6 | Load, index, and the blocked measurements | **done** | 2026-10-01 | `2772d8b` |
| 7 | Identity tier (LLDAP, Authelia) | **done** | 2026-10-01 | `649fbcf` |
| 8 | Edge (Caddy, forward auth, TLS) | **done** | 2026-10-01 | `649fbcf` |
| 9 | Group-to-row-level access | **done** | 2026-10-01 | `649fbcf` |
| 10 | Migration-equivalence proof | **done** | 2026-10-01 | `ba8aace` |
| 11 | Cleanliness audit and resumability | **done** | 2026-10-01 | `7f986f0` |

---

## Why Docker, and what it trades away

The machine already has everything needed to run containers, so **no host packages are required**:

| Component | State on host | Verdict |
|---|---|---|
| Docker Engine 29.1.3 (rootful), containerd 2.2.2 | already installed, `docker.service` enabled | reuse |
| Docker Compose v2.40.3 | already installed | reuse |
| NVIDIA Container Toolkit 1.20.1, `nvidia` runtime in `/etc/docker/daemon.json` | already installed, driver 595.91.07 | reuse |
| user `ninel` in the `docker` group | yes | reuse |
| PostgreSQL, pgvector, Caddy, Authelia, LLDAP, model servers | not installed | containerise |

The only things that genuinely cannot be containerised are the container engine and the GPU kernel
driver, and both are already present. The host `apt-get install` list that preceded this plan is
therefore dropped entirely. **Net new host packages: zero.** Phase 11 proves that claim rather than
asserting it.

**The trade.** `CLAUDE.md` originally mandated rootless Podman with Quadlet systemd units, and the
feasibility report budgets 8–12 h for that as a *job-practice* work package. Choosing Docker drops
that rehearsal item. Two mitigations: the compose files avoid Docker-only features where avoiding
them is free, and step 11.3 records what a Podman conversion would involve. One deliberate
exception — the GPU `driver: cdi` syntax in `compose.yaml` is **not** supported by podman-compose
([containers/podman#19338](https://github.com/containers/podman/issues/19338)), so that is the one
block a conversion must rewrite.

---

## Repo constraints this must respect

Found by reading the code. These are the things most likely to break silently inside a container:

- **`src/gcr/config.py:12` — `REPO_ROOT = Path(__file__).resolve().parents[2]`.** Paths derive from
  the source tree at import time, so the image must place the project at `/app` with the package at
  `/app/src/gcr`. A normal wheel install into `site-packages` computes a wrong root — install
  **editable**.
- **`src/gcr/fetch.py:69` — `path=str(dest.relative_to(REPO_ROOT))`** raises `ValueError` if a
  download target sits outside `REPO_ROOT`. The data volume **must** mount at `/app/data`, not at a
  tidier path like `/data`.
- **No environment variables exist anywhere in the codebase.** `config.py` is plain module constants.
  The database needs a new, deliberately small config surface (step 2.4) rather than being threaded
  through existing plumbing.
- **The HuggingFace cache is unconfigured**, defaulting to `~/.cache/huggingface`. Point it at a
  named volume via `HF_HOME` or every container rebuild re-downloads several GB.
- **Python is pinned `>=3.12,<3.13`** because the ML wheels do not build on 3.13+. The image uses
  3.12, not "latest".
- **`.gitignore` already reserves** `secrets/`, `pgdata/`, `volumes/`, `models/`, `data/cache/`,
  `**/authelia/configuration.yml`, `**/lldap/lldap_config.toml` and `compose.override.yml`, and keeps
  `!.env.example`. The layout below deliberately matches names it already anticipates.
- **Baseline to preserve.** [`measurements.md`](measurements.md) records 23,613 projects →
  **50,940 sections**, 13,520,730 tokens, ~141 sections/s. `data/interim/cordis-horizon-sections.jsonl`
  is on disk at exactly 50,940 lines, so parity can be checked by diffing section IDs rather than
  merely counting them.

---

## Target layout

```
GrantConsultantRAG/
├── compose.yaml                  # all services, behind profiles
├── compose.proof.yaml            # overlay: second DB for the migration proof
├── .env.example                  # committed; .env is gitignored
├── containers/
│   ├── pipeline/Containerfile    # python:3.12-slim + uv + editable install, base/embed targets
│   ├── caddy/Caddyfile
│   ├── authelia/configuration.yml.example
│   ├── lldap/lldap_config.toml.example
│   ├── gen-secrets.sh            # idempotent: writes .env and secrets/
│   ├── fetch-model.sh            # pulls the GGUF into the gcr_models volume, size-checked
│   └── db/
│       ├── initdb/               # 00-authelia-db.sh, 01-extensions.sql, 02-schema.sql, 03-indexes.sql
│       └── hnsw.sql              # built after the bulk load, in 6.2, so the timing means something
├── secrets/.gitkeep              # generated secrets, gitignored
└── docs/
    ├── containerisation-plan.md  # this file
    └── measurements.md           # extended by phases 5 and 6
```

### Services and profiles

Profiles keep the GPU tier off when only the database is wanted.

| Service | Profile | Published port | Volume |
|---|---|---|---|
| `db` | `core` | `127.0.0.1:5432` (dev only) | `gcr_pgdata` |
| `pipeline` (built) | `tools`, run-on-demand | none | `./data:/app/data`, `gcr_hf_cache` |
| `tei-embed` | `models` | internal | `gcr_hf_cache` |
| `tei-rerank` | `models` | internal | `gcr_hf_cache` |
| `llm` | `models` | internal | `gcr_models` |
| `lldap` | `auth` | internal | `gcr_lldap_data` |
| `authelia` | `auth` | internal | uses `db` (separate database and role) |
| `caddy` | `edge` | `443`, `80` | `gcr_caddy_data`, `gcr_caddy_config` |

Only Caddy publishes to the network. That is the whole point of putting Authelia in front.

### Pinned images

Verified against live sources on 2026-10-01. Pins are exact on purpose: floating tags move silently.

| Service | Pin | Note |
|---|---|---|
| `db` | `pgvector/pgvector:0.8.6-pg18-trixie` | pgvector 0.8.6 (2026-07-29). **Must be ≥ 0.8.4 on PG18**: 0.8.3 fixed HNSW index corruption during vacuum, 0.8.4 fixed vacuum errors on concurrent insert. Fallback `0.8.6-pg17-trixie` loses nothing vector-side. |
| `tei-embed`, `tei-rerank` | `ghcr.io/huggingface/text-embeddings-inference:86-1.9.4` | `86` = Ampere sm_86. TEI 1.9.4 (2026-09-15). **Tag confirmed to exist in 0.3**; fallback `86-1.9` also exists. Listens on **port 80**, not 8080. |
| `llm` | `ghcr.io/ggml-org/llama.cpp:server-cuda-b11206`<br>`@sha256:e2f285f5b208ea5940a28f1573ae4791a8735dd1c41aa0e4f4836aab211bb734` | **Corrected in 0.3.** GitHub releases are at `b11312`, but container images are published for only a subset of builds — the highest `server-cuda-b*` tag on GHCR is `b11206` (540 such tags across 12,000 total). The floating `server-cuda` tag has a *different* digest again, so it is ahead of the published b-tags: do not use it. Confirm the digest still serves after the 5.0 spike. |
| model weights | `unsloth/Qwen3.5-9B-GGUF` → `Qwen3.5-9B-UD-Q4_K_XL.gguf` | **Confirmed in 0.3**: 5,966,095,584 bytes = 5.56 GiB, repo last modified 2026-03-02. See risk R1. |
| `authelia` | `ghcr.io/authelia/authelia:4.39.28` | 2026-09-17 |
| `lldap` | `lldap/lldap:v0.6.3` | SQLite backend on a named volume |
| `caddy` | `caddy:2.11.4-alpine` | 2026-09-23 |

---

## Risk register

Kept here so an unresolved unknown cannot quietly become an assumption. Update **Status** as each is
settled.

| ID | Risk | Status |
|---|---|---|
| R1 | Qwen3.5-9B on llama.cpp | **closed in 5.0** — coherent on sm_86 at 16k ctx |
| R2 | VRAM has no grace | **closed in 5.5** — 8.5 GB of 16, 7.2 GB spare |
| R3 | Caddy local CA needs manual trust | **confirmed in 8.4** — runbook step written |
| R4 | Docker 29 containerd image store | **confirmed, benign here** — see below |
| R5 | Healthcheck false-negatives on first start | **hit, and fixed** — see below |
| R6 | Compose CDI needs `capabilities: [gpu]` | **closed in 0.2** — see below |
| R7 | llama.cpp mangles `--flag=value` | **closed in 5.3** — pass flag and value separately |

**R1 — Qwen3.5-9B on llama.cpp is the single biggest risk.** The model is not the plain dense 9B the
feasibility report implies: it is hybrid **Gated DeltaNet + sparse MoE**, multimodal, 262k native
context, and a **thinking model by default**. llama.cpp's GDN support is recent and visibly buggy —
open issues cover a CUDA kernel crash on sm_70
([#29783](https://github.com/ggml-org/llama.cpp/issues/29783)), silent instant-EOS past ~130k context
([#27756](https://github.com/ggml-org/llama.cpp/issues/27756)), and HIP context corruption
([#27556](https://github.com/ggml-org/llama.cpp/issues/27556)). No positive confirmation for sm_86
was found either way. This machine is plausibly outside both known blast radii (sm_86, ~16k context),
but that is an inference, not a confirmation. **Mitigation:** step 5.0 is a standalone generation
spike before anything depends on it; the named fallback is a plain-dense Qwen3-8B-class GGUF with
zero GDN exposure. Separately, `<think>` must be disabled with
`--chat-template-kwargs '{"enable_thinking":false}'` or both latency and output format break.

**R2 — VRAM has no grace.** Realistic resident budget: TEI embed ~2.0–2.5 GB, TEI rerank
~2.0–2.5 GB, llama.cpp ~7–9 GB at 16k context ⇒ **~11–14 GB of 15.9 GB**. CUDA OOM in llama.cpp is a
hard crash, not a degrade. Mitigations in step 5.3: `--ctx-size 16384` (never the model's 262144,
which is also a `CLAUDE.md` hard rule), `--cache-type-k q8_0 --cache-type-v q8_0`, and a reduced
`--max-batch-tokens` on the reranker where batches are small and bounded. GPU time-slicing across
three containers works, but it is not fair-sharing: expect embedding p99 to spike during generation.
Fine for a single user; do not promise concurrent throughput.

**R3 — Caddy's local CA needs manual trust**, and this looks like a broken deployment if unplanned.
Caddy cannot auto-install its root CA from inside a container. The CA lives at
`/data/caddy/pki/authorities/local/root.crt` and must be copied out and trusted; Firefox and Chrome
on Linux need it imported into the browser's own store separately. Step 8.4 is that runbook entry.
`/data` must be a named volume or the CA regenerates on every recreate and the trust must be redone.

**R4 — Docker 29 made containerd the default image store.** *Confirmed in 0.1 and benign here:*
`docker image ls` reports **0 images** despite 25 pre-existing volumes from other projects, because
images in the classic store are no longer listed. Nothing this project needs is affected — every
image is pulled fresh — but it does mean the other projects on this machine (`legalease-*`,
`ai-chat`) will re-pull on next use, and that is not something this plan caused. The minimum API
version is now 1.44, so anything talking to the Docker socket must be recent. Compose 2.40.3 is
already past the CVE-2025-62725 fix (2.40.2) — do not downgrade.

**R6 — Compose rejects a CDI device reservation without `capabilities`.** *Closed in 0.2.* The
verification pass proposed `driver: cdi` + `device_ids` alone; Compose v2.40.3 refuses that with
`missing property 'capabilities'`. The working form, confirmed against the real GPU, is:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: cdi
          capabilities: [gpu]
          device_ids: ["nvidia.com/gpu=0"]
```

Also worth knowing: the CDI spec is auto-generated by the toolkit at **`/var/run/cdi/nvidia.yaml`**,
not `/etc/cdi`. `/var/run` is tmpfs, so the spec is regenerated per boot — fine, but it means a
missing `nvidia.com/gpu=0` after a reboot is a toolkit-regeneration issue, not a compose error.

**R5 — healthchecks will false-negative on first start.** TEI and llama.cpp take 30–120 s to load
weights, longer on first download. Use `start_period: 180s` or Compose tears the stack down during
the very first model pull. The slim images may not contain `curl`, so a naive
`CMD curl -f .../health` can fail for the wrong reason — verify the binary exists or use `CMD-SHELL`
with whatever is present.

---

## Phase 0 — Preflight and baseline

Read-only. Establishes what "clean" meant before any of this, so Phase 11 can prove the machine came
back to it.

- [x] **0.1 Record the host baseline.** Summary in `data/reference/host-baseline-pre.txt` (committed);
      full inventories in `data/cache/host-baseline-pre-*.txt` (gitignored). **2,406 apt packages**,
      sorted-list sha256 `5ecc79c10807…c17542` — that hash is the Phase 11.2 comparison target.
      0 images, 25 volumes (all pre-existing), 0 containers, 3 default networks, 374 GB free.
- [x] **0.2 Prove GPU-in-container works.** Verified three ways: `--gpus all`, `--device
      nvidia.com/gpu=0`, and a real Compose service using the `deploy` CDI block. All three see the
      RTX 3080 Laptop with 15,912 MiB free. The Compose form needed a correction — see **R6**.
- [x] **0.3 Verify the uncertain pins.** All seven service images resolve via `docker manifest
      inspect`, **including the TEI `86-1.9.4` tag that was only inferred**. Two corrections: the
      llama.cpp image tag scheme does not track GitHub releases (see the pins table), and the Qwen
      GGUF was confirmed byte-exact at 5,966,095,584 bytes.
- [x] **0.4 Record the pipeline parity target** in `data/reference/parity-target.txt` — 50,940
      sections, 13,520,730 tokens, ~141 sections/s, plus the sha256 of the on-disk sections JSONL
      (`d9217ad9d9cc…ca0f57`) so Phase 4 diffs against a file of known integrity.

**Validation** — run, passed:

```bash
docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi
```

Reported `NVIDIA GeForce RTX 3080 Laptop GPU`, 64 MiB / 16384 MiB used, driver 595.91.07,
CUDA 13.2. Every pin either resolved or was corrected and then resolved; no pin is left unverified.

---

## Phase 1 — Scaffolding

- [x] **1.1 Create the directory skeleton** — `containers/{pipeline,caddy,authelia,lldap,db/initdb}`,
      `secrets/.gitkeep`, `data/snapshots/`, `data/cache/.gitkeep`. Confirmed via `git check-ignore`
      that `secrets/` and `data/cache/*` are ignored while their `.gitkeep` files are not.
- [x] **1.2 Write `.env.example`** — every variable commented with why it exists, not just what it
      is. Image pins deliberately **not** in `.env`: they live in `compose.yaml` so the versions in
      use are version-controlled and cannot drift per machine.
- [x] **1.3 Generate secrets** via `containers/gen-secrets.sh` — idempotent (existing values are
      reported as `keep`, never rotated, since rotating the storage encryption key would make
      existing Authelia rows unreadable). Seven secrets at exactly 64 chars (32 for the LDAP bind
      password), no trailing newline, `0600`, in a `0700` directory. One shared `ldap_admin_password`
      serves both LLDAP's admin account and Authelia's bind.
- [x] **1.4 Write `compose.yaml`** — `name: gcr`, two networks, six named volumes, shared logging
      anchor, and the `db` service complete. Services are added as their phase is validated rather
      than all at once, so everything in the committed file has been proven to come up.
- [x] **1.5 Amend `CLAUDE.md` and `README.md`** — done, including a container-first Setup section in
      the README and the `docker compose run --rm pipeline …` command set in both:
  - `CLAUDE.md` "Not installed… `podman`, `postgresql` with `pgvector`, `caddy`" → the
    Docker/Compose/NVIDIA-toolkit reality, and "no host packages required".
  - `CLAUDE.md` "**Rootless Podman** with Quadlet systemd units" → Docker Compose with profiles,
    plus one line on why and what it trades away.
  - `CLAUDE.md` command block → add the `docker compose run --rm pipeline gcr …` forms alongside the
    `uv run gcr …` ones.
  - `README.md` status row "Podman/Quadlet, Caddy, Authelia, LLDAP | not started" → split into rows
    that can be ticked independently as the phases land.
  - `README.md` "Not yet installed on the development machine…" → same correction.

**Validation** — run, passed:

```bash
docker compose --profile core config
```

Resolves every variable with no warnings. Note the `--profile core`: without it the output is
`services: {}`, because every service sits behind a profile. A bare `docker compose config` therefore
validates nothing useful here, which is worth knowing before trusting it as a check.

---

## Phase 2 — Database tier

- [x] **2.1 Add the `db` service** on `pgvector/pgvector:0.8.6-pg18-trixie`, `pg_isready`
      healthcheck, `gcr_pgdata` volume. Healthy in ~5 s.
- [x] **2.2 `01-extensions.sql`** — `vector` 0.8.6, `pg_trgm` 1.6, `unaccent` 1.1. `unaccent` was
      added beyond the plan: the corpus is English-origin, but the organisation and place names in it
      are not (*Göteborg*, *Łódź*, *Côte*). Versions are logged at init so the migration proof can
      rule an extension-version difference in or out as an explanation for differing results.
- [x] **2.3 `02-schema.sql`** — `sections` (22 columns), `sections_translated` (22, built with `LIKE
      … INCLUDING GENERATED` so the tiers cannot drift apart), and `ingestion_runs` tying rows back
      to a manifest sha256 and a chunking/embed version. `00-authelia-db.sh` creates the `authelia`
      database and role for 7.2. Two `DOMAIN`s (`programme_period`, `iso_country`) carry the
      vocabularies as CHECKs over `text` rather than `ENUM` — cheaper to extend when 2035-2041
      arrives, and it keeps type OIDs out of the migration comparison.
- [x] **2.4 Add a minimal DB config surface** — `DATABASE_URL` in `src/gcr/config.py`, defaulting to
      the published loopback port so a host-side `uv run` needs no setup, with compose overriding it
      to the in-network form. Plus `SECTIONS_TABLE` / `SECTIONS_TRANSLATED_TABLE` constants so the
      two tiers cannot be confused in a query. Covered by `tests/test_config.py`.

**Validation** — run, passed. `vector` reports **0.8.6**. All four init scripts ran with no errors on
a fresh volume, and the schema was then exercised rather than merely parsed — the hard design rules
are enforced *in the database*, not just by convention in code:

| Attempted | Result |
|---|---|
| insert well-formed `english_origin` section | accepted |
| insert `machine_translated` into **core** | **rejected** (the Kohesio rule, in SQL) |
| insert `english_origin` into **translated tier** | **rejected** (mirror rule: nothing else hides there) |
| `country = 'ireland'` | **rejected** (ISO-2 upper only) |
| `programme_period = '2035-2041'` | **rejected** (extend the CHECK deliberately) |
| `source_url = NULL`, `fetch_date = NULL` | **rejected** (identity and dates are sacred) |
| blank text | **rejected** |
| duplicate `(source_system, source_id, ordinal)` | **rejected** (would double a section's retrieval weight) |
| `source_date = NULL` | accepted — some upstreams publish none, and it is never guessed |
| `vector` of 3 dimensions | **rejected**: `expected 1024 dimensions, not 3` |

Also confirmed: the generated `tsv` weights `part` as `B` and body as `C`
(`'fund':2C 'object':1B 'photon':4C`), stemming matches *funding* from *fund*, `access_group` defaults
to `public` in core and `restricted` in the translated tier, and **`docker compose down` then `up -d`
preserved all rows and the stored 1024-dim embedding** — the check that proves the corrected PGDATA
mount works. Test rows were then truncated. Host suite: **33 passed** (29 before this phase; the
plan's earlier figure of 32 was wrong), `ruff check` clean.

---

## Phase 3 — Pipeline image

- [x] **3.1 Write `containers/pipeline/Containerfile`** — `python:3.12-slim-trixie`, `uv` pinned to
      **0.11.11** (the version that generated the committed `uv.lock`, revision 3), project at `/app`,
      **editable** install, `HF_HOME=/opt/hf` on `gcr_hf_cache`, and a non-root user built from
      `HOST_UID`/`HOST_GID` build args.
- [x] **3.2 Two build targets** — `base` and `embed`. **`base` had to change from the plan**: it now
      installs a new `tokenize` extra (transformers without torch, a few MB) because the real bge-m3
      tokenizer turned out to be load-bearing for chunk boundaries, not just for reporting. See the
      run log.
- [x] **3.3 Add the `pipeline` service** — binds `./data:/app/data`, `./src:/app/src`, `./tests`,
      shares `hf_cache` with the model servers. No `depends_on`: `fetch`, `sections`, `manifest`,
      `pytest` and `ruff` need no database, and naming a dependency in another profile would force
      the `core` profile on for all of them.

**Validation** — run, passed:

```bash
docker compose --profile tools run --rm pipeline gcr --help                   # all four commands
docker compose --profile tools run --rm --entrypoint pytest pipeline -q       # 38 passed
docker compose --profile tools run --rm --entrypoint ruff pipeline check src tests
```

`REPO_ROOT` resolves to `/app` and `DATA_RAW` to `/app/data/raw`, confirming the editable install and
the `/app/data` mount satisfy `fetch.py`'s `relative_to(REPO_ROOT)`. The container and the host now
agree exactly on a sample slice — `gcr sections horizon --limit 100` gives **219 sections / 58,935
tokens / 18 countries** in both.

---

## Phase 4 — Parity gate

The step that makes everything after it trustworthy. If the container has silently altered the
corpus, nothing downstream means anything.

- [x] **4.1 Build sections in the container** — 50,940 sections in 71 s (host: 72 s).
- [x] **4.2 Compare to the baseline** — exactly **50,940 sections**, **13,520,730 tokens**, 265 mean
      tokens, 52 countries, 0 without country, 384 without date. Every figure matches.
- [x] **4.3 Re-run the embedding benchmark** in-container — **142.5 sections/s** at batch 32 against
      the host's 141.7, a 0.6% difference, and **peak VRAM 1.42 GB**, identical. Recorded in
      `data/reference/embed_benchmark_container.json`. CUDA reaches the container through the CDI
      reservation: torch 2.14.1+cu130 sees the RTX 3080 with 15.6 GB.
- [x] **4.4 Confirm `gcr fetch` works in-container** — both paths exercised. The skip path (HEAD plus
      manifest lookup) and, with `--force`, a real 36.9 MB download that goes through
      `dest.relative_to(REPO_ROOT)`, the trap that throws when the data mount is wrong. The manifest
      gained a correctly-formed record with `path` stored relative, the sha256 unchanged
      (`1496a16e…`, so upstream has not moved and the corpus is unaffected), and the downloaded file
      owned by `ninel:ninel` rather than root — confirming the UID mapping.

**Validation** — run, passed, at a stronger level than the plan required. The plan asked for matching
counts and matching IDs. After the `fetch_date` fix below, host and container output is **identical
byte for byte**:

```
735fd73b093117c377257299020ccc574b45943fd3a7db5b39602a4b373db033  parity-host.jsonl
735fd73b093117c377257299020ccc574b45943fd3a7db5b39602a4b373db033  parity-container.jsonl
```

Section IDs, text and token counts are also identical to the pre-containerisation baseline artefact
`data/interim/cordis-horizon-sections.jsonl`, row for row across all 50,940.

---

## Phase 5 — Model tier

- [x] **5.0 Risk spike first (R1).** Stand up `llm` alone, load the Qwen GGUF, disable thinking, and
      run a handful of grounded-answer prompts. Judge **coherence**, not just HTTP 200 — GDN bugs
      manifest as plausible-looking gibberish or instant EOS. If it fails, switch to the plain-dense
      fallback and record the decision here. **Nothing downstream is built until this passes.**
- [x] **5.1 `tei-embed` serving `BAAI/bge-m3`**, weights on `gcr_hf_cache`, with **`--pooling cls`
      passed explicitly** — bge-m3 is CLS-pooled, and a silent fall-through to mean pooling degrades
      retrieval in a way that merely looks like a mediocre model.
- [x] **5.2 `tei-rerank` serving `BAAI/bge-reranker-v2-m3`** via TEI's native `/rerank` (there is no
      OpenAI-compatible rerank route), with a reduced `--max-batch-tokens`.
- [x] **5.3 Finalise `llm` flags** — `--host 0.0.0.0` (it binds loopback by default and would be
      unreachable in a container), `--ctx-size 16384`, `-ngl all`,
      `--cache-type-k q8_0 --cache-type-v q8_0`, thinking disabled, and a mounted GGUF rather than
      `-hf` so startup is offline and reproducible.
- [x] **5.4 Record the real model, quantisation and flags** in [`measurements.md`](measurements.md) —
      the report's bare "Qwen3.5-9B" is not enough to reproduce a run.
- [x] **5.5 Measure total VRAM** with all three resident, against 15.9 GB and the report's 9–12 GB
      estimate. This also settles the open question in `measurements.md` about whether the generation
      model can stay resident during bulk embedding.

**Validation** — run, passed. All four services healthy; full numbers in
[`measurements.md`](measurements.md).

- `tei-embed` `/v1/embeddings` returns 1024 dimensions; `tei-rerank` `/rerank` ranks the relevant
  text at 0.8314 and the two irrelevant ones at 0.0000.
- **VRAM: 8,732 MiB of 16,384 with all three resident** (llm 5,958 / embed 1,362 / rerank 1,330),
  leaving 7,244 MiB free — against the plan's 11–14 GB estimate and the report's 9–12 GB. R2 is far
  less tight than feared, and it settles the open question in `measurements.md`: **the generation
  model can stay resident during bulk embedding**, since embedding peaks at 1.42 GB.
- The check that actually matters — TEI versus local FlagEmbedding on identical input — gives
  **worst-case cosine 0.999988** against the 0.99 bar, across ASCII, numeric and non-ASCII text.
  That also confirms `--pooling cls` took effect; mean pooling would have shown here as a much
  lower cosine.

---

## Phase 6 — Load, index, and the blocked measurements

- [x] **6.1 Load the 50,940 Horizon sections** into `sections` with embeddings.
- [x] **6.2 Build the HNSW index and time it**; build the full-text index.
- [x] **6.3 Measure search latency** — vector-only, full-text-only, hybrid — at p50/p95 over a fixed
      query set, with and without the structured eligibility filter.
- [x] **6.4 Extrapolate** to 126,000 sections (Horizon + H2020) and to the 500,000 cap.
- [x] **6.5 Write the results into [`measurements.md`](measurements.md)** and state explicitly
      whether the 500,000-section cap can be relaxed. This is the question `CLAUDE.md` says "needs
      PostgreSQL and pgvector installed"; this is where it finally gets answered.

**Validation** — run, passed. `gcr search "hydrogen production and storage"` returns ranked CORDIS
projects, each with its project number, source URL and "as of" date attached. Full numbers are in
[`measurements.md`](measurements.md); the headline is:

| Measure | Result |
|---|---|
| Embed + load 50,940 sections | 5 min 52 s, with the generation model still resident |
| **HNSW build** | **8.9 s** (index 398 MB, table + indexes 835 MB) |
| Hybrid search p50 / p95 | 6.8 ms / 8.3 ms |
| Hybrid + country filter p95 | 26.1 ms |

**The 500,000-section cap can be relaxed.** It rested partly on embedding cost (already weakened) and
partly on unmeasured index and search cost. Both are now measured and neither binds: at 500,000 the
extrapolations are ~2 min to build the index and tens of milliseconds to search. The binding
constraint is disk, at roughly 16 GB per million sections against 374 GB free.

---

## Phase 7 — Identity tier

- [x] **7.1 `lldap`** with a bootstrap admin and the groups that map to access tiers, including the
      restricted tier the Kohesio rule requires for translated content. SQLite on a named volume —
      LLDAP supports Postgres, but its dataset is a handful of users, and SQLite avoids making the
      login chain depend on Postgres start-up ordering.
- [x] **7.2 `authelia`** with the LDAP backend and `_FILE` secrets, storing state in a **separate
      `authelia` database and role on the same instance** — one less container, one backup target.
      Accepted cost: a Postgres restart logs everyone out mid-session.
- [x] **7.3 Commit `*.example` templates only**; the real configs are gitignored already.

**Validation** — run, passed. Authelia migrated its schema into the shared PostgreSQL instance
(schema 0 → 29) on first start, confirming the separate-database design. A test user authenticates
through Authelia against LLDAP and the forwarded identity is correct:

```
Remote-User: alice     Remote-Groups: consultants
Remote-User: bob       Remote-Groups: consultants,restricted
```

Groups are created idempotently by `containers/bootstrap-identity.sh`, which also sets passwords.

---

## Phase 8 — Edge

- [x] **8.1 `caddy`** with a `Caddyfile` for `grants.localhost`, `tls internal`, `/data` on a named
      volume.
- [x] **8.2 `forward_auth`** to Authelia:
      `forward_auth authelia:9091 { uri /api/authz/forward-auth; copy_headers Remote-User Remote-Groups Remote-Email Remote-Name }`
- [x] **8.3 Set `trusted_proxies` and Authelia's `server.endpoints.authz` consistently** — on a
      Docker bridge network a mismatch makes identity-header spoofing live.
- [x] **8.4 Extract and trust the local CA (R3)**, and write the browser-import step into the runbook.
- [x] **8.5 Confirm no service except Caddy publishes a port.**

**Validation** — run, passed:

| Request | Result |
|---|---|
| unauthenticated `GET /` | **302** to `/authelia/?rd=…`, the login portal |
| unauthenticated `GET /about` | **200**, showing "© European Union" — public by design |
| unauthenticated `GET /authelia/` | **200**, or there would be nowhere to log in |
| authenticated `GET /` | **200**, with `Remote-User` / `Remote-Groups` forwarded |
| alice (consultants) `GET /restricted/x` | **403** |
| bob (consultants, restricted) `GET /restricted/x` | **200** |

Caddy obtained a certificate from its own local CA for `grants.localhost`.

---

## Phase 9 — Group-to-row-level access

- [x] **9.1 Map Authelia/LLDAP groups** to the `access_group` column added in 2.3.
- [x] **9.2 Enforce the filter in the query path, not in the prompt.** A model instruction is not an
      access control.

**Validation** — run, passed. A restricted-tier row was inserted, then queried as each group, in
every retrieval mode. Verified by querying, not by asking the model:

| Retrieval mode | `groups=[public]` | `groups=[public, restricted]` |
|---|---|---|
| full-text | withheld | visible |
| vector | withheld | visible |
| hybrid | withheld | visible |

And the default is closed: with **no groups supplied at all**, the restricted row is withheld rather
than everything being returned. `tests/test_access_filter.py` covers the clause builder (7 tests,
no database needed) so this cannot regress silently.

---

## Phase 10 — Migration-equivalence proof

A named Phase-1 deliverable. Containerisation makes it a more honest rehearsal than a host install
would: the "new data centre" is a genuinely separate volume and container.

- [x] **10.1 Freeze a snapshot** and `pg_dump` to `./data/snapshots/` (gitignored).
- [x] **10.2 Bring up `compose.proof.yaml`** — a second `db` on a **second, empty volume** — and
      restore into it.
- [x] **10.3 Run the fixed question set against both** and compare retrieved identifiers, rank
      overlap, and answer similarity.
- [x] **10.4 Commit the comparison** as an artefact.

**Validation** — run, passed. Artefact committed at `data/reference/migration-proof.txt`;
`containers/compare_retrieval.py` holds the question set and the criteria.

Data integrity, where exactness *is* required:

| | source | target |
|---|---|---|
| rows | 50,940 | 50,940 |
| embedded | 50,940 | 50,940 |
| indexes on `sections` | 13 | 13 |
| content checksum | `71e6b110…b19397` | `71e6b110…b19397` |

Retrieval, 12 questions × 3 modes, top 10:

| mode | ids match | order match | mean overlap | criterion |
|---|---|---|---|---|
| full-text | 12/12 | 12/12 | 1.0000 | exact — GIN is deterministic |
| vector | 11/12 | 11/12 | 0.9167 | ≥ 0.85 **and** one-sided hits are near-ties |
| hybrid | 12/12 | 11/12 | 0.9667 | ≥ 0.85 **and** one-sided hits are near-ties |

**VERDICT: EQUIVALENT.** The proof target was then destroyed and its volume removed; the source
still reports 50,940 rows and the same checksum.

---

## Phase 11 — Cleanliness audit and resumability

This phase delivers the goal that motivated the whole plan, so it is a real step, not a closing
remark.

- [x] **11.1 Rebuild from zero** on a scratch copy: `docker compose down -v`, then `up`, proving the
      stack comes back from repo + `.env` alone with no manual fixups.
- [x] **11.2 Diff the host against the Phase-0 baseline** — no new apt packages, nothing written
      outside `/var/lib/docker`, the repo, and the user's docker config. Record disk consumed by
      images and volumes against the 374 GB budget (note that `/var/lib/docker` shares a filesystem
      with the corpus).
- [x] **11.3 Document teardown** — `docker compose down -v`, named-volume removal, `docker image rm`
      by pin — and what a later Podman/Quadlet conversion would involve, including the `driver: cdi`
      block.
- [x] **11.4 Final commit.**

**Validation** — run, passed. Recorded in `data/reference/cleanliness-audit.txt`; teardown in
[`teardown.md`](teardown.md).

**The headline claim is verified rather than asserted: 2,406 apt packages before, 2,406 after,
identical sha256 over the sorted package list. Zero host packages added, removed or changed.**

From-zero rebuild: the stateful volumes (`pgdata`, `authelia_data`, `lldap_data`, `caddy_data`,
`caddy_config`) were destroyed and the stack rebuilt from the repository and `.env` alone, with no
manual fixups — all seven services healthy in ~15 s, schema and extensions recreated by initdb,
identity rebootstrapped by script, 50,940 rows reloaded, HNSW rebuilt in 9.1 s (8.9 s first time),
and the edge chain still giving 302 / 200 / 200. The model-weight volumes were deliberately kept,
since `containers/fetch-model.sh` is separately verified and re-downloading 14 GB proves nothing new.

Storage: free disk went 374 GB → 288 GB, of which **46.1 GB was Docker build cache** left behind by
building the `embed` image. That has since been reclaimed with `docker builder prune --all`, taking
free disk back to **324 GB** with running containers, volumes and images untouched. The project's
standing footprint is therefore **about 50 GB** — images, the model and corpus volumes, and the
repository. See [`teardown.md`](teardown.md).

---

## Definition of done

The stack is proven when all of these hold:

1. `docker compose --profile core --profile models --profile auth --profile edge up -d` brings
   everything to healthy from a clean machine.
2. `docker compose run --rm pipeline gcr sections horizon` reproduces **exactly 50,940 sections**
   with identical IDs.
3. `docker compose run --rm pipeline pytest` passes inside the container (38 tests).
4. A hybrid retrieval query returns ranked sections with source identifiers and dates attached.
5. An unauthenticated browser request is redirected to the Authelia portal; an authenticated one is
   served; and a restricted-tier row is withheld from a user outside its group.
6. The dump/restore proof shows equivalent retrieval on a second volume.
7. `apt list --installed` is unchanged from the Phase-0 baseline — **zero new host packages**.

---

## Run log

Newest last. One entry per working session: what was done, what was measured, what surprised us.

### 2026-10-01 — plan created

Established that Docker 29.1.3, Compose v2.40.3 and NVIDIA Container Toolkit 1.20.1 are already
installed on this machine, which removes the need for any host package install. Pins verified against
live sources. Two surprises worth recording:

- "Qwen3.5-9B" from the feasibility report is a real model, but it is a hybrid Gated DeltaNet + MoE
  multimodal thinking model, not the plain dense 9B the report's framing implies — hence R1 and the
  5.0 spike.
- pgvector on PostgreSQL 18 needs a version floor, not just a tag: 0.8.3 and 0.8.4 carry HNSW
  vacuum/corruption fixes that a re-ingested RAG store cannot do without.

### 2026-10-01 — Phase 0 complete

Baseline captured, GPU-in-container proven, all pins verified. Four things worth recording because
they contradict what was planned:

1. **Compose rejects the CDI syntax the plan specified.** `driver: cdi` + `device_ids` is refused
   with `missing property 'capabilities'`; `capabilities: [gpu]` is required alongside. Caught by
   actually running a probe service rather than trusting the snippet. Logged as R6.
2. **The llama.cpp image tag scheme does not follow its GitHub releases.** Releases are at `b11312`,
   but only a subset of builds get images: the highest `server-cuda-b*` on GHCR is **`b11206`**
   (540 such tags out of 12,000). The floating `server-cuda` tag resolves to a *third*, different
   digest — so "pin the build you tested" was right, but the build number to pin was wrong.
3. **The TEI `86-1.9.4` tag is real** — it had been inferred from a documented naming scheme rather
   than observed, and it checked out. So did `86-1.9` as a fallback.
4. **`docker image ls` shows 0 images** on a machine with 25 volumes from live projects, confirming
   R4's containerd-store switch. Benign for this plan; the other projects will re-pull.

The CDI spec lives at `/var/run/cdi/nvidia.yaml`, not `/etc/cdi`, and is regenerated per boot.

### 2026-10-01 — Phase 1 complete

Scaffolding, `.env.example`, the secret generator, `compose.yaml` with the `db` service, and the
`CLAUDE.md`/`README.md` amendments. Two bugs caught by validating rather than assuming:

1. **The first secret generator produced short secrets.** It base64-encoded exactly the target
   number of bytes, then stripped `=+/`, then truncated — so the output was always *under* the
   requested length. `authelia_storage_encryption_key` came out at **60 characters against Authelia's
   64-character minimum**, which would have failed in Phase 7 with an error that does not mention
   length. Now it over-generates in a loop and truncates down to an exact length.
2. **The PG18 image does not use `/var/lib/postgresql/data`.** It sets
   `PGDATA=/var/lib/postgresql/18/docker` and declares its `VOLUME` at `/var/lib/postgresql`. The
   conventional `pgdata:/var/lib/postgresql/data` mount would have persisted *nothing* — the real
   data directory would have landed in an anonymous volume, and `docker compose down -v` would have
   taken the corpus with it while appearing to have a named volume. `compose.yaml` mounts
   `pgdata:/var/lib/postgresql`.

Also worth recording: `docker compose config` with no `--profile` prints `services: {}` and exits 0,
because every service is behind a profile. As a validation step that is worthless; the profile must
be named.

### 2026-10-01 — Phase 2 complete

Database tier up and validated. The schema does not merely hold the mandatory fields — it *enforces*
them, so the hard design rules survive a careless loader:

- **The Kohesio rule is now a CHECK constraint on both sides.** `sections` rejects
  `machine_translated` and `sections_translated` rejects everything else, so translated text cannot
  reach the core corpus and nothing else can be parked in the restricted tier. Previously this was a
  convention that code was trusted to honour.
- `source_url`/`fetch_date`/`licence`/`attribution` are `NOT NULL`; `source_date` is nullable
  *deliberately*, since some upstreams publish none and it must never be guessed.
- `programme_period` and `iso_country` are `DOMAIN`s over `text` with CHECKs rather than `ENUM`s:
  easier to extend for 2028-2034 and 2035-2041, and it keeps type OIDs out of the migration
  comparison.
- `sections_translated` is built with `LIKE sections INCLUDING GENERATED`, so the two tiers cannot
  drift apart as columns are added. Verified: both are 22 columns with identical types.

All eleven constraint probes behaved (see the Phase 2 validation table). `unaccent` was added beyond
the plan — the corpus is English-origin but its organisation and place names are not.

The HNSW index is deliberately **not** in `03-indexes.sql`: building it on an empty table and then
inserting 50,000 rows is far slower than bulk-loading then building, and 6.2 needs to time that build
for the cap decision. It lives in `containers/db/hnsw.sql` instead.

Host test suite is **33 passed**, not the 32 the plan claimed — it was 29 before this phase and
`tests/test_config.py` added four.

### 2026-10-01 — Phase 3 complete, and the most important finding so far

The pipeline image works, but building it surfaced a defect that would have invalidated everything
downstream had Phase 4 not been designed to catch it.

**The container was silently building a different corpus from the host.** The first image had core
dependencies only, so `transformers` was absent, so `chunking._hf_tokenizer()` returned `None`, so
`count_tokens` fell back to the 4-characters-per-token heuristic — which `CLAUDE.md` records as
over-estimating by about 17%. The same sentence counted **9 tokens on the host and 10 in the
container**. Since token counts decide where chunks are cut, the container would have produced a
different number of sections, with different boundaries, and reported success while doing it. One
pre-existing chunking test (`test_tail_is_not_merged_when_it_would_breach_the_ceiling`) failed in the
container and passed on the host, which is what exposed it.

The fallback was deliberate and is documented in `chunking.py` as "degrade, not abort" — reasonable
for tests and lint, which must run without the GPU stack. It is not reasonable for a corpus that will
be embedded, compared, or cited. Three changes:

1. **New `tokenize` extra** in `pyproject.toml` — `transformers` *without* torch, a few MB rather
   than 2.5 GB. The base image installs it, so every image that can build sections has the real
   tokenizer.
2. **`chunking.require_real_tokenizer()`** turns the silent fallback into a loud error naming the fix,
   and `gcr sections` calls it before doing any work. `--allow-token-heuristic` opts out for a rough
   count that must never be embedded.
3. **`gcr sections` now prints `token counter` and `chunking version`** in the corpus profile, so a
   pasted run is self-describing and two runs that disagree on section count are explained by the
   first line rather than investigated from scratch.

`tests/test_tokenizer_guard.py` keeps the guard loud. The container now reports
`tokenizer: XLMRobertaTokenizer`, `count_tokens = 9`, identical to the host.

Smaller things: the `uv` image is pinned to 0.11.11 to match the `uv.lock` revision the host wrote;
`uv pip install pytest ruff` must come *after* `uv sync`, because `uv sync` prunes anything absent
from the lock; and `ARG` does not cross stage boundaries, so `HOST_UID`/`HOST_GID` are re-declared in
the `embed` stage. A test of mine was also environment-sensitive — it asserted the `DATABASE_URL`
default while compose sets that variable, so it passed on the host and failed in the container. It
now states the environment it wants.

### 2026-10-01 — Phase 4 complete: parity proven, and a second data-integrity bug found

The container reproduces the host corpus **byte for byte** — same sha256 over all 50,940 rows — and
embeds at 142.5 sections/s against the host's 141.7 with identical 1.42 GB peak VRAM. Everything
downstream can be trusted to be operating on the same corpus.

Getting there turned up a second defect, and this one was invisible to the counts.

**`fetch_date` recorded when sections were built, not when the source was fetched.** The first parity
run matched on every section ID and every character of text, yet the files differed — the only
divergent field, in all 50,940 rows, was `source.fetch_date`. `gcr sections` never passed a
`fetch_date` to `iter_sections`, so it defaulted to `datetime.now(UTC)`.

That is not cosmetic. `CLAUDE.md` makes fetch date sacred because it drives "as of" dates and
staleness warnings, so **a corpus rebuilt today from a two-year-old download would have reported
itself as fresh** — and the migration-equivalence proof in Phase 10 would have shown a difference on
every row for a reason that has nothing to do with migrating. The manifest already held the true
date, so `gcr sections` now reads it from there via `_source_fetch_date()`, falling back to `now()`
only when no record exists, which is the honest answer when there is no evidence of an earlier fetch.
`tests/test_fetch_date.py` covers all three cases.

Worth noting what caught it: not the section counts, which were already exact, but the decision to
compare file hashes rather than stop at "50,940 = 50,940". A parity gate that only counts rows would
have passed this straight through.

One consequence to be aware of: step 4.4 ran `gcr fetch --force`, so the manifest now has a second
record and later `sections` runs will carry that newer `fetch_date`. The payload sha256 is unchanged,
so the corpus text is unaffected.

### 2026-10-01 — Phase 5 complete: both big risks closed

**R1 is closed.** Qwen3.5-9B runs correctly on sm_86 at 16k context. It extracted a funding rate and
deadline from supplied context, **declined to invent a deadline the context did not contain**, and
produced 400 tokens of accurate sustained prose with no drift and no premature EOS. The known Gated
DeltaNet defects (sm_70 kernel crash, instant-EOS past ~130k context) did not appear, as hoped. This
remains a smoke test rather than an evaluation, and the plain-dense Qwen3-8B fallback stays on record.

**R2 is closed, and generously.** 8.5 GB resident of 16 GB, 7.2 GB free. Both the report (9–12 GB)
and this plan (11–14 GB) over-estimated. The practical consequence is recorded in `measurements.md`:
the report's advice to stop the chat model during bulk embedding is unnecessary.

**R5 was hit exactly as predicted, twice over, and the fix was the opposite of the advice.** The
guidance was that these slim images lack `curl`, so healthchecks should avoid it. Both images in fact
*have* `curl` — and what they lack is everything else: `wget`, `nc`, `python3`, and in llama.cpp's
case a `sh` that supports `/dev/tcp` (it is dash). The `/dev/tcp` healthcheck I wrote to avoid curl
therefore failed while the service was serving perfectly, reporting `unhealthy` against a `/health`
that returned `{"status":"ok"}`. Both now use `curl -fsS`. The TEI check was also weak in a way worth
noting: probing `--help` passes while weights are still downloading, so it would have reported healthy
on a service that could not answer.

**A new failure mode, R7: llama.cpp mangles `--flag=value`.** Its argument parser normalises
underscores to hyphens across the entire token, so
`--model=/models/Qwen3.5-9B-UD-Q4_K_XL.gguf` arrived as `...Q4-K-XL.gguf` and the server crash-looped
on a file that does not exist — while `docker compose config` showed the correct name and the file
was present under the correct name. Every flag for this service is now passed as two separate tokens.
TEI, being Rust/clap, is unaffected and keeps the `--flag=value` form.

Smaller things: `--chat-template-kwargs '{"enable_thinking":false}'` works but is deprecated in favour
of `--reasoning off`, which is what the service now uses. And `containers/fetch-model.sh` needed
`--user 0:0`, because a fresh named volume is root-owned while the curl image runs as uid 100 — the
failure surfaces as `curl: (23) client returned ERROR on write`, which reads like a network fault and
is a permission one.

### 2026-10-01 — Phase 6 complete: the cap question is answered, and filtered search was broken

The corpus is loaded, indexed and searchable, and the two measurements `CLAUDE.md` had blocked on
"needs PostgreSQL and pgvector installed" now exist. **HNSW builds in 8.9 seconds** over 50,940
vectors and hybrid search runs at 6.8 ms p50. Neither is anywhere near a constraint, so
**the 500,000-section cap is no longer justified by anything measured** — full reasoning and
extrapolations in [`measurements.md`](measurements.md).

Two defects found, one of them serious.

**Filtered vector search returned nothing at all.** HNSW fetches `ef_search` candidates and
PostgreSQL applies the WHERE clause afterwards, so a country filter discarded all forty candidates
and returned zero rows — for a query with 1,260 genuine matches. Since the structured eligibility
filter (country, NUTS, programme) is applied to essentially every real query, nearly all retrieval
would have come back empty, or near-empty, while looking perfectly healthy: no error, fast response,
just no results. The fix is pgvector 0.8.0's iterative index scans, set per statement in `gcr.db`.
It costs 1.2 ms → 9.5 ms p50 on filtered vector search, which is a trivial price for the difference
between "nothing" and "the right ten rows". It is also a concrete reason the ≥ 0.8 pin matters:
the feature does not exist before it.

What caught this was measuring *hit counts* alongside latency. A latency benchmark alone would have
reported filtered vector search as the fastest mode in the table and moved on.

**PostgreSQL's parallel HNSW build died on Docker's default `/dev/shm`.** The error names the wrong
resource entirely — `DiskFull: could not resize shared memory segment ... to 2144407072 bytes: No
space left on device` — on a machine with 370 GB free. Docker gives a container 64 MB of `/dev/shm`
by default and PostgreSQL puts parallel workers' shared memory there. `shm_size: 4gb` on the `db`
service fixes it.

Also added this phase, because Phase 6 could not run without them: `psycopg` as a core dependency,
`src/gcr/db.py` (COPY-based bulk load, full-text/vector/hybrid retrieval, HNSW management), and the
`load`, `build-index` and `search` CLI commands. Hybrid merging uses reciprocal rank fusion rather
than a weighted score sum, because `ts_rank_cd` and cosine similarity are not on comparable scales
and any fixed weighting between them would be a guess that quietly favours one half.

### 2026-10-01 — Phases 7, 8 and 9 complete: the login chain, and an access-control leak

LLDAP, Authelia and Caddy are up, the whole chain works, and `ss -ltnp` confirms the design holds:
**only Caddy's 80 and 443 are published**, plus the dev-only loopback PostgreSQL port. Authelia
migrated its schema into the shared PostgreSQL instance (0 → 29) on first start, so the
separate-database-same-instance choice works as intended.

**The important finding is an access-control leak that the obvious configuration contains.** Authelia
applies the *first* matching rule, and a `subject:` constraint does not deny a non-member — it simply
fails to match. So this, which reads correctly:

```yaml
- resources: ['^/restricted.*$']
  subject: ['group:restricted']
  policy: 'one_factor'
- subject: ['group:consultants']       # catch-all, no `resources:`
  policy: 'one_factor'
```

…grants `/restricted` to **any** consultant, because a non-member of `restricted` falls through to
the catch-all. Measured: alice, in `consultants` only, received **HTTP 200** on `/restricted`. An
explicit `policy: 'deny'` rule for the same resource, placed between the two, fixes it — alice now
gets 403 and bob, who is in both groups, still gets 200. A rule that looks redundant is load-bearing.

This is also the clearest argument for the belt-and-braces design: the HTTP layer decides whether a
request reaches the application, and the SQL `access_group` filter decides which rows it may see.
Phase 9 verified the second independently — a restricted row is withheld from `groups=[public]` in
**all three** retrieval modes and returned for `groups=[public, restricted]`, and with no groups
supplied at all the default is closed rather than open. Had only the HTTP rule existed, the leak
above would have exposed restricted content.

**A root container took ownership of repository files.** Authelia runs as root and `/config` was
mounted read-write, so it chowned `containers/authelia/` to `root:root` and subsequent edits failed
with `EACCES`. The mount is now `:ro`, with notifications redirected to a named volume. Worth
remembering for any other config directory handed to a container that runs as root.

**R3 confirmed as described.** Caddy issued its own certificate for `grants.localhost` but cannot
install its root CA from inside a container. `containers/trust-local-ca.sh` extracts it and installs
it into the system store; Firefox and Chrome on Linux keep separate stores and need a manual import,
which the script prints. The CA is on the `gcr_caddy_data` volume and survives a recreate but not
`down -v`.

### 2026-10-01 — Phases 10 and 11 complete: the plan is finished

**The migration-equivalence proof passes**, and getting there corrected a mistake in how the proof
itself was written. The first comparison demanded that every retrieval result match exactly and
reported `NOT EQUIVALENT` on 4 of 36 differences. That verdict was wrong: HNSW is an *approximate*
index, a restore rebuilds the graph with a different insertion order, and nearest-neighbour results
therefore differ at the cut-off even when the data is identical. Demanding exact equality tests the
index's determinism, not the migration.

The rewritten comparison splits the checks by what is genuinely deterministic — exact match for row
counts, index counts, full-text results and a content checksum over every
`(section_id, text, embedding)` tuple; a threshold plus a **near-tie test** for the approximate
modes. The near-tie test is what makes the threshold defensible: every section returned on one side
but not the other must exist on both and score within 0.02 of the last result that made the top ten,
which distinguishes ranking noise at the boundary from lost data. Result: identical checksums,
full-text 12/12 exact, vector 0.9167, hybrid 0.9667, **EQUIVALENT**.

**The cleanliness claim is verified, not asserted.** 2,406 apt packages before and after, identical
checksum over the sorted list. Everything this work added lives under `/var/lib/docker` or in the
repository.

The from-zero rebuild worked without a single manual fixup, which is the real test of whether the
plan's artefacts are complete. One number is worth flagging to whoever reads this next: of the 86 GB
consumed, **46 GB is Docker build cache** — reclaimable in one command and by far the easiest saving
available. (Since reclaimed: free disk is back to 324 GB and the standing footprint is ~50 GB.)

Two limits worth stating plainly rather than leaving implied. The latency and throughput figures
throughout are single-user, warm-cache, single-concurrency on one laptop GPU; they say nothing about
concurrent users. And the generation model passed a coherence smoke test, not an evaluation — the
~150-question evaluation set that Phase 1 calls for is still to come, and R1's fallback stays on
record until then.

---

## Follow-on: reranking and answer composition (2026-10-01)

Not part of the twelve phases above, but it completes the path they left half-wired and is recorded
here because it changed the compose file and found two faults in it.

The stack had the reranker and the generation model running, healthy and measured, and **nothing
called either**. `gcr ask` and `POST /ask` now close that: filter → hybrid → rerank → 6–10 sections →
answer with sources. Measured end to end, **12.9 s** for a question over the 50,940-section corpus.

### What it proves that the phases above could not

- **Caddy and Authelia now guard something real.** Unauthenticated `POST /ask` → **303** to the
  portal (303, not 302, because the request is a POST). Authenticated → an answer, with
  `Remote-Groups` feeding the SQL filter.
- **Row-level access works through a real request path**, not a test script. A restricted section was
  inserted and asked about by both users: alice (`consultants`) got "The retrieved sources do not
  state this"; bob (`consultants`, `restricted`) got the section and quoted its figure with a
  citation. This is the Phase 9 check again, now with Authelia supplying the identity.
- **The no-hallucinated-figures rule is enforced rather than requested.** Proven against real
  retrieved context by substituting a model reply that invents three figures: all three were caught
  and marked — `EUR 45,000,000`, `85%`, `3 March 2027`. Asked to express a contribution as a
  percentage of total cost, the model refused rather than calculating, which is what the prompt
  demands and the guard would have caught had it not.

### Two faults in the containerisation work, found by using it

1. **`tei-rerank` was configured smaller than retrieval needs.** `--max-client-batch-size=32` against
   `RETRIEVE_CANDIDATES=50` gave `HTTP 422: batch size 50 > maximum allowed batch size 32` — two of
   my own decisions in direct conflict, each defensible alone. Fixed on both sides: the flag is now
   64, and `services.rerank` batches regardless, so the breadth of retrieval is no longer coupled to
   a serving flag.
2. **A branch switch silently broke Caddy.** Checking out `main` while it was still at the
   pre-containerisation commit deleted `containers/` from the working tree; the fast-forward then
   recreated it as a *new inode*, leaving the running container's bind mount pointing at a deleted
   one. Caddy stayed up, reported `unhealthy`, and served 404 for every file. The healthcheck error
   named it precisely — `current working directory is outside of container mount namespace root` —
   but nothing else did. **Any long-running container with a bind mount into the repository needs
   `--force-recreate` after a branch switch that touches the mounted path.**

### Still open

The **~150-question evaluation set**. R1 stays open until it exists: Qwen3.5-9B has now answered
real questions well, refused correctly twice, and honoured "never calculate" — but that is a handful
of observations, not an evaluation, and the plain-dense fallback stays on record. The figure guard's
flags are deliberately countable so that the eval set can report a rate rather than an impression.
