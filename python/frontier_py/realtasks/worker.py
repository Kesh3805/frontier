"""Deterministic non-LLM worker: seeded program search over the DSL.

One attempt samples up to `MAX_SAMPLES` programs and submits the first that
reproduces every visible example; if none does, it submits the last sample.
The charge is deterministic: `BASE_UNITS + UNITS_PER_SAMPLE * samples`, so
failed searches cost more than quick successes. Everything is a function of
(task, seed, k): a policy making the k-th attempt on a task gets the same
candidate as any other policy would.
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any

from .dsl import compile_program, sample_program
from .suite import RealTask

MAX_SAMPLES = 256
BASE_UNITS = 0.05
UNITS_PER_SAMPLE = 0.01
PROBE_SAMPLES = 200


def _rng(*parts: object) -> random.Random:
    key = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return random.Random(int.from_bytes(key[:8], "little"))


def canon(x: Any) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"))


def run_program(source: str, xs: list[int]) -> tuple[bool, Any]:
    try:
        return True, compile_program(source)(list(xs))
    except Exception:  # noqa: BLE001 - any failure means "does not match"
        return False, None


def matches(source: str, cases: list[tuple[list[int], Any]]) -> bool:
    for xs, want in cases:
        ok, got = run_program(source, xs)
        if not ok or canon(got) != canon(want):
            return False
    return True


def attempt(task: RealTask, seed: int, k: int) -> dict[str, Any]:
    rng = _rng("attempt", task.name, seed, k)
    visible = list(task.visible)
    src = ""
    for i in range(1, MAX_SAMPLES + 1):
        src = sample_program(rng, task.kind)
        if matches(src, visible):
            return {"source": src, "samples": i, "visible_pass": True, "gen_units": round(BASE_UNITS + UNITS_PER_SAMPLE * i, 9)}
    return {"source": src, "samples": MAX_SAMPLES, "visible_pass": False,
            "gen_units": round(BASE_UNITS + UNITS_PER_SAMPLE * MAX_SAMPLES, 9)}


def probe_hint(task: RealTask) -> float:
    """Difficulty predictor: P(an attempt finds a visible-passing program),
    estimated from a fixed probe sample. It sees only the visible examples,
    so it cannot tell a program that overfits them from a correct one."""
    rng = _rng("probe", task.name)
    q = sum(matches(sample_program(rng, task.kind), list(task.visible)) for _ in range(PROBE_SAMPLES)) / PROBE_SAMPLES
    return min(max(1.0 - (1.0 - q) ** MAX_SAMPLES, 0.001), 0.999)
