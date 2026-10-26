"""Generate the exp-003 real-task pilot configs (committed with their output)."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG_SHA256 = "80bdd82bec3e249b17d7938dab3e28786989dae55edd0650875c0c6c440b9585"
POLICIES = [
    {"kind": "round_robin"},
    {"kind": "fifo"},
    {"kind": "random"},
    {"kind": "greedy_prior"},
    {"kind": "thompson", "prior_strength": 2.0, "use_hints": True},
    {"kind": "thompson", "prior_strength": 2.0, "use_hints": False},
    {"kind": "oracle_index"},
]

for budget in (60, 240, 480):
    cfg = {
        "schema_version": "0.1",
        "experiment_id": f"exp-003-b{budget}",
        "catalog": "../../realtasks/catalog-v1.json",
        "catalog_sha256": CATALOG_SHA256,
        "server": {"program": "python", "args": ["-m", "frontier_py.realtasks.server"], "cwd": "../../../python"},
        "policies": POLICIES,
        "seed_start": 1001,
        "seeds": 100,
        "run": {
            "seed": 0, "workers": 8, "budget_units": float(budget), "attempt_cap_units": 3.0, "verify_cost_units": 0.25,
            "crash_prob": 0.0, "max_attempts_per_task": 64, "max_parallel_per_task": 1, "prior_cost": 1.0,
            "policy": {"kind": "round_robin"},
        },
    }
    with open(HERE / f"b{budget}.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
