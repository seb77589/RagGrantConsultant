"""HTTP endpoint for asking questions.

One route that matters, `POST /ask`. Its job is to turn an authenticated request
into the same call `gcr ask` makes, so there is exactly one answer path and not
two that drift.

**Where identity comes from.** Authelia authenticates, and Caddy's `forward_auth`
copies `Remote-User` and `Remote-Groups` onto the proxied request. Those groups go
straight into the SQL access filter. The service therefore trusts a header, which
is only sound because of how it is deployed: it publishes no port, and it sits on
the `edge` network solely so Caddy can reach it. Nothing else can. That is an
assumption about the deployment, not a property of this code, so it is stated
here rather than left implicit — if this service were ever published directly,
anyone could set `Remote-Groups: restricted`.

A missing `Remote-Groups` yields the public tier, because `db._filters` treats an
empty group list as "public only" rather than "no filter".
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .answer import as_dict, compose
from .config import RERANK_TOP_K
from .db import PUBLIC_GROUP, connect
from .retrieve import retrieve
from .services import ServiceUnavailable

app = FastAPI(
    title="Grant consultant",
    description="Retrieval-augmented answers over official EU funding sources.",
    docs_url=None,
    redoc_url=None,
)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    country: str | None = Field(default=None, max_length=2)
    programme_period: str | None = None
    top_k: int = Field(default=RERANK_TOP_K, ge=1, le=20)


def _groups(header: str | None) -> list[str]:
    """Access groups from the forwarded header, always including the public tier.

    Authelia sends a comma-separated list. An absent or empty header means an
    unauthenticated or group-less caller, who gets public rows only.
    """
    groups = [g.strip() for g in (header or "").split(",") if g.strip()]
    if PUBLIC_GROUP not in groups:
        groups.append(PUBLIC_GROUP)
    return groups


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness only. Deliberately does not touch the database or the model
    services: this answers "is the process up", and conflating that with "is the
    whole stack well" makes a healthcheck that flaps for reasons outside its
    control."""
    return {"status": "ok"}


@app.post("/ask")
def ask(
    request: AskRequest,
    remote_groups: Annotated[str | None, Header(alias="Remote-Groups")] = None,
    remote_user: Annotated[str | None, Header(alias="Remote-User")] = None,
) -> dict[str, object]:
    groups = _groups(remote_groups)
    try:
        with connect() as conn:
            hits = retrieve(
                conn,
                request.question,
                groups,
                request.country,
                request.programme_period,
                top_k=request.top_k,
            )
        answer = compose(request.question, hits)
    except ServiceUnavailable as exc:
        # 503 rather than 500: the stack is incomplete, not broken, and the
        # message names which service and at what address.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    payload = as_dict(answer)
    # Echoed back so a caller can see which identity the answer was filtered for.
    # Useful when a question returns less than someone expected.
    payload["user"] = remote_user
    payload["groups"] = groups
    return payload
