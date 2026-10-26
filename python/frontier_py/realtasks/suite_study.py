"""How should a hidden test suite be built so that wrong programs are rejected?

    python -m frontier_py.realtasks.suite_study --out study.json

Program pool: for every live task, the distinct programs the worker submits
over `POOL_ATTEMPTS` attempts on a pool seed, keeping only those that
reproduce the visible examples (the ones a verifier actually has to judge),
each weighted by how often the worker produced it.

Reference truth for a program: agreement with the reference on a strong
suite, the union of every list over {-3..3} of length <= 4 (2,801 inputs)
and 5,000 random lists (length 0-20, values in [-100, 100]). Truth is
itself finite, which is a stated limitation.

For each candidate suite, the false-acceptance rate is the share of
truth-wrong programs that pass it, counted both per distinct program and
weighted by production frequency.
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
from pathlib import Path
from typing import Any, Callable

from .suite import SUITE, RealTask
from .worker import attempt, canon, matches, run_program

POOL_SEED = 424242
POOL_ATTEMPTS = 400


def exhaustive(values: range, max_len: int) -> list[list[int]]:
    return [list(t) for n in range(max_len + 1) for t in itertools.product(values, repeat=n)]


def random_lists(seed: int, n: int, lo: int, hi: int, max_len: int = 12) -> list[list[int]]:
    rng = random.Random(seed)
    return [[rng.randint(lo, hi) for _ in range(rng.randint(0, max_len))] for _ in range(n)]


SUITES: dict[str, Callable[[], list[list[int]]]] = {
    "random40_pm20 (current)": lambda: random_lists(1, 40, -20, 20),
    "random160_pm20": lambda: random_lists(2, 160, -20, 20),
    "random640_pm20": lambda: random_lists(3, 640, -20, 20),
    "random40_pm3": lambda: random_lists(4, 40, -3, 3),
    "random160_pm3": lambda: random_lists(5, 160, -3, 3),
    "exhaustive_pm2_len3 (156)": lambda: exhaustive(range(-2, 3), 3),
    "exhaustive_pm2_len3 + random40_pm20": lambda: exhaustive(range(-2, 3), 3) + random_lists(1, 40, -20, 20),
    # The extended check used as ground truth in exp-003/004 (same inputs).
    "extended1000_pm50 (exp-003 truth)": lambda: random_lists(777, 1000, -50, 50, max_len=20),
}


def truth_inputs() -> list[list[int]]:
    return exhaustive(range(-3, 4), 4) + random_lists(99, 5000, -100, 100, max_len=20)


def passes(source: str, task: RealTask, inputs: list[list[int]]) -> bool:
    for xs in inputs:
        ok, got = run_program(source, xs)
        if not ok or canon(got) != canon(task.reference(list(xs))):
            return False
    return True


def program_pool(task: RealTask) -> dict[str, int]:
    pool: dict[str, int] = {}
    for k in range(POOL_ATTEMPTS):
        src = attempt(task, POOL_SEED, k)["source"]
        if matches(src, list(task.visible)):
            pool[src] = pool.get(src, 0) + 1
    return pool


def study() -> dict[str, Any]:
    truth = truth_inputs()
    suites = {name: make() for name, make in SUITES.items()}
    wrong_total, wrong_weight = 0, 0
    passed = {name: [0, 0] for name in suites}
    per_task = {}
    for t in SUITE:
        if t.status not in ("solvable", "misleading"):
            continue
        pool = program_pool(t)
        wrong = {s: w for s, w in pool.items() if not passes(s, t, truth)}
        wrong_total += len(wrong)
        wrong_weight += sum(wrong.values())
        task_row = {"distinct_visible_passing": len(pool), "truth_wrong": len(wrong), "passes": {}}
        for name, inputs in suites.items():
            ok = {s: w for s, w in wrong.items() if passes(s, t, inputs)}
            passed[name][0] += len(ok)
            passed[name][1] += sum(ok.values())
            task_row["passes"][name] = len(ok)
        per_task[t.name] = task_row
    rates = {name: {"cases": len(suites[name]),
                    "false_accept_distinct": round(p[0] / wrong_total, 5) if wrong_total else None,
                    "false_accept_weighted": round(p[1] / wrong_weight, 5) if wrong_weight else None,
                    "wrong_programs_passing": p[0]}
             for name, p in passed.items()}
    return {"pool_seed": POOL_SEED, "pool_attempts": POOL_ATTEMPTS, "truth_inputs": len(truth),
            "wrong_programs": wrong_total, "wrong_weight": wrong_weight, "suites": rates, "per_task": per_task}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    res = study()
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, indent=1)
        f.write("\n")
    print(f"{res['wrong_programs']} truth-wrong visible-passing programs (weight {res['wrong_weight']})")
    for name, r in res["suites"].items():
        print(f"  {name:40s} cases={r['cases']:5d} FA distinct={r['false_accept_distinct']} weighted={r['false_accept_weighted']}")


if __name__ == "__main__":
    main()
