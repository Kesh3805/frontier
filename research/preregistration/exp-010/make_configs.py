"""Generate exp-010 configs: the exp-004/006/007 designs with verification
charged at the cost exp-009 measured (`--charge-model measured`).

Arms (budgets are the earlier ones times 5.5, the ratio of a v2 attempt plus
verification under the measured charge, 1.35 + 11.55 CU, to the same under
the per-case charge, 1.35 + 0.995 CU):

* S-v1:   exp-004 (catalog v1, suite v1), budgets 330 / 1320 / 2640;
* S-v2:   exp-006 (catalog v2, suite v2), same budgets;
* S-v2ff: exp-006 with --fail-fast, same budgets;
* D-v2:   exp-007 (catalog v3, suite v2), budgets 660 / 2640.

`verify_cost_units` (the runner's verification reservation, and the
verification cost policies assume) is the measured full charge rounded up:
10.9 CU for suite v1 (43 cases), 11.6 CU for suite v2 (199 cases).
Everything else is copied from the frozen source configs.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRE = HERE.parent
ARMS = (
    ("S-v1", "exp-004", (60, 240, 480), [], 10.9),
    ("S-v2", "exp-006", (60, 240, 480), [], 11.6),
    ("S-v2ff", "exp-006", (60, 240, 480), ["--fail-fast"], 11.6),
    ("D-v2", "exp-007", (120, 480), [], 11.6),
)
SCALE = 5.5

for arm, src, budgets, flags, verify_units in ARMS:
    for b in budgets:
        cfg = json.loads((PRE / src / f"b{b}.json").read_text(encoding="utf-8"))
        nb = int(b * SCALE)
        cfg["experiment_id"] = f"exp-010-{arm}-b{nb}"
        cfg["server"]["args"] = [*cfg["server"]["args"], *flags, "--charge-model", "measured"]
        cfg["run"]["budget_units"] = float(nb)
        cfg["run"]["verify_cost_units"] = verify_units
        with open(HERE / f"{arm}-b{nb}.json", "w", encoding="utf-8", newline="\n") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
