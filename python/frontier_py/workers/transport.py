"""Model transports: the only code that would ever talk to a provider.

A `Transport` turns one `TransportRequest` plus an API key into one
`TransportResponse`. This module ships only `FakeTransport`, which returns
deterministic canned replies for tests and for building pools from the DSL
worker. There is deliberately NO real HTTP transport in this repository
yet: connecting a provider needs the project owner's authorisation (see
docs/research/stage2-plan.md, phases 1 and 2). `HttpTransport` below marks
the interface such a transport must implement and refuses to run.

Rules for any future real transport:

* the API key is passed in per call by the caller, which reads it from an
  environment variable at call time; the transport must not store it, log
  it, put it in an exception message, or forward it anywhere but the
  provider's auth header;
* `task` and `j` are local metadata and must not be sent to the provider;
* usage must come from the provider's response, not be estimated.

The replay service (`realtasks.server --worker llm-pool`) never imports this
module: it has no transport and needs no key.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TransportRequest:
    provider: str
    model: str
    model_revision: str
    prompt: str
    temperature: float
    top_p: float
    max_output_tokens: int
    seed: int
    # Local metadata for fakes and bookkeeping; never sent to a provider.
    task: str = ""
    j: int = 0


@dataclass(frozen=True)
class TransportResponse:
    text: str
    input_tokens: int
    output_tokens: int
    finish_reason: str = "stop"
    response_model_id: str = ""
    provider_usd: float | None = None


@runtime_checkable
class Transport(Protocol):
    name: str

    def complete(self, request: TransportRequest, api_key: str) -> TransportResponse: ...


Canned = str | TransportResponse


def approx_tokens(text: str) -> int:
    """Deterministic token estimate for fakes: one token per 4 UTF-8 bytes, rounded up."""
    return (len(text.encode("utf-8")) + 3) // 4


@dataclass
class FakeTransport:
    """Deterministic canned replies; makes no network call.

    `responses` is either a mapping from `(task, j)` (or from `task`, for
    every j) to a reply, or a callable `(request) -> reply`. A reply that is
    a plain string gets usage from `approx_tokens`, with output tokens
    capped at the request's `max_output_tokens`. `usage_scale` multiplies
    the reported token counts (and lifts the cap) to simulate a provider
    that over-reports. `fail` raises the given exception on every call.
    The key a call receives is never stored; only whether one was given.
    """

    responses: Mapping[object, Canned] | Callable[[TransportRequest], Canned]
    usage_scale: float = 1.0
    fail: BaseException | None = None
    name: str = "fake"
    calls: list[tuple[str, int]] = field(default_factory=list)
    keyed_calls: int = 0

    def _reply(self, req: TransportRequest) -> Canned:
        if callable(self.responses):
            return self.responses(req)
        for k in ((req.task, req.j), req.task):
            if k in self.responses:
                return self.responses[k]
        raise KeyError(f"no canned reply for {req.task!r} j={req.j}")

    def complete(self, request: TransportRequest, api_key: str) -> TransportResponse:
        self.calls.append((request.task, request.j))
        self.keyed_calls += bool(api_key)
        if self.fail is not None:
            raise self.fail
        r = self._reply(request)
        if isinstance(r, TransportResponse):
            return r
        tin = approx_tokens(request.prompt)
        tout = approx_tokens(r)
        if self.usage_scale == 1.0:
            tout = min(tout, request.max_output_tokens)
        else:
            tin, tout = int(tin * self.usage_scale), int(tout * self.usage_scale) + 1
        digest = hashlib.sha256(r.encode("utf-8")).hexdigest()[:12]
        return TransportResponse(r, tin, tout, "stop", f"fake-{digest}")


class HttpTransport:
    """TODO(stage2 phase 1): a real provider transport.

    Not implemented on purpose. It needs an authorised provider, model and
    campaign cap from the project owner. Implement `complete` against the
    provider's API, obeying the rules in this module's docstring, and add
    the transport's name to `realtasks.pool.TRANSPORTS` only then.
    """

    name = "http"

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError("no real model transport exists yet: a provider call needs explicit authorisation")

    def complete(self, request: TransportRequest, api_key: str) -> TransportResponse:  # pragma: no cover
        raise NotImplementedError
