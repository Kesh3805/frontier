"""Pilot task suite: real algorithm tasks with a frozen hidden test suite.

Every task asks for `def f(xs)` over a list of ints. Status labels are
ground truth by construction and are never shown to the scheduler:

* `solvable`: the reference is expressible in the worker's DSL, so some
  program the worker can sample passes every test.
* `inexpressible`: the reference needs operations the DSL lacks; dead for
  this worker (another worker might solve it).
* `misspecified`: the statement and visible examples describe one function
  but the hidden tests check a different one; dead for every worker, and
  the visible examples give no warning.
* `misleading`: the visible examples contradict each other, so a worker
  guided by them cannot use them, but the verifier checks the reference
  (which is well defined), so the task is alive: a correct program can still
  be submitted blind. (First labelled "contradictory" and assumed dead;
  calibration showed p > 0 before any experiment, and it was relabelled.)
"""

from __future__ import annotations

import hashlib
import itertools
import random
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Literal

from ..tasks import TaskDef
from .dsl import Kind

Status = Literal["solvable", "inexpressible", "misspecified", "misleading"]
DEAD: frozenset[str] = frozenset({"inexpressible", "misspecified"})
SUITE_VERSION = "1"  # default hidden-suite version (v1 kept for reproducing exp-003/004)
SUITE_VERSIONS = ("1", "2")
HIDDEN_SEED = 20261026  # frozen hidden test suite


def _gen_lists(rng: random.Random) -> list[list[Any]]:
    cases: list[list[Any]] = [[[]], [[0]], [[5]], [[-3]], [[1, 2, 3]], [[3, -1, 2, -7, 0]]]
    for _ in range(34):
        n = rng.randint(0, 12)
        cases.append([[rng.randint(-20, 20) for _ in range(n)]])
    return cases


def _gen_lists_v2(rng: random.Random) -> list[list[Any]]:
    """v2 = every list over {-2..2} of length <= 3 (156 inputs), then the v1
    random cases. Added after exp-005 found boundary bugs that v1 accepts."""
    small = [[list(t)] for n in range(4) for t in itertools.product(range(-2, 3), repeat=n)]
    return small + _gen_lists(rng)


GENERATORS = {"1": _gen_lists, "2": _gen_lists_v2}


def _stable_hash(xs: list[int]) -> int:
    return int.from_bytes(hashlib.sha256(repr(xs).encode()).digest()[:4], "little")


@dataclass(frozen=True)
class RealTask:
    name: str
    status: Status
    kind: Kind
    statement: str
    reference: Callable[[list[int]], Any]
    visible: tuple[tuple[list[int], Any], ...]

    def task_def(self, version: str = SUITE_VERSION) -> TaskDef:
        return TaskDef(
            name=f"pilot/{self.name}",
            version=version,
            function_name="f",
            statement=self.statement,
            reference=self.reference,
            generate=GENERATORS[version],
            visible=tuple(([xs], out) for xs, out in self.visible),
            per_call_timeout_s=2.0,
            wall_timeout_s=20.0,
        )


def _vis(ref: Callable[[list[int]], Any], *inputs: list[int]) -> tuple[tuple[list[int], Any], ...]:
    return tuple((xs, ref(xs)) for xs in inputs)


V = ([3, -1, 2], [4, 4, -6, 1], [0, 7])  # default visible inputs


def _t(name: str, status: Status, kind: Kind, statement: str, ref: Callable[[list[int]], Any], *inputs: list[int]) -> RealTask:
    return RealTask(name, status, kind, statement, ref, _vis(ref, *(inputs or V)))


def _second_largest(xs: list[int]) -> int:
    s = sorted(set(xs))
    return s[-2] if len(s) >= 2 else 0


def _mode(xs: list[int]) -> int:
    if not xs:
        return 0
    c = Counter(xs)
    return min(v for v, n in c.items() if n == max(c.values()))


def _product(xs: list[int]) -> int:
    p = 1
    for x in xs:
        p *= x
    return p


def _prefix(xs: list[int]) -> list[int]:
    out, s = [], 0
    for x in xs:
        s += x
        out.append(s)
    return out


def _noisy_sum(xs: list[int]) -> int:
    return sum(xs) + (_stable_hash(xs) % 3 if len(xs) > 6 else 0)


