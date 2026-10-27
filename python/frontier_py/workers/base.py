"""Worker adapter protocol and pre-call budget enforcement.

A worker turns a prompt into text plus an optional artifact body. Whatever
it says about its own correctness is data for calibration only; acceptance
is decided by verifiers (see `frontier_py.verifiers`).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .ledger import CampaignLedger

FinishReason = Literal["stop", "length", "latent_cap", "tool_cap", "timeout", "error"]


class WorkerUnavailable(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class Limits:
    max_output_tokens: int
    max_latent_steps: int
    max_tool_calls: int
    wall_seconds: float

    def __post_init__(self) -> None:
        if min(self.max_output_tokens, self.max_latent_steps, self.max_tool_calls) < 0:
            raise ValueError("limits must be non-negative")
        if not (self.wall_seconds > 0 and math.isfinite(self.wall_seconds)):
            raise ValueError("wall_seconds must be finite and > 0")


@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    limits: Limits
    seed: int
    model_revision: str


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    latent_steps: int = 0
    tool_calls: int = 0
    gpu_seconds: float = 0.0
    wall_seconds: float = 0.0
    usd: float = 0.0

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class GenerationResult:
    text: str
    artifact_body: dict[str, Any] | None
    usage: Usage
    finish_reason: FinishReason


@dataclass(frozen=True)
class Capabilities:
    name: str
    model: str
    model_revision: str
    latent_reasoning: bool
    tool_use: bool
    max_context_tokens: int


@dataclass(frozen=True)
class Availability:
    available: bool
    reasons: tuple[str, ...] = ()

    @property
    def reason(self) -> str:
        return "; ".join(self.reasons) if self.reasons else "available"


@dataclass(frozen=True)
class Charge:
    """Upper bound on what one call can cost."""

    tokens: int
    usd: float


class WorkerAdapter(ABC):
    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abstractmethod
    def probe(self) -> Availability:
        """Check local prerequisites without side effects (no downloads, no paid calls)."""

    @abstractmethod
    def max_charge(self, req: GenerationRequest) -> Charge:
        """Worst-case cost of `req`, used to refuse calls before they are made."""

    @abstractmethod
    def generate(self, req: GenerationRequest) -> GenerationResult: ...


@dataclass
class BudgetGuard:
    """Wraps an adapter; refuses any call whose worst case exceeds what is left.

    With a `ledger` (a `CampaignLedger`), every call is also reserved at its
    worst-case USD in the campaign's crash-safe ledger before it is made and
    settled with the actual USD afterwards. If the adapter raises, the
    reservation stays unsettled and keeps counting at its worst case (the
    call may still have been billed). Without a ledger the behaviour is
    exactly as before.
    """

    adapter: WorkerAdapter
    max_tokens: int
    max_usd: float
    spent_tokens: int = 0
    spent_usd: float = 0.0
    calls: int = 0
    refused: int = 0
    overruns: list[str] = field(default_factory=list)
    ledger: CampaignLedger | None = None

    def __post_init__(self) -> None:
        if self.max_tokens < 0 or not (self.max_usd >= 0 and math.isfinite(self.max_usd)):
            raise ValueError("budgets must be finite and non-negative")

    @property
    def remaining_tokens(self) -> int:
        return self.max_tokens - self.spent_tokens

    @property
    def remaining_usd(self) -> float:
        return self.max_usd - self.spent_usd

    def generate(self, req: GenerationRequest) -> GenerationResult:
        worst = self.adapter.max_charge(req)
        if worst.tokens > self.remaining_tokens or worst.usd > self.remaining_usd:
            self.refused += 1
            raise BudgetExceeded(
                f"worst case {worst.tokens} tokens / ${worst.usd:.6f} exceeds remaining "
                f"{self.remaining_tokens} tokens / ${self.remaining_usd:.6f}"
            )
        rid = None if self.ledger is None else self.ledger.reserve(worst.usd, label=f"call {self.calls + 1}")
        self.calls += 1
        result = self.adapter.generate(req)
        u = result.usage
        if self.ledger is not None and rid is not None:
            self.ledger.settle(rid, u.usd)
        # Charge what was actually used, even if the adapter's bound was wrong.
        self.spent_tokens += u.tokens
        self.spent_usd += u.usd
        if u.tokens > worst.tokens or u.usd > worst.usd:
            self.overruns.append(f"call {self.calls}: used {u.tokens} tokens / ${u.usd:.6f} > bound")
        return result
