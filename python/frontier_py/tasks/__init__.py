"""Frozen algorithm tasks held by the verifier.

Reference implementations and hidden-input generators live here, in the
verifier's process only. Candidates never receive this package: the child
interpreter runs with `-I -S` and a temporary cwd, so it is not importable
there (see `frontier_py.verifiers.property_tests` for what that does and does
not guarantee).
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

Args = list[Any]


@dataclass(frozen=True)
class TaskDef:
    name: str
    version: str
    function_name: str
    statement: str
    reference: Callable[..., Any]
    generate: Callable[[random.Random], list[Args]]
    visible: Sequence[tuple[Args, Any]]
    per_call_timeout_s: float = 2.0
    wall_timeout_s: float = 20.0
    memory_limit_mb: int = 512  # RLIMIT_AS counts reserved address space (thread stacks, malloc arenas)

    def hidden_inputs(self, seed: int) -> list[Args]:
        """Fresh hidden inputs; deterministic in (task, version, seed) on every platform."""
        key = hashlib.sha256(f"{self.name}|{self.version}|{seed}".encode()).digest()
        return self.generate(random.Random(int.from_bytes(key[:8], "little")))


def _registry() -> dict[str, TaskDef]:
    from . import gcd, lis_length, sort_ints

    return {t.name: t for t in (sort_ints.TASK, gcd.TASK, lis_length.TASK)}


TASKS: dict[str, TaskDef] = _registry()
