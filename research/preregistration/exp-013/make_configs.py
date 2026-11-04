"""Generate exp-013 configs: which tail of the hint prior costs hinted
Thompson its moderate-budget yield under the measured verification charge?

The exp-010 S-v2 configs (catalog v2, suite v2, measured charge), budgets
330 / 1320 / 2640, fresh seeds 9001-9100, with six policies:

* round_robin and hint-free thompson, as anchors;
* hinted thompson (neither tail tempered);
* thompson_tempered with the high tail, the low tail, or both pulled
  half-way to 0.5 (factor 0.5).
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRE = HERE.parent


def tempered(high, low):
    return {"kind": "thompson_tempered", "prior_strength": 2.0, "high": high, "low": low}


POLICIES = [
    {"kind": "round_robin"},
    {"kind": "thompson", "prior_strength": 2.0, "use_hints": True},
    tempered(0.5, 1.0),
    tempered(1.0, 0.5),
    tempered(0.5, 0.5),
    {"kind": "thompson", "prior_strength": 2.0, "use_hints": False},
]

for b in (330, 1320, 2640):
    cfg = json.loads((PRE / "exp-010" / f"S-v2-b{b}.json").read_text(encoding="utf-8"))
    cfg["experiment_id"] = f"exp-013-b{b}"
    cfg["policies"] = POLICIES
    cfg["seed_start"] = 9001
    with open(HERE / f"b{b}.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
