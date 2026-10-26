"""Generate the exp-007 dependency-task pilot configs (committed with their output)."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG_SHA256 = "6c63d226d405975517d67fc87f48e4d8345f6f315886cc59d87c35a9b70ef686"
POLICIES = [
    {"kind": "round_robin"},
    {"kind": "random"},
    {"kind": "greedy_prior"},
    {"kind": "thompson", "prior_strength": 2.0, "use_hints": True},
    {"kind": "thompson", "prior_strength": 2.0, "use_hints": False},
    {"kind": "oracle_index"},
]

for budget in (120, 480, 1920):
    cfg = {
        "schema_version": "0.1",
        "experiment_id": f"exp-007-b{budget}",
        "catalog": "../../realtasks/catalog-v3.json",
        "catalog_sha256": CATALOG_SHA256,
        "server": {"program": "python", "args": ["-m", "frontier_py.realtasks.server", "--suite-version", "2"], "cwd": "../../../python"},
        "policies": POLICIES,
        "seed_start": 3001,
        "seeds": 100,
        "run": {
            "seed": 0, "workers": 8, "budget_units": float(budget), "attempt_cap_units": 3.0, "verify_cost_units": 1.05,
            "crash_prob": 0.0, "max_attempts_per_task": 64, "max_parallel_per_task": 1, "prior_cost": 1.0,
            "policy": {"kind": "round_robin"},
        },
        "shuffle_problem_order": True,
    }
    with open(HERE / f"b{budget}.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
