"""Hosted-model adapter skeleton.

No provider is built in: the caller supplies a `Transport` (request dict and
API key in, response dict out). The API key is read only from the
environment variable named in config, at call time, and never stored. The
adapter refuses to exist without an explicit `max_usd` > 0, and every call
goes through a `BudgetGuard` sized from that cap using a conservative
worst case (prompt UTF-8 bytes as an upper bound on input tokens).
"""

from __future__ import annotations

import math
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .base import (
    Availability,
    BudgetGuard,
    Capabilities,
    Charge,
    GenerationRequest,
    GenerationResult,
    Usage,
    WorkerAdapter,
    WorkerUnavailable,
)

Transport = Callable[[dict[str, Any], str], dict[str, Any]]
_FINISH = {"stop", "length", "timeout", "error"}


@dataclass(frozen=True, kw_only=True)
class HostedConfig:
    provider: str
    model: str
    model_revision: str
    api_key_env: str
    max_usd: float
    max_tokens: int
    usd_per_input_token: float
    usd_per_output_token: float
    max_context_tokens: int

    def __post_init__(self) -> None:
        if not (isinstance(self.max_usd, (int, float)) and math.isfinite(self.max_usd) and self.max_usd > 0):
            raise ValueError("an explicit max_usd budget > 0 is required")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be > 0")
        if min(self.usd_per_input_token, self.usd_per_output_token) < 0:
            raise ValueError("prices must be non-negative")
        if not self.api_key_env:
            raise ValueError("api_key_env must name an environment variable")


class HostedAdapter(WorkerAdapter):
    def __init__(self, config: HostedConfig, transport: Transport) -> None:
        self.config = config
        self._transport = transport
        self.guard = BudgetGuard(_Raw(self), max_tokens=config.max_tokens, max_usd=config.max_usd)

    def capabilities(self) -> Capabilities:
        c = self.config
        return Capabilities(f"hosted:{c.provider}", c.model, c.model_revision, False, False, c.max_context_tokens)

    def probe(self) -> Availability:
        if not os.environ.get(self.config.api_key_env):
            return Availability(False, (f"environment variable {self.config.api_key_env} is not set",))
        return Availability(True)

    def max_charge(self, req: GenerationRequest) -> Charge:
        c = self.config
        tin, tout = len(req.prompt.encode("utf-8")), req.limits.max_output_tokens
        return Charge(tin + tout, tin * c.usd_per_input_token + tout * c.usd_per_output_token)

    def generate(self, req: GenerationRequest) -> GenerationResult:
        return self.guard.generate(req)

    def _call(self, req: GenerationRequest) -> GenerationResult:
        c = self.config
        if req.model_revision != c.model_revision:
            raise ValueError(f"request pins revision {req.model_revision}, adapter pins {c.model_revision}")
        key = os.environ.get(c.api_key_env)
        if not key:
            raise WorkerUnavailable(f"environment variable {c.api_key_env} is not set")
        payload = {
            "model": c.model,
            "revision": c.model_revision,
            "prompt": req.prompt,
            "max_output_tokens": req.limits.max_output_tokens,
            "seed": req.seed,
            "timeout_s": req.limits.wall_seconds,
        }
        t0 = time.monotonic()
        resp = self._transport(payload, key)
        wall = time.monotonic() - t0
        tin, tout = int(resp["input_tokens"]), int(resp["output_tokens"])
        finish = resp.get("finish_reason", "stop")
        body = resp.get("artifact_body")
        return GenerationResult(
            text=str(resp.get("text", "")),
            artifact_body=body if isinstance(body, dict) else None,
            usage=Usage(
                input_tokens=tin,
                output_tokens=tout,
                wall_seconds=wall,
                usd=tin * c.usd_per_input_token + tout * c.usd_per_output_token,
            ),
            finish_reason=finish if finish in _FINISH else "error",
        )


class _Raw(WorkerAdapter):
    """Unguarded view used by the adapter's own BudgetGuard."""

    def __init__(self, outer: HostedAdapter) -> None:
        self.outer = outer

    def capabilities(self) -> Capabilities:
        return self.outer.capabilities()

    def probe(self) -> Availability:
        return self.outer.probe()

    def max_charge(self, req: GenerationRequest) -> Charge:
        return self.outer.max_charge(req)

    def generate(self, req: GenerationRequest) -> GenerationResult:
        return self.outer._call(req)
