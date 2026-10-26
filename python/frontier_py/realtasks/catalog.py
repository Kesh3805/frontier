"""Build the pilot catalog consumed by the Rust runner.

    python -m frontier_py.realtasks.catalog --out ../research/realtasks/catalog-v1.json
    python -m frontier_py.realtasks.catalog --suite-version 2 --out ../research/realtasks/catalog-v2.json

Per task it records the statement, the probe hint, the ground-truth status
label, a commitment to the frozen hidden test suite (inputs and expected
outputs), and calibration estimates from `CALIBRATION_ATTEMPTS` worker
attempts on a calibration seed disjoint from experiment seeds:

* `p_hat`: fraction of attempts whose program is correct on the frozen
  hidden suite *and* an extended suite of 1,000 further inputs;
* `mean_gen_units`: mean deterministic charge per attempt.

These estimates feed only the diagnostic oracle policy and ground-truth
reporting; ordinary policies see the statement-level hint alone.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from ..receipt import canonical_digest
from .suite import DEAD, HIDDEN_SEED, SUITE, SUITE_VERSION, SUITE_VERSIONS, RealTask
from .worker import MAX_SAMPLES, attempt, canon, probe_hint, run_program

CATALOG_VERSION = "1"
CALIBRATION_SEED = 999_000_001
CALIBRATION_ATTEMPTS = 200
EXTENDED_SEED = 777


def hidden_cases(task: RealTask, version: str = SUITE_VERSION) -> list[tuple[list[int], Any]]:
    td = task.task_def(version)
    inputs = [list(a) for a, _ in td.visible] + td.hidden_inputs(HIDDEN_SEED)
    return [(a[0], task.reference(list(a[0]))) for a in inputs]


def extended_cases(task: RealTask, n: int = 1000) -> list[tuple[list[int], Any]]:
    rng = random.Random(EXTENDED_SEED)
    out = []
    for _ in range(n):
        xs = [rng.randint(-50, 50) for _ in range(rng.randint(0, 20))]
        out.append((xs, task.reference(list(xs))))
    return out


def correct_on(source: str, cases: list[tuple[list[int], Any]]) -> bool:
    for xs, want in cases:
        ok, got = run_program(source, xs)
        if not ok or canon(got) != canon(want):
            return False
    return True


def build(version: str = SUITE_VERSION) -> dict[str, Any]:
    entries = []
    for t in SUITE:
        hidden, extended = hidden_cases(t, version), extended_cases(t)
        n_ok = n_hidden_ok = 0
        units = 0.0
        for k in range(CALIBRATION_ATTEMPTS):
            a = attempt(t, CALIBRATION_SEED, k)
            units += a["gen_units"]
            if correct_on(a["source"], hidden):
                n_hidden_ok += 1
                n_ok += correct_on(a["source"], extended)
        entries.append({
            "name": t.name,
            "problem_id": f"pilot.{t.name}",
            "statement": t.statement,
            "kind": t.kind,
            "status": t.status,
            "dead": t.status in DEAD,
            "hint": round(probe_hint(t), 6),
            "criterion_sha256": canonical_digest({"suite": version, "task": t.name, "hidden_seed": HIDDEN_SEED,
                                                  "cases": [[xs, want] for xs, want in hidden]}),
            "p_hat": n_ok / CALIBRATION_ATTEMPTS,
            "p_hat_hidden_only": n_hidden_ok / CALIBRATION_ATTEMPTS,
            "mean_gen_units": round(units / CALIBRATION_ATTEMPTS, 6),
        })
    return {
        "catalog_version": CATALOG_VERSION,
        "suite_version": version,
        "hidden_seed": HIDDEN_SEED,
        "worker": {"max_samples": MAX_SAMPLES, "calibration_seed": CALIBRATION_SEED, "calibration_attempts": CALIBRATION_ATTEMPTS},
        "tasks": entries,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--suite-version", default=SUITE_VERSION, choices=SUITE_VERSIONS)
    a = p.parse_args()
    cat = build(a.suite_version)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cat, f, indent=1)
        f.write("\n")
    for e in cat["tasks"]:
        print(f"{e['status']:14s} {e['name']:22s} hint={e['hint']:.3f} p_hat={e['p_hat']:.3f} "
              f"(hidden-only {e['p_hat_hidden_only']:.3f}) units={e['mean_gen_units']:.2f}")


if __name__ == "__main__":
    main()
