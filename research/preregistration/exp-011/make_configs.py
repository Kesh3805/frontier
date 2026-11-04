"""Generate exp-011 configs: does a cost-blind Thompson index remove hinted
Thompson's moderate-budget loss under the measured verification charge?

Parts (catalog v2, suite v2, fresh seeds 5001-5100):

* M: the exp-010 S-v2 configs (measured charge), budgets 330 / 1320 / 2640;
* P: the exp-006 configs (per-case charge), budgets 60 / 240 / 480.

Both parts run the same five policies. Everything else is copied from the
frozen source configs.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRE = HERE.parent
PARTS = (
    ("M", "exp-010", "S-v2-b{}.json", (330, 1320, 2640)),
    ("P", "exp-006", "b{}.json", (60, 240, 480)),
)
POLICIES = [
    {"kind": "round_robin"},
    {"kind": "thompson", "prior_strength": 2.0, "use_hints": True},
    {"kind": "thompson_flat", "prior_strength": 2.0, "use_hints": True},
    {"kind": "thompson", "prior_strength": 2.0, "use_hints": False},
    {"kind": "thompson_flat", "prior_strength": 2.0, "use_hints": False},
]

for part, src, name, budgets in PARTS:
    for b in budgets:
        cfg = json.loads((PRE / src / name.format(b)).read_text(encoding="utf-8"))
        cfg["experiment_id"] = f"exp-011-{part}-b{b}"
        cfg["policies"] = POLICIES
        cfg["seed_start"] = 5001
        with open(HERE / f"{part}-b{b}.json", "w", encoding="utf-8", newline="\n") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
