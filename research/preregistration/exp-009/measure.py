"""exp-009 part M: measured cost of verification, full execution vs early stop.

    python research/preregistration/exp-009/measure.py OUT_DIR

Builds the held-out candidate corpus (catalog v2 single-step tasks, the DSL
worker's attempts k = 0..3 at seeds 9001..9020, deduplicated by task and
source), then verifies every candidate with suite v2 in two modes:

* F: full execution with fail-fast charging (`fail_fast=True`), as in exp-008;
* E: early stop (`early_stop=True`): the run is streamed and stopped at the
  first failing case.

Each candidate is measured REPS times per mode, mode order shuffled per
repetition, candidate order shuffled once; all seeded. Measurements are
sequential in one process, after WARMUP discarded verifications. Per call it
records wall seconds around `verify`, parent CPU (`time.process_time`
delta, all parent threads) and child CPU (`stats`). The worker's attempt
wall time is recorded once per attempt (descriptive only).

Writes OUT_DIR/measurements.jsonl, corpus.jsonl, attempts.jsonl and
manifest.json. Run it on an otherwise idle machine.
"""

from __future__ import annotations

import hashlib
import json
import platform
import random
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "python"))

from frontier_py.realtasks.server import VERIFY_UNITS_PER_CASE  # noqa: E402
from frontier_py.realtasks.suite import HIDDEN_SEED, SUITE  # noqa: E402
from frontier_py.realtasks.worker import attempt  # noqa: E402
from frontier_py.verifiers.property_tests import verify  # noqa: E402

SEEDS = range(9001, 9021)
KS = range(4)
REPS = 3
WARMUP = 20
ORDER_SEED = 9009
SPEC = "0" * 64
MODES = {"F": {"fail_fast": True}, "E": {"early_stop": True}}


def corpus() -> tuple[list[dict], list[dict]]:
    attempts, seen, cands = [], set(), []
    for task in SUITE:
        for seed in SEEDS:
            for k in KS:
                t0 = time.perf_counter()
                a = attempt(task, seed, k)
                attempts.append({"task": task.name, "seed": seed, "k": k, "gen_wall_s": time.perf_counter() - t0,
                                 "gen_units": a["gen_units"]})
                key = (task.name, a["source"])
                if key not in seen:
                    seen.add(key)
                    cands.append({"id": len(cands), "task": task.name, "status": task.status, "source": a["source"]})
    return attempts, cands


def measure(task_def, source: str, mode: str) -> dict:
    stats: dict = {}
    c0, t0 = time.process_time(), time.perf_counter()
    r = verify(task_def, {"source": source}, spec_digest=SPEC, seed=HIDDEN_SEED, artifact_digest="1" * 64,
               charge_per_case=VERIFY_UNITS_PER_CASE, **MODES[mode])
    wall, cpu = time.perf_counter() - t0, time.process_time() - c0
    return {"verdict": r.verdict, "charge": r.cost_units, "wall_s": wall, "parent_cpu_s": cpu,
            "child_cpu_s": stats.get("child_cpu_seconds")}


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=False)
    by_name = {t.name: t.task_def("2") for t in SUITE}
    attempts, cands = corpus()
    with open(out / "corpus.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for c in cands:
            f.write(json.dumps(c) + "\n")
    with open(out / "attempts.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for a in attempts:
            f.write(json.dumps(a) + "\n")
    rng = random.Random(ORDER_SEED)
    order = list(range(len(cands)))
    rng.shuffle(order)
    for i in order[:WARMUP]:
        measure(by_name[cands[i]["task"]], cands[i]["source"], "F")
    started = time.time()
    with open(out / "measurements.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for i in order:
            c = cands[i]
            for rep in range(REPS):
                modes = list(MODES)
                rng.shuffle(modes)
                for pos, mode in enumerate(modes):
                    m = measure(by_name[c["task"]], c["source"], mode)
                    f.write(json.dumps({"id": i, "task": c["task"], "rep": rep, "mode": mode, "pos": pos, **m}) + "\n")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True,
                                text=True).stdout.strip())
    manifest = {
        "experiment_id": "exp-009-M", "candidates": len(cands), "attempts": len(attempts), "reps": REPS, "warmup": WARMUP,
        "source_commit": commit, "source_dirty": dirty, "python": sys.version, "platform": platform.platform(),
        "machine": platform.machine(), "processor": platform.processor(), "started_unix": started,
        "elapsed_s": time.time() - started,
        "measurements_sha256": hashlib.sha256((out / "measurements.jsonl").read_bytes()).hexdigest(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
