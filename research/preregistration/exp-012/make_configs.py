"""Generate exp-012 configs: does pricing a task by the cost of one novel
candidate, and/or not counting reused rejections as failures, fix hinted
Thompson's moderate-budget loss under the measured verification charge?

The exp-010 S-v2 configs (catalog v2, suite v2, measured charge), budgets
330 / 1320 / 2640, fresh seeds 7001-7100, with six policies:

* round_robin;
* thompson (hints): the observed-cost, reuse-as-failure cell;
* thompson_novel (hints), the other three cells of cost x reuse;
* thompson_flat (hints), the exp-011 intervention, as a bridge.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRE = HERE.parent


def novel(per_novel_cost, reuse_is_failure):
    return {"kind": "thompson_novel", "prior_strength": 2.0, "use_hints": True,
            "per_novel_cost": per_novel_cost, "reuse_is_failure": reuse_is_failure}


POLICIES = [
    {"kind": "round_robin"},
    {"kind": "thompson", "prior_strength": 2.0, "use_hints": True},
    novel(False, False),
    novel(True, True),
    novel(True, False),
    {"kind": "thompson_flat", "prior_strength": 2.0, "use_hints": True},
]

for b in (330, 1320, 2640):
    cfg = json.loads((PRE / "exp-010" / f"S-v2-b{b}.json").read_text(encoding="utf-8"))
    cfg["experiment_id"] = f"exp-012-b{b}"
    cfg["policies"] = POLICIES
    cfg["seed_start"] = 7001
    with open(HERE / f"b{b}.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
