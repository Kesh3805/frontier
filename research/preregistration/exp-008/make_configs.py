"""Generate exp-008 configs: exp-006 (part S) and exp-007 (part D) with fail-fast charging.

Everything except the experiment id and the service's --fail-fast flag is
copied from the frozen exp-006 / exp-007 configs, so runs pair seed for seed.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRE = HERE.parent

for part, src, budgets in (("S", "exp-006", (60, 240, 480)), ("D", "exp-007", (120, 480, 1920))):
    for b in budgets:
        cfg = json.loads((PRE / src / f"b{b}.json").read_text(encoding="utf-8"))
        cfg["experiment_id"] = f"exp-008-{part}-b{b}"
        cfg["server"]["args"] = [*cfg["server"]["args"], "--fail-fast"]
        with open(HERE / f"{part}-b{b}.json", "w", encoding="utf-8", newline="\n") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
