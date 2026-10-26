from __future__ import annotations

import bisect
import random

from . import Args, TaskDef


def reference(xs: list[int]) -> int:
    tails: list[int] = []
    for x in xs:
        i = bisect.bisect_left(tails, x)
        tails[i : i + 1] = [x]
    return len(tails)


def generate(rng: random.Random) -> list[Args]:
    cases: list[Args] = [[[]], [[1]], [[2, 2, 2]], [list(range(100))], [list(range(100, 0, -1))]]
    for _ in range(55):
        n = rng.randint(0, 300)
        hi = rng.choice([5, 1000])
        cases.append([[rng.randint(-hi, hi) for _ in range(n)]])
    return cases


TASK = TaskDef(
    name="lis_length",
    version="1",
    function_name="lis_length",
    statement="def lis_length(xs: list[int]) -> int: length of the longest strictly increasing subsequence of xs.",
    reference=reference,
    generate=generate,
    visible=(([[10, 9, 2, 5, 3, 7, 101, 18]], 4), ([[]], 0), ([[7, 7, 7]], 1)),
)
