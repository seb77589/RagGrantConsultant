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
| 0 | Preflight and baseline | **done** | 2026-10-01 | |
| 1 | Scaffolding, `.env`, secrets, doc amendments | not started | | |
| 2 | Database tier (PostgreSQL + pgvector) | not started | | |
| 3 | Pipeline image | not started | | |
| 4 | Parity gate | not started | | |
| 5 | Model tier (embed, rerank, generate) | not started | | |
| 6 | Load, index, and the blocked measurements | not started | | |
| 7 | Identity tier (LLDAP, Authelia) | not started | | |
| 8 | Edge (Caddy, forward auth, TLS) | not started | | |
| 9 | Group-to-row-level access | not started | | |
| 10 | Migration-equivalence proof | not started | | |
| 11 | Cleanliness audit and resumability | not started | | |

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
│   ├── pipeline/Containerfile    # python:3.12-slim + uv + editable install
│   ├── caddy/Caddyfile
│   ├── authelia/configuration.yml.example
│   ├── lldap/lldap_config.toml.example
│   └── db/initdb/                # 01-extensions.sql, 02-schema.sql, 03-indexes.sql
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
| R1 | Qwen3.5-9B on llama.cpp | **open** |
| R2 | VRAM has no grace | **open** |
| R3 | Caddy local CA needs manual trust | **open** |
| R4 | Docker 29 containerd image store | **confirmed, benign here** — see below |
| R5 | Healthcheck false-negatives on first start | **open** |
| R6 | Compose CDI needs `capabilities: [gpu]` | **closed in 0.2** — see below |

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

- [ ] **1.1 Create the directory skeleton** — `containers/`, `secrets/.gitkeep`, and
      `data/cache/.gitkeep` (the gitignore names a `data/cache/.gitkeep` that does not exist on disk).
- [ ] **1.2 Write `.env.example`** with every variable commented, and generate a real `.env`.
- [ ] **1.3 Generate secrets** into `secrets/` using the `_FILE` convention Authelia documents as
      preferred: `…RESET_PASSWORD_JWT_SECRET_FILE`, `…SESSION_SECRET_FILE`,
      `…STORAGE_ENCRYPTION_KEY_FILE`, `…LDAP_PASSWORD_FILE`, `…STORAGE_POSTGRES_PASSWORD_FILE`; plus
      LLDAP's `LLDAP_JWT_SECRET`, `LLDAP_KEY_SEED`, `LLDAP_LDAP_USER_PASS`.
- [ ] **1.4 Write `compose.yaml`** — service skeleton, profiles, networks, named volumes.
- [ ] **1.5 Amend `CLAUDE.md` and `README.md`.** Leaving these stale is how the next session
      re-derives the wrong stack:
  - `CLAUDE.md` "Not installed… `podman`, `postgresql` with `pgvector`, `caddy`" → the
    Docker/Compose/NVIDIA-toolkit reality, and "no host packages required".
  - `CLAUDE.md` "**Rootless Podman** with Quadlet systemd units" → Docker Compose with profiles,
    plus one line on why and what it trades away.
  - `CLAUDE.md` command block → add the `docker compose run --rm pipeline gcr …` forms alongside the
    `uv run gcr …` ones.
  - `README.md` status row "Podman/Quadlet, Caddy, Authelia, LLDAP | not started" → split into rows
    that can be ticked independently as the phases land.
  - `README.md` "Not yet installed on the development machine…" → same correction.

**Validation**

```bash
docker compose config
```

Parses and resolves every variable with no warnings.

---

## Phase 2 — Database tier

- [ ] **2.1 Add the `db` service** on the pinned pgvector image, with a `pg_isready` healthcheck and
      the `gcr_pgdata` named volume.
- [ ] **2.2 `01-extensions.sql`** — `CREATE EXTENSION vector; CREATE EXTENSION pg_trgm;`
- [ ] **2.3 `02-schema.sql`** — the `sections` table carrying **every field the hard design rules
      make mandatory**: source identifier, source date, fetch date, country, NUTS region, programme
      period, origin, access group, chunking version — plus `vector(1024)` and a generated `tsvector`.
      The translated tier gets a **separate table**, per the Kohesio rule. Also create the `authelia`
      database and role for step 7.2.
- [ ] **2.4 Add a minimal DB config surface** to `src/gcr/config.py`, reading `DATABASE_URL` from the
      environment with a sane default. This is the first environment variable in the codebase — keep
      it to one.

**Validation**

```sql
SELECT extversion FROM pg_extension WHERE extname = 'vector';   -- expect 0.8.6
```

Schema applies cleanly on a fresh volume, and `docker compose down && docker compose up -d` preserves
the data.