SUITE: tuple[RealTask, ...] = (
    # Solvable: expressible in the DSL, at varying depth.
    _t("sum", "solvable", "int", "Sum of the elements.", lambda xs: sum(xs)),
    _t("count", "solvable", "int", "Number of elements.", lambda xs: len(xs)),
    _t("max0", "solvable", "int", "Largest element, or 0 if empty.", lambda xs: max(xs, default=0)),
    _t("min0", "solvable", "int", "Smallest element, or 0 if empty.", lambda xs: min(xs, default=0)),
    _t("sum_squares", "solvable", "int", "Sum of squares.", lambda xs: sum(x * x for x in xs)),
    _t("count_positive", "solvable", "int", "Number of positive elements.", lambda xs: sum(1 for x in xs if x > 0)),
    _t("sum_even", "solvable", "int", "Sum of the even elements.", lambda xs: sum(x for x in xs if x % 2 == 0)),
    _t("reverse", "solvable", "list", "The list reversed.", lambda xs: xs[::-1]),
    _t("sort", "solvable", "list", "The list sorted ascending.", lambda xs: sorted(xs)),
    _t("sort_desc", "solvable", "list", "The list sorted descending.", lambda xs: sorted(xs)[::-1]),
    _t("double", "solvable", "list", "Every element doubled.", lambda xs: [2 * x for x in xs]),
    _t("positives", "solvable", "list", "The positive elements, in order.", lambda xs: [x for x in xs if x > 0]),
    _t("abs_all", "solvable", "list", "Absolute value of every element.", lambda xs: [abs(x) for x in xs]),
    _t("span", "solvable", "int", "Largest minus smallest element (0 if empty).", lambda xs: max(xs, default=0) - min(xs, default=0)),
    _t("sum_abs", "solvable", "int", "Sum of absolute values.", lambda xs: sum(abs(x) for x in xs)),
    _t("count_odd", "solvable", "int", "Number of odd elements.", lambda xs: sum(1 for x in xs if x % 2 == 1)),
    _t("first0", "solvable", "int", "First element, or 0 if empty.", lambda xs: xs[0] if xs else 0),
    _t("sum_plus_len", "solvable", "int", "Sum of the elements plus their count.", lambda xs: sum(xs) + len(xs)),
    _t("squares_of_positives", "solvable", "list", "Squares of the positive elements, in order.", lambda xs: [x * x for x in xs if x > 0]),
    _t("max_abs", "solvable", "int", "Largest absolute value (0 if empty).", lambda xs: max((abs(x) for x in xs), default=0)),
    _t("sum_negatives", "solvable", "int", "Sum of the negative elements.", lambda xs: sum(x for x in xs if x < 0)),
    _t("drop_first_sorted", "solvable", "list", "The sorted list without its smallest element.", lambda xs: sorted(xs)[1:]),
    _t("twice_sum_minus_max", "solvable", "int", "Twice the sum minus the largest element (0 if empty).", lambda xs: 2 * sum(xs) - max(xs, default=0)),
    _t("count_nonzero_even", "solvable", "int", "Number of even elements that are positive.", lambda xs: sum(1 for x in xs if x > 0 and x % 2 == 0)),
    # Inexpressible in the DSL: dead for this worker.
    _t("second_largest", "inexpressible", "int", "Second largest distinct element, or 0.", _second_largest),
    _t("product", "inexpressible", "int", "Product of the elements (1 if empty).", _product),
    _t("prefix_sums", "inexpressible", "list", "Running sums.", _prefix),
    _t("dedupe_sorted", "inexpressible", "list", "Distinct elements, ascending.", lambda xs: sorted(set(xs))),
    _t("mode", "inexpressible", "int", "Most frequent element (smallest on ties), or 0.", _mode),
    _t("count_above_7", "inexpressible", "int", "Number of elements greater than 7.", lambda xs: sum(1 for x in xs if x > 7)),
    # Misspecified: visible examples agree with the statement; hidden tests do not.
    _t("noisy_sum", "misspecified", "int", "Sum of the elements.", _noisy_sum),
    _t("hashed_bucket", "misspecified", "int", "Number of elements (as in the examples).",
       lambda xs: len(xs) if len(xs) < 4 else _stable_hash(xs) % 7, [1, 2], [5], [3, 3, 3]),
    # Misleading: contradictory visible examples over a well-defined reference.
    RealTask("contradictory_sum", "misleading", "int", "Sum of the elements.", lambda xs: sum(xs),
             (([1, 2], 3), ([1, 2], 4), ([5], 5))),
    RealTask("contradictory_sort", "misleading", "list", "The list sorted ascending.", lambda xs: sorted(xs),
             (([2, 1], [1, 2]), ([2, 1], [2, 1]), ([3], [3]))),
)

BY_NAME = {t.name: t for t in SUITE}
