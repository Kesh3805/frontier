from __future__ import annotations

import math
import random

from . import Args, TaskDef


def reference(a: int, b: int) -> int:
    return math.gcd(a, b)


def generate(rng: random.Random) -> list[Args]:
    cases: list[Args] = [[0, 0], [0, 7], [7, 0], [1, 1], [2**61 - 1, 2**31 - 1], [10**30, 10**20 * 6]]
    for _ in range(54):
        g = rng.randint(1, 10**6)
        cases.append([g * rng.randint(0, 10**9), g * rng.randint(0, 10**9)])
    return cases


TASK = TaskDef(
    name="gcd",
    version="1",
    function_name="gcd",
    statement="def gcd(a: int, b: int) -> int: greatest common divisor of non-negative a and b; gcd(0, 0) == 0.",
    reference=reference,
    generate=generate,
    visible=(([12, 18], 6), ([7, 0], 7), ([17, 5], 1)),
)