---

## Phase 3 — Pipeline image

- [ ] **3.1 Write `containers/pipeline/Containerfile`** — `python:3.12-slim`, `uv`, project at
      `/app`, **editable** install, `HF_HOME` on `gcr_hf_cache`, and a non-root user whose UID matches
      the host so `./data` writes are not root-owned.
- [ ] **3.2 Two build targets** — `base` (core deps, CPU, fast) and `embed` (adds the `embed` extra,
      CUDA). Keeping the ~2.5 GB torch layer out of the default target keeps the dev loop quick.
- [ ] **3.3 Add the `pipeline` service** — binds `./data:/app/data` and `./src:/app/src`, GPU on the
      `embed` target, entrypoint `gcr`.

**Validation**

```bash
docker compose run --rm pipeline gcr --help          # lists fetch, sections, benchmark-embed, manifest
docker compose run --rm pipeline pytest              # full suite passes inside the container
docker compose run --rm pipeline ruff check src tests
```

---

## Phase 4 — Parity gate

The step that makes everything after it trustworthy. If the container has silently altered the
corpus, nothing downstream means anything.

- [ ] **4.1 Build sections in the container** against the already-downloaded zip.
- [ ] **4.2 Compare to the baseline** — exactly **50,940 sections** and **13,520,730 tokens**; diff
      section IDs against the existing `data/interim/cordis-horizon-sections.jsonl`; country profile
      unchanged.
- [ ] **4.3 Re-run the embedding benchmark** in-container and compare to ~141 sections/s and 1.42 GB
      peak VRAM.
- [ ] **4.4 Confirm `gcr fetch` works in-container** — this exercises the `relative_to(REPO_ROOT)`
      trap, which throws if the data mount is wrong.

**Validation**

Identical section and token counts, and identical IDs. **If they differ, stop and diagnose** — do not
proceed to embedding a corpus the container has changed. Throughput within ~15% is fine (container
overhead, thermal state); a larger gap must be explained before Phase 6.

---

## Phase 5 — Model tier

- [ ] **5.0 Risk spike first (R1).** Stand up `llm` alone, load the Qwen GGUF, disable thinking, and
      run a handful of grounded-answer prompts. Judge **coherence**, not just HTTP 200 — GDN bugs
      manifest as plausible-looking gibberish or instant EOS. If it fails, switch to the plain-dense
      fallback and record the decision here. **Nothing downstream is built until this passes.**
- [ ] **5.1 `tei-embed` serving `BAAI/bge-m3`**, weights on `gcr_hf_cache`, with **`--pooling cls`
      passed explicitly** — bge-m3 is CLS-pooled, and a silent fall-through to mean pooling degrades
      retrieval in a way that merely looks like a mediocre model.
- [ ] **5.2 `tei-rerank` serving `BAAI/bge-reranker-v2-m3`** via TEI's native `/rerank` (there is no
      OpenAI-compatible rerank route), with a reduced `--max-batch-tokens`.
- [ ] **5.3 Finalise `llm` flags** — `--host 0.0.0.0` (it binds loopback by default and would be
      unreachable in a container), `--ctx-size 16384`, `-ngl all`,
      `--cache-type-k q8_0 --cache-type-v q8_0`, thinking disabled, and a mounted GGUF rather than
      `-hf` so startup is offline and reproducible.
- [ ] **5.4 Record the real model, quantisation and flags** in [`measurements.md`](measurements.md) —
      the report's bare "Qwen3.5-9B" is not enough to reproduce a run.
- [ ] **5.5 Measure total VRAM** with all three resident, against 15.9 GB and the report's 9–12 GB
      estimate. This also settles the open question in `measurements.md` about whether the generation
      model can stay resident during bulk embedding.

**Validation**

Each endpoint answers a smoke request; `nvidia-smi` shows all three resident within budget; and — the
check that actually matters — embedding a known string through TEI gives a 1024-dim vector whose
cosine similarity to the local FlagEmbedding vector for the same string is **≥ 0.99**. If the two
embedding paths disagree, the index and the query encoder disagree, and retrieval degrades silently.

---

## Phase 6 — Load, index, and the blocked measurements

- [ ] **6.1 Load the 50,940 Horizon sections** into `sections` with embeddings.
- [ ] **6.2 Build the HNSW index and time it**; build the full-text index.
- [ ] **6.3 Measure search latency** — vector-only, full-text-only, hybrid — at p50/p95 over a fixed
      query set, with and without the structured eligibility filter.
