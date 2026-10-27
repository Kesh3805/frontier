"""Versioned rate card: tokens to compute units (CU) and to USD.

Replay must be deterministic, so the compute units charged for a recorded
model call are a pure function of the recorded token usage and a frozen,
versioned rate card, never of wall time or of whatever price the provider
reports at replay time. USD from the same card is the *expected* charge;
the provider's own reported cost, when it gives one, is recorded beside it
for reconciliation (stage2-plan.md, design decision 5).

All prices are assumptions until checked against the provider.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..receipt import canonical_digest

RATE_CARD_SCHEMA = "frontier.rate-card/1"
UNITS_DECIMALS = 9  # same rounding as the DSL worker's gen_units


def _tokens(usage: Any) -> tuple[int, int]:
    """(input_tokens, output_tokens) from a `Usage`, a mapping, or anything with those attributes."""
    if isinstance(usage, Mapping):
        tin, tout = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    else:
        tin, tout = getattr(usage, "input_tokens", 0), getattr(usage, "output_tokens", 0)
    for t in (tin, tout):
        if isinstance(t, bool) or not isinstance(t, int) or t < 0:
            raise ValueError(f"token counts must be non-negative integers, got {tin!r} / {tout!r}")
    return tin, tout


@dataclass(frozen=True)
class RateCard:
    version: str
    cu_per_input_token: float
    cu_per_output_token: float
    usd_per_input_token: float
    usd_per_output_token: float

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version:
            raise ValueError("a rate card needs a non-empty version")
        for name in ("cu_per_input_token", "cu_per_output_token", "usd_per_input_token", "usd_per_output_token"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
                raise ValueError(f"{name} must be finite and non-negative, got {v!r}")

    def cu(self, usage: Any) -> float:
        tin, tout = _tokens(usage)
        return round(tin * self.cu_per_input_token + tout * self.cu_per_output_token, UNITS_DECIMALS)

    def usd(self, usage: Any) -> float:
        tin, tout = _tokens(usage)
        return tin * self.usd_per_input_token + tout * self.usd_per_output_token

    def to_dict(self) -> dict[str, Any]:
        return {"schema": RATE_CARD_SCHEMA, **asdict(self)}

    def sha256(self) -> str:
        return canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> RateCard:
        if d.get("schema", RATE_CARD_SCHEMA) != RATE_CARD_SCHEMA:
            raise ValueError(f"unsupported rate card schema {d.get('schema')!r}")
        extra = set(d) - {"schema", "version", "cu_per_input_token", "cu_per_output_token", "usd_per_input_token", "usd_per_output_token"}
        if extra:
            raise ValueError(f"unknown rate card fields {sorted(extra)}")
        return cls(d["version"], d["cu_per_input_token"], d["cu_per_output_token"], d["usd_per_input_token"], d["usd_per_output_token"])

    @classmethod
    def load(cls, path: str | Path) -> RateCard:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
