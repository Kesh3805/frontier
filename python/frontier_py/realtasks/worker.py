"""Deterministic non-LLM worker: seeded program search over the DSL.

One attempt samples up to `MAX_SAMPLES` programs and submits the first that
reproduces every visible example; if none does, it submits the last sample.
The charge is deterministic: `BASE_UNITS + UNITS_PER_SAMPLE * samples`, so
failed searches cost more than quick successes. Everything is a function of
(task, seed, k), plus the library for a dependent task: a policy making the
k-th attempt on a task gets the same candidate as any other policy would.

A dependent (catalog v3) task's attempt receives a library of verified
helpers, one per prerequisite. It samples from the helper-extended grammar
(`dsl.sample_program_h`), keeps only programs that call a helper, and
matches visible examples with the composed program. The search stream is
keyed by the helper names, not their sources, so policies that verified
different (equally valid) lemma programs still share the stream; the
sources decide only which sample first matches the examples. Library
sources are executed in-process like the worker's own DSL programs, which
is safe only because they are DSL programs this worker produced (see the
errata's known limitation before connecting a model-written worker).
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from .dsl import Helpers, Kind, compile_program, compose, sample_program, sample_program_h, uses_helper
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


@dataclass(frozen=True)
class LibEntry:
    """A verified helper available to a dependent task: its call name, the
    kind of value it returns, and the accepted artifact's full source."""

    name: str
    kind: Kind
    source: str


def _helpers(library: Sequence[LibEntry]) -> Helpers:
    return Helpers(ints=tuple(sorted(e.name for e in library if e.kind == "int")),
                   lists=tuple(sorted(e.name for e in library if e.kind == "list")))


def _sampler(task: RealTask, library: Sequence[LibEntry]) -> Callable[[random.Random], str | None]:
    """Without a library: the v1 sampler, unchanged. With one: the helper
    grammar, and a sample that calls no helper is discarded (returns None),
    because an attempt on a lemma route must build on its lemmas."""
    if not library:
        return lambda rng: sample_program(rng, task.kind)
    h = _helpers(library)

    def draw(rng: random.Random) -> str | None:
        src = sample_program_h(rng, task.kind, h)
        return src if uses_helper(src, h) else None

    return draw


def attempt(task: RealTask, seed: int, k: int, library: Sequence[LibEntry] = ()) -> dict[str, Any]:
    """One search attempt. The returned `source` is the candidate alone; the
    program that is verified is `compose(library, source)`, built by the
    caller from accepted artifacts. Deterministic in (task, seed, k, library):
    the stream is keyed by the helper names, matching uses their sources."""
    lib = sorted(library, key=lambda e: e.name)
    rng = _rng("attempt", task.name, seed, k, *(["lib", *(e.name for e in lib)] if lib else []))
    pairs = [(e.name, e.source) for e in lib]
    draw = _sampler(task, lib)
    visible = list(task.visible)
    src = ""
    for i in range(1, MAX_SAMPLES + 1):
        s = draw(rng)
        if s is None:
            continue
        src = s
        if matches(compose(pairs, src) if pairs else src, visible):
            return {"source": src, "samples": i, "visible_pass": True, "gen_units": round(BASE_UNITS + UNITS_PER_SAMPLE * i, 9)}
    return {"source": src, "samples": MAX_SAMPLES, "visible_pass": False,
            "gen_units": round(BASE_UNITS + UNITS_PER_SAMPLE * MAX_SAMPLES, 9)}


def probe_hint(task: RealTask, library: Sequence[LibEntry] = (), samples: int = PROBE_SAMPLES) -> float:
    """Difficulty predictor: P(an attempt finds a visible-passing program),
    estimated from a fixed probe sample. It sees only the visible examples,
    so it cannot tell a program that overfits them from a correct one."""
    rng = _rng("probe", task.name)
    lib = sorted(library, key=lambda e: e.name)
    pairs = [(e.name, e.source) for e in lib]
    draw = _sampler(task, lib)
    hits = 0
    for _ in range(samples):
        s = draw(rng)
        hits += s is not None and matches(compose(pairs, s) if pairs else s, list(task.visible))
    q = hits / samples
    return min(max(1.0 - (1.0 - q) ** MAX_SAMPLES, 0.001), 0.999)