- [ ] **6.4 Extrapolate** to 126,000 sections (Horizon + H2020) and to the 500,000 cap.
- [ ] **6.5 Write the results into [`measurements.md`](measurements.md)** and state explicitly
      whether the 500,000-section cap can be relaxed. This is the question `CLAUDE.md` says "needs
      PostgreSQL and pgvector installed"; this is where it finally gets answered.

**Validation**

A hybrid query returns plausible ranked sections with their source identifiers and dates attached,
and the measured numbers are committed to `measurements.md`.

---

## Phase 7 — Identity tier

- [ ] **7.1 `lldap`** with a bootstrap admin and the groups that map to access tiers, including the
      restricted tier the Kohesio rule requires for translated content. SQLite on a named volume —
      LLDAP supports Postgres, but its dataset is a handful of users, and SQLite avoids making the
      login chain depend on Postgres start-up ordering.
- [ ] **7.2 `authelia`** with the LDAP backend and `_FILE` secrets, storing state in a **separate
      `authelia` database and role on the same instance** — one less container, one backup target.
      Accepted cost: a Postgres restart logs everyone out mid-session.
- [ ] **7.3 Commit `*.example` templates only**; the real configs are gitignored already.

**Validation**

A test user authenticates against LLDAP through Authelia, and group membership is visible in the
forwarded headers.

---

## Phase 8 — Edge

- [ ] **8.1 `caddy`** with a `Caddyfile` for `grants.localhost`, `tls internal`, `/data` on a named
      volume.
- [ ] **8.2 `forward_auth`** to Authelia:
      `forward_auth authelia:9091 { uri /api/authz/forward-auth; copy_headers Remote-User Remote-Groups Remote-Email Remote-Name }`
- [ ] **8.3 Set `trusted_proxies` and Authelia's `server.endpoints.authz` consistently** — on a
      Docker bridge network a mismatch makes identity-header spoofing live.
- [ ] **8.4 Extract and trust the local CA (R3)**, and write the browser-import step into the runbook.
- [ ] **8.5 Confirm no service except Caddy publishes a port.**

**Validation**

An unauthenticated request is redirected to the portal; an authenticated one passes through with
identity headers; `ss -ltnp` shows only Caddy's ports plus the dev-only loopback Postgres port.

---

## Phase 9 — Group-to-row-level access

- [ ] **9.1 Map Authelia/LLDAP groups** to the `access_group` column added in 2.3.
- [ ] **9.2 Enforce the filter in the query path, not in the prompt.** A model instruction is not an
      access control.

**Validation**

A user outside the restricted group cannot retrieve a restricted-tier row — verified by querying as
that user, not by asking the model.

---

## Phase 10 — Migration-equivalence proof

A named Phase-1 deliverable. Containerisation makes it a more honest rehearsal than a host install
would: the "new data centre" is a genuinely separate volume and container.

- [ ] **10.1 Freeze a snapshot** and `pg_dump` to `./data/snapshots/` (gitignored).
- [ ] **10.2 Bring up `compose.proof.yaml`** — a second `db` on a **second, empty volume** — and
      restore into it.
- [ ] **10.3 Run the fixed question set against both** and compare retrieved identifiers, rank
      overlap, and answer similarity.
- [ ] **10.4 Commit the comparison** as an artefact.

**Validation**

Identifier sets identical, rank overlap at the stated threshold, any differences explained. Then
destroy the proof volume and confirm the primary is untouched.

---

## Phase 11 — Cleanliness audit and resumability

This phase delivers the goal that motivated the whole plan, so it is a real step, not a closing
remark.

- [ ] **11.1 Rebuild from zero** on a scratch copy: `docker compose down -v`, then `up`, proving the
      stack comes back from repo + `.env` alone with no manual fixups.
- [ ] **11.2 Diff the host against the Phase-0 baseline** — no new apt packages, nothing written
      outside `/var/lib/docker`, the repo, and the user's docker config. Record disk consumed by
      images and volumes against the 374 GB budget (note that `/var/lib/docker` shares a filesystem
      with the corpus).
- [ ] **11.3 Document teardown** — `docker compose down -v`, named-volume removal, `docker image rm`
      by pin — and what a later Podman/Quadlet conversion would involve, including the `driver: cdi`
      block.
- [ ] **11.4 Final commit.**

**Validation**

The host diff is empty apart from Docker-owned storage, and a from-scratch `up` succeeds.

---

## Definition of done

The stack is proven when all of these hold:

1. `docker compose --profile core --profile models --profile auth --profile edge up -d` brings
   everything to healthy from a clean machine.
2. `docker compose run --rm pipeline gcr sections horizon` reproduces **exactly 50,940 sections**
   with identical IDs.
3. `docker compose run --rm pipeline pytest` passes inside the container.
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
