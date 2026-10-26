from __future__ import annotations

import random

from . import Args, TaskDef


def reference(xs: list[int]) -> list[int]:
    return sorted(xs)


def generate(rng: random.Random) -> list[Args]:
    cases: list[Args] = [[[]], [[0]], [[5, 5, 5]], [list(range(50, 0, -1))], [[-(2**40), 2**40, 0, -1]]]
    for _ in range(55):
        n = rng.randint(0, 200)
        hi = rng.choice([3, 100, 10**9])
        cases.append([[rng.randint(-hi, hi) for _ in range(n)]])
    return cases


TASK = TaskDef(
    name="sort_ints",
    version="1",
    function_name="sort_ints",
    statement="def sort_ints(xs: list[int]) -> list[int]: return the integers of xs in non-decreasing order.",
    reference=reference,
    generate=generate,
    visible=(([[3, 1, 2]], [1, 2, 3]), ([[]], []), ([[2, -1, 2]], [-1, 2, 2])),
)
