"""Generate exp-009 part C configs: exp-008's S-b60 with the service in fail-fast
(F) or early-stop (E) mode, two copies of each for the ABBA run order
E1, F1, F2, E2.

Everything except the experiment id and the service's mode flag is copied
from the frozen exp-008 S-b60 config, so runs pair seed for seed.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRE = HERE.parent

base = json.loads((PRE / "exp-008" / "S-b60.json").read_text(encoding="utf-8"))
args = [a for a in base["server"]["args"] if a != "--fail-fast"]
for name, flag in (("C-E1", "--early-stop"), ("C-F1", "--fail-fast"), ("C-F2", "--fail-fast"), ("C-E2", "--early-stop")):
    cfg = json.loads(json.dumps(base))
    cfg["experiment_id"] = f"exp-009-{name}"
    cfg["server"]["args"] = [*args, flag]
    with open(HERE / f"{name}.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
