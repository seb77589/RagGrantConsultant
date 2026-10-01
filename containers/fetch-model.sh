#!/usr/bin/env bash
#
# Download the generation model's GGUF into the gcr_models volume.
#
# Deliberately a separate step rather than llama.cpp's `-hf` auto-download:
#   * the server then starts offline and reproducibly, with no network call on
#     every boot and no dependency on HuggingFace being reachable;
#   * `-hf` also pulls the multimodal projector for this model, which is
#     several hundred MB we have no use for -- the stack is text-only;
#   * the file is checked once, here, instead of silently re-resolving a tag.
#
# Idempotent: an existing file of the expected size is left alone.
#
#   ./containers/fetch-model.sh
#
set -euo pipefail

cd "$(dirname "$0")/.."

# shellcheck disable=SC1091
set -a; [[ -f .env ]] && . ./.env; set +a

REPO="${LLM_GGUF_REPO:-unsloth/Qwen3.5-9B-GGUF}"
FILE="${LLM_GGUF_FILE:-Qwen3.5-9B-UD-Q4_K_XL.gguf}"
VOLUME="${COMPOSE_PROJECT_NAME:-gcr}_models"
URL="https://huggingface.co/${REPO}/resolve/main/${FILE}"

# Verified against the HuggingFace API on 2026-10-01. A size mismatch means the
# upstream file moved, which is a thing to look at rather than paper over.
EXPECTED_BYTES=5966095584

docker volume create "$VOLUME" >/dev/null

existing=$(docker run --rm -v "$VOLUME":/models alpine:3.22 \
    stat -c %s "/models/${FILE}" 2>/dev/null || echo 0)

if [[ "$existing" == "$EXPECTED_BYTES" ]]; then
    echo "keep      ${FILE} already present at ${EXPECTED_BYTES} bytes"
    exit 0
fi

if [[ "$existing" != "0" ]]; then
    echo "warning   ${FILE} present but ${existing} bytes, expected ${EXPECTED_BYTES}"
    echo "          resuming the download"
fi

echo "fetching  ${REPO}/${FILE}"
echo "          $(numfmt --to=iec "$EXPECTED_BYTES" 2>/dev/null || echo "$EXPECTED_BYTES bytes") into volume ${VOLUME}"

# --continue-at - resumes a partial file rather than restarting 5.5 GB.
# --user 0:0 because a fresh named volume is root-owned, and the curl image
# otherwise runs as uid 100 and fails with "client returned ERROR on write"
# -- which reads like a network fault but is a permission one.
docker run --rm --user 0:0 -v "$VOLUME":/models curlimages/curl:8.18.0 \
    --location --fail --continue-at - --retry 3 --retry-delay 5 --no-progress-meter \
    --output "/models/${FILE}" "$URL"

actual=$(docker run --rm -v "$VOLUME":/models alpine:3.22 stat -c %s "/models/${FILE}")
if [[ "$actual" != "$EXPECTED_BYTES" ]]; then
    echo "FAILED    got ${actual} bytes, expected ${EXPECTED_BYTES}" >&2
    exit 1
fi

echo "ok        ${FILE} ${actual} bytes in volume ${VOLUME}"
