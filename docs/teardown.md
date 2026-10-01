# Teardown and storage

How to give the machine its disk back, and what a later move to Podman would
involve. Companion to [`containerisation-plan.md`](containerisation-plan.md).

## What this project put on the machine

**No apt packages.** Verified: 2,406 packages before the work and 2,406 after,
with an identical checksum over the sorted package list. Docker, Compose and
the NVIDIA Container Toolkit were already installed and were not modified.

Everything else is Docker-owned storage under `/var/lib/docker`, plus the
repository itself.

| What | Size | Notes |
|---|---|---|
| `gcr-pipeline:embed` image | 20 GB | torch and its bundled CUDA libraries |
| TEI image | 8.2 GB | shared by `tei-embed` and `tei-rerank` |
| llama.cpp server image | 7.0 GB | |
| `gcr_hf_cache` volume | 8.5 GB | bge-m3 and the reranker, shared with the pipeline |
| `gcr_models` volume | 5.6 GB | the Qwen GGUF |
| `gcr_pgdata` volume | 1.6 GB | 50,940 sections, embeddings and indexes |
| `gcr-pipeline:base` image | 674 MB | |
| pgvector image | 651 MB | |
| Caddy, Authelia, LLDAP images | ~300 MB | |
| small volumes (`caddy_data`, `lldap_data`, `authelia_data`) | < 1 MB | |
| repository working tree | 555 MB | includes the gitignored CORDIS zip and snapshots |
| Docker build cache | 0 GB | 46.1 GB was reclaimed on 2026-10-01 — see below |

Free disk went from 374 GB before any of this work to **324 GB** after the build
cache was reclaimed, so the project's standing footprint is **about 50 GB**.

### The build cache has already been reclaimed

Building the `embed` target left 46.1 GB of build cache, kept only to make
rebuilds fast. It was reclaimed with:

```bash
docker builder prune --all --force
```

Free disk went 288 GB → 324 GB. Running containers, volumes and images are all
untouched by this; the only cost is that the next `docker compose build` of the
pipeline image starts from scratch and re-downloads the torch wheels.

Note this command is **global**, not per-project: it also discards build cache
for anything else built on this machine. Nothing breaks, builds are just slower.
Worth re-running after any future image rebuild, since the cache comes back.

## Teardown, least to most destructive

### Stop the stack, keep everything

```bash
docker compose --profile core --profile models --profile auth --profile edge down
```

Containers and networks go; all volumes survive. `up -d` brings it back in
about fifteen seconds.

### Drop the state, keep the weights

Destroys the corpus, users and certificates while keeping the ~14 GB of model
weights that are slow to re-download:

```bash
docker compose --profile core --profile models --profile auth --profile edge down
docker volume rm gcr_pgdata gcr_authelia_data gcr_lldap_data gcr_caddy_data gcr_caddy_config
```

Rebuild — this exact sequence was run and verified:

```bash
docker compose --profile core --profile models --profile auth --profile edge up -d
./containers/bootstrap-identity.sh alice '<password>'
docker compose run --rm pipeline gcr load horizon     # PIPELINE_TARGET=embed
docker compose run --rm pipeline gcr build-index
./containers/trust-local-ca.sh --install              # the CA is regenerated
```

Roughly seven minutes, almost all of it embedding.

### Remove everything this project created

```bash
docker compose --profile core --profile models --profile auth --profile edge --profile tools down
docker volume rm $(docker volume ls -q --filter name='^gcr_')
docker image rm gcr-pipeline:base gcr-pipeline:embed \
  pgvector/pgvector:0.8.6-pg18-trixie \
  ghcr.io/huggingface/text-embeddings-inference:86-1.9.4 \
  ghcr.io/ggml-org/llama.cpp:server-cuda-b11206 \
  ghcr.io/authelia/authelia:4.39.28 lldap/lldap:v0.6.3 caddy:2.11.4-alpine
docker builder prune --all
```

Then, if the local CA was installed into the system trust store:

```bash
sudo rm /usr/local/share/ca-certificates/caddy-gcr-local-ca.crt
sudo update-ca-certificates --fresh
```

and remove the certificate from the browser's own authority store, which is
separate.

Finally, the repository's gitignored payloads, if the corpus is not wanted:

```bash
rm -rf data/raw/* data/interim/* data/processed/* data/snapshots/*
```

At that point the machine is back to its Phase 0 state. `.env` and `secrets/`
are gitignored and can be deleted too; `./containers/gen-secrets.sh` regenerates
them, though a new storage encryption key makes any surviving Authelia rows
unreadable — which is only a problem if `gcr_pgdata` was kept.

## What a move to Podman would involve

The compose files avoid Docker-only features wherever that was free, so most of
this is mechanical:

- **`driver: cdi` in the GPU reservation blocks is the one real
  incompatibility.** podman-compose does not support it
  ([containers/podman#19338](https://github.com/containers/podman/issues/19338)).
  Rootless Podman wants `--device nvidia.com/gpu=0` or a CDI-aware equivalent.
- `shm_size: 4gb` on `db` is supported by Podman.
- Bind mounts of `./secrets` and `./containers/*` need `:z` or `:Z` on an
  SELinux host; Ubuntu uses AppArmor, so this does not arise here.
- The `pipeline` service runs as the host UID via build args. Rootless Podman
  maps UIDs differently, so that would become `--userns=keep-id` instead.
- `docker compose` would become `podman-compose`, or the services would be
  converted to Quadlet `.container` units — which is what the original design
  called for, and what `.gitignore` already anticipates with its
  `*.container`/`*.volume`/`*.network` rules.

Rootless Podman would also need the five apt packages this approach avoided:
`podman`, `uidmap`, `slirp4netns`, `passt`, `fuse-overlayfs`.
